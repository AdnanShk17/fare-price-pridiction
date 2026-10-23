"""Generate the simulated Mumbai trip dataset and train the fare model.

IMPORTANT: the dataset is SIMULATED. Fares are produced by the pricing rules in
`fare_logic.py` / `platform_fares.json` (plus noise); no real trip records are
used. Metrics therefore measure how well the model learns those rules, not how
close it is to real-world Ola/Uber/taxi prices.

Usage:  python train_mumbai_model.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")  # never block on plt.show(); just write the PNGs
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

import fare_logic as fl

BASE_DIR = Path(__file__).resolve().parent
DATASET_PATH = BASE_DIR / "mumbai_cab_fare_train.csv"
MODEL_PATH = BASE_DIR / "mumbai_cab_fare_model.pkl"
METRICS_PATH = BASE_DIR / "mumbai_model_metrics.json"
PLOT_PATH = BASE_DIR / "actual_vs_predicted.png"
IMPORTANCE_PLOT_PATH = BASE_DIR / "feature_importance.png"

SEED = 42

MUMBAI_HUBS = [
    (18.9400, 72.8353),  # CST Station
    (18.9438, 72.8234),  # Marine Drive
    (19.0178, 72.8478),  # Dadar
    (19.0657, 72.8687),  # BKC
    (19.0596, 72.8295),  # Bandra
    (19.1197, 72.8464),  # Andheri
    (19.0896, 72.8656),  # Mumbai Airport T2
    (19.1264, 72.9080),  # Powai
    (19.2183, 72.9781),  # Thane
    (19.0771, 72.9986),  # Vashi
]

# Outer-MMR / getaway towns so the model also sees 50-160 km trips.
DISTANT_HUBS = [
    (18.6414, 72.8722),  # Alibaug
    (18.9107, 73.3236),  # Karjat
    (18.7546, 73.4062),  # Lonavala
    (18.5204, 73.8567),  # Pune
    (19.9975, 73.7898),  # Nashik
    (20.0110, 73.7903),  # Nashik Road
    (19.2403, 73.1305),  # Kalyan-Badlapur belt
    (18.4088, 72.8064),  # Murud
]


def generate_dataset(n_city_tight: int = 3500, n_city_wide: int = 1500, n_long: int = 2200,
                     seed: int = SEED, config: dict | None = None) -> pd.DataFrame:
    """Simulate trips. Distances are ROAD-like (straight line x detour factor),
    durations include the same traffic multiplier the app applies, and fares come
    from the same functions the app uses to compare platforms."""
    rng = np.random.default_rng(seed)
    config = config or fl.load_config()

    plan = (
        [(MUMBAI_HUBS, MUMBAI_HUBS, 0.02)] * n_city_tight
        + [(MUMBAI_HUBS, MUMBAI_HUBS, 0.04)] * n_city_wide
        + [(MUMBAI_HUBS, DISTANT_HUBS, 0.02)] * n_long
    )

    def jitter(pool, noise):
        lat, lon = pool[rng.integers(0, len(pool))]
        return lat + rng.uniform(-noise, noise), lon + rng.uniform(-noise, noise)

    rows = []
    for pickup_pool, drop_pool, noise in plan:
        p_lat, p_lon = jitter(pickup_pool, noise)
        d_lat, d_lon = jitter(drop_pool, noise)

        straight_km = fl.haversine_km(p_lat, p_lon, d_lat, d_lon)
        road_km = max(straight_km * rng.uniform(1.15, 1.45), 0.6)  # detour factor

        free_flow_speed = rng.uniform(20, 38) if road_km <= 40 else rng.uniform(40, 65)
        free_flow_min = road_km / free_flow_speed * 60

        hour = int(rng.integers(0, 24))
        weather_flag = int(rng.choice([0, 1, 2], p=[0.75, 0.20, 0.05]))
        level, traffic_mult = fl.traffic_level(p_lat, p_lon, d_lat, d_lon, hour, weather_flag)
        duration_min = free_flow_min * traffic_mult

        fares = fl.all_platform_fares(config, road_km, duration_min, hour, weather_flag)
        noisy = {k: v * float(np.clip(rng.normal(1.0, 0.03), 0.9, 1.1)) for k, v in fares.items()}
        fare = fl.fair_price(noisy)

        row = {
            "pickup_latitude": round(p_lat, 6),
            "pickup_longitude": round(p_lon, 6),
            "dropoff_latitude": round(d_lat, 6),
            "dropoff_longitude": round(d_lon, 6),
            "route_distance_km": round(road_km, 2),
            "route_duration_min": round(duration_min, 1),
            "pickup_hour": hour,
            "weather_flag": weather_flag,
            "traffic_level": level,
            "ola_fare": round(noisy["ola_mini"], 2),
            "uber_fare": round(noisy["uber_go"], 2),
            "rapido_fare": round(noisy["rapido_bike_cab"], 2),
            "kaali_peeli_fare": round(noisy["mumbai_kaali_peeli"], 2),
            "fare_amount": round(fare, 2),
            # coarse origin/destination cell, used to keep similar trips in the same CV fold
            "route_group": f"{round(p_lat / 0.05)}_{round(p_lon / 0.05)}>{round(d_lat / 0.05)}_{round(d_lon / 0.05)}",
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    df["is_peak"] = df["pickup_hour"].map(lambda h: int(fl.is_peak_hour(int(h))))
    df["is_night"] = df["pickup_hour"].map(lambda h: int(fl.is_night_hour(int(h))))
    return df


def _scores(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    return {
        "mae": round(float(mean_absolute_error(y_true, y_pred)), 2),
        "rmse": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 2),
        "r2_score": round(float(r2_score(y_true, y_pred)), 4),
        "mape_pct": round(float(np.mean(np.abs(y_true - y_pred) / y_true) * 100), 2),
    }


def _new_regressor() -> RandomForestRegressor:
    return RandomForestRegressor(
        n_estimators=150, max_depth=12, min_samples_leaf=5, n_jobs=-1, random_state=SEED
    )


def _fit_ratio(df_train: pd.DataFrame) -> RandomForestRegressor:
    ratio = df_train["fare_amount"] / fl.baseline_fare(
        df_train["route_distance_km"], df_train["route_duration_min"])
    reg = _new_regressor()
    reg.fit(df_train[fl.FEATURES], ratio)
    return reg


def main() -> None:
    print("--- Mumbai cab fare: dataset generation + model training (SIMULATED data) ---")
    df = generate_dataset()
    df.to_csv(DATASET_PATH, index=False)
    print(f"[OK] dataset: {DATASET_PATH.name} ({len(df)} rows)")

    # ---- Held-out evaluation, grouped by origin/destination cell -----------
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=SEED)
    train_idx, test_idx = next(splitter.split(df, groups=df["route_group"]))
    df_train, df_test = df.iloc[train_idx], df.iloc[test_idx]

    holdout_model = fl.FareModel(_fit_ratio(df_train))
    y_test = df_test["fare_amount"].to_numpy()
    y_pred = holdout_model.predict_frame(df_test)
    holdout = _scores(y_test, y_pred)

    lin = LinearRegression().fit(df_train[["route_distance_km", "route_duration_min"]], df_train["fare_amount"])
    lin_pred = lin.predict(df_test[["route_distance_km", "route_duration_min"]])
    linear_baseline = _scores(y_test, lin_pred)

    bands = {}
    for lo, hi in [(0, 10), (10, 20), (20, 40), (40, 1000)]:
        mask = (df_test["route_distance_km"] >= lo) & (df_test["route_distance_km"] < hi)
        if mask.any():
            bands[f"{lo}-{hi if hi < 1000 else '+'}km"] = _scores(y_test[mask.to_numpy()], y_pred[mask.to_numpy()])

    # ---- 5-fold grouped cross-validation -----------------------------------
    cv_mae = []
    for tr, te in GroupKFold(n_splits=5).split(df, groups=df["route_group"]):
        m = fl.FareModel(_fit_ratio(df.iloc[tr]))
        cv_mae.append(mean_absolute_error(df.iloc[te]["fare_amount"], m.predict_frame(df.iloc[te])))

    print("\n========== HELD-OUT PERFORMANCE (unseen route cells) ==========")
    print(f"MAE  : Rs {holdout['mae']:.2f}   RMSE: Rs {holdout['rmse']:.2f}   "
          f"R2: {holdout['r2_score']:.4f}   MAPE: {holdout['mape_pct']:.2f}%")
    print(f"Linear(dist,dur) baseline MAE: Rs {linear_baseline['mae']:.2f}  R2: {linear_baseline['r2_score']:.4f}")
    print(f"5-fold grouped CV MAE: Rs {np.mean(cv_mae):.2f} +/- {np.std(cv_mae):.2f}")

    # ---- Plots -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.scatter(y_test, y_pred, alpha=0.4, s=12)
    lim = [0, max(y_test.max(), y_pred.max())]
    ax.plot(lim, lim, "r--", linewidth=2)
    ax.set_title(f"Actual vs Predicted fare - held-out routes (R2 = {holdout['r2_score']:.4f})")
    ax.set_xlabel("Actual simulated fare (Rs)")
    ax.set_ylabel("Predicted fare (Rs)")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOT_PATH, dpi=150)
    plt.close(fig)

    # ---- Final model: refit on all rows (metrics above are from the held-out split)
    final_reg = _fit_ratio(df)
    importances = dict(zip(fl.FEATURES, (round(float(v), 4) for v in final_reg.feature_importances_)))

    fig, ax = plt.subplots(figsize=(7, 4))
    order = sorted(importances, key=importances.get)
    ax.barh(order, [importances[k] for k in order])
    ax.set_title("Random Forest feature importance (fare / baseline ratio)")
    ax.grid(alpha=0.3, axis="x")
    fig.tight_layout()
    fig.savefig(IMPORTANCE_PLOT_PATH, dpi=150)
    plt.close(fig)

    metrics = {
        "model_name": "Random Forest Regressor (predicts fare / baseline ratio)",
        "data_source": "simulated",
        "dataset_records": int(len(df)),
        "evaluation": "20% held-out split grouped by origin/destination cell (unseen route cells)",
        "n_estimators": final_reg.n_estimators,
        "max_depth": final_reg.max_depth,
        "min_samples_leaf": final_reg.min_samples_leaf,
        "features": fl.FEATURES,
        "mae": holdout["mae"],
        "rmse": holdout["rmse"],
        "r2_score": holdout["r2_score"],
        "mape_pct": holdout["mape_pct"],
        "cv_mae_mean": round(float(np.mean(cv_mae)), 2),
        "cv_mae_std": round(float(np.std(cv_mae)), 2),
        "linear_baseline": linear_baseline,
        "mae_by_distance_band": bands,
        "feature_importance": importances,
        "city": "Mumbai",
        "currency": "INR",
        "sklearn_version": sklearn.__version__,
        "trained_on": date.today().isoformat(),
    }
    with open(METRICS_PATH, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=4)

    final_model = fl.FareModel(final_reg, meta={"sklearn_version": sklearn.__version__})
    joblib.dump(final_model, MODEL_PATH, compress=3)
    print(f"\n[OK] model saved: {MODEL_PATH.name} ({MODEL_PATH.stat().st_size / 1e6:.1f} MB)")
    print("[OK] metrics + plots written")


if __name__ == "__main__":
    sys.exit(main())
