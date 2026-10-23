"""Single source of truth for Mumbai fare rules.

Both the training script and the Streamlit app import from here, so the data
the model is trained on and the inputs it sees at prediction time are built
by exactly the same code (no train/serve skew, no double-applied multipliers).
"""
from __future__ import annotations

import json
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from typing import Dict, Mapping, Optional, Tuple

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
PLATFORM_CONFIG_PATH = BASE_DIR / "platform_fares.json"

PLATFORM_KEYS = ("ola_mini", "uber_go", "rapido_bike_cab", "mumbai_kaali_peeli")
_REQUIRED_PLATFORM_FIELDS = (
    "name", "base_fare", "free_km", "per_km_rate", "per_min_rate", "minimum_fare",
    "surge_peak_multiplier", "surge_night_multiplier", "rain_multiplier",
    "heavy_rain_multiplier",
)

MIN_FARE = 28.0

# ---- Time windows --------------------------------------------------------
# Inclusive hour ranges for peak traffic / surge.
PEAK_WINDOWS = ((8, 11), (17, 21))
# Night window: start <= hour < end (wraps past midnight if start > end).
# ASSUMPTION - verify against the current Mumbai taxi tariff notification.
NIGHT_START_HOUR = 0
NIGHT_END_HOUR = 5

# ---- Geography -----------------------------------------------------------
# Rough bounding box of the Mumbai Metropolitan core, used only for warnings.
SERVICE_AREA = {"lat_min": 18.85, "lat_max": 19.45, "lon_min": 72.70, "lon_max": 73.20}

TRAFFIC_ZONES: Dict[str, Tuple[float, float]] = {
    "BKC": (19.0600, 72.8650),
    "Dadar": (19.0180, 72.8430),
    "Andheri": (19.1190, 72.8460),
    "Sion": (19.0430, 72.8610),
    "Powai": (19.1180, 72.9050),
    "Airport": (19.0990, 72.8740),
}
TRAFFIC_ZONE_RADIUS_KM = 2.5

# Vehicle categories are an ASSUMPTION (not learned from data).
VEHICLE_MULTIPLIERS = {
    "Auto Rickshaw": 0.85,
    "Kaali-Peeli Taxi": 0.95,
    "Hatchback / Sedan": 1.00,
    "SUV Prime": 1.45,
}

WEATHER_LABELS = {0: "Sunny / Clear", 1: "Monsoon Rain", 2: "Heavy Torrential Rain"}

# Features fed to the ML model (order matters).
FEATURES = [
    "route_distance_km",
    "route_duration_min",
    "pickup_hour",
    "is_peak",
    "is_night",
    "weather_flag",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return r * 2 * atan2(sqrt(a), sqrt(1 - a))


def in_service_area(lat: float, lon: float) -> bool:
    a = SERVICE_AREA
    return a["lat_min"] <= lat <= a["lat_max"] and a["lon_min"] <= lon <= a["lon_max"]


def is_peak_hour(hour: int) -> bool:
    return any(lo <= hour <= hi for lo, hi in PEAK_WINDOWS)


def is_night_hour(hour: int) -> bool:
    if NIGHT_START_HOUR <= NIGHT_END_HOUR:
        return NIGHT_START_HOUR <= hour < NIGHT_END_HOUR
    return hour >= NIGHT_START_HOUR or hour < NIGHT_END_HOUR


def load_config(path: Optional[Path] = None) -> dict:
    """Load and validate platform_fares.json (raises on a missing/invalid file)."""
    path = Path(path) if path else PLATFORM_CONFIG_PATH
    with open(path, "r", encoding="utf-8") as fh:
        config = json.load(fh)
    platforms = config.get("platforms", {})
    for key in PLATFORM_KEYS:
        if key not in platforms:
            raise ValueError(f"platform_fares.json is missing platform '{key}'")
        missing = [f for f in _REQUIRED_PLATFORM_FIELDS if f not in platforms[key]]
        if missing:
            raise ValueError(f"platform '{key}' is missing fields: {missing}")
        vm = platforms[key].get("vehicle_multipliers")
        if not isinstance(vm, dict) or any(v not in vm for v in VEHICLE_MULTIPLIERS):
            raise ValueError(f"platform '{key}' needs vehicle_multipliers for {list(VEHICLE_MULTIPLIERS)}")
    return config


# ---------------------------------------------------------------------------
# Traffic (rule-based estimate - NOT live data)
# ---------------------------------------------------------------------------
def traffic_level(p_lat: float, p_lon: float, d_lat: float, d_lon: float,
                  hour: int, weather_flag: int) -> Tuple[str, float]:
    """Estimate congestion from time of day, rain and proximity to busy zones.

    Returns (label, duration_multiplier).
    """
    score = 0
    if 8 <= hour <= 11:
        score += 2
    if 17 <= hour <= 21:
        score += 3
    score += int(weather_flag)
    for z_lat, z_lon in TRAFFIC_ZONES.values():
        if (haversine_km(p_lat, p_lon, z_lat, z_lon) < TRAFFIC_ZONE_RADIUS_KM
                or haversine_km(d_lat, d_lon, z_lat, z_lon) < TRAFFIC_ZONE_RADIUS_KM):
            score += 1
    if score <= 1:
        return "Low", 1.00
    if score <= 3:
        return "Moderate", 1.22
    return "Heavy", 1.48


# ---------------------------------------------------------------------------
# Platform fares
# ---------------------------------------------------------------------------
def weather_multiplier(pcfg: Mapping, weather_flag: int) -> float:
    if weather_flag == 1:
        return float(pcfg["rain_multiplier"])
    if weather_flag >= 2:
        return float(pcfg["heavy_rain_multiplier"])
    return 1.0


def platform_fare(pcfg: Mapping, dist_km: float, dur_min: float,
                  hour: int, weather_flag: int) -> float:
    """Fare for one platform. `dur_min` must already include traffic effects."""
    chargeable_km = max(dist_km - float(pcfg["free_km"]), 0.0)
    fare = (float(pcfg["base_fare"])
            + chargeable_km * float(pcfg["per_km_rate"])
            + dur_min * float(pcfg["per_min_rate"]))
    fare = max(fare, float(pcfg["minimum_fare"]))
    if is_peak_hour(hour):
        fare *= float(pcfg["surge_peak_multiplier"])
    if is_night_hour(hour):
        fare *= float(pcfg["surge_night_multiplier"])
    fare *= weather_multiplier(pcfg, weather_flag)
    return fare


def all_platform_fares(config: Mapping, dist_km: float, dur_min: float,
                       hour: int, weather_flag: int) -> Dict[str, float]:
    return {
        key: platform_fare(config["platforms"][key], dist_km, dur_min, hour, weather_flag)
        for key in PLATFORM_KEYS
    }


def vehicle_fares(config: Mapping, dist_km: float, dur_min: float, hour: int,
                  weather_flag: int, vehicle_type: str) -> Dict[str, Optional[float]]:
    """Fare per platform for the SELECTED vehicle category.

    Returns None for a platform that does not offer that category (e.g. a Kaali-Peeli
    meter taxi has no SUV), so the UI can show 'not available' instead of a fake price.
    """
    result: Dict[str, Optional[float]] = {}
    for key in PLATFORM_KEYS:
        pcfg = config["platforms"][key]
        mult = pcfg["vehicle_multipliers"].get(vehicle_type)
        result[key] = None if mult is None else platform_fare(pcfg, dist_km, dur_min, hour, weather_flag) * float(mult)
    return result


def fair_price(fares: Mapping[str, float]) -> float:
    """Definition of the ML target: mean of the four platform estimates."""
    return max(float(np.mean(list(fares.values()))), MIN_FARE)


# ---------------------------------------------------------------------------
# ML model wrapper
# ---------------------------------------------------------------------------
def baseline_fare(dist_km, dur_min):
    """Simple linear scale. The model predicts fare / baseline (a ratio), which
    lets it extrapolate sensibly for trips longer than any seen in training."""
    return 30.0 + 14.0 * np.asarray(dist_km, dtype=float) + 1.5 * np.asarray(dur_min, dtype=float)


def feature_row(dist_km: float, dur_min: float, hour: int, weather_flag: int) -> dict:
    return {
        "route_distance_km": float(dist_km),
        "route_duration_min": float(dur_min),
        "pickup_hour": int(hour),
        "is_peak": int(is_peak_hour(hour)),
        "is_night": int(is_night_hour(hour)),
        "weather_flag": int(weather_flag),
    }


class FareModel:
    """Pickle-able wrapper: regressor predicts a ratio, we scale by the baseline."""

    def __init__(self, regressor, features=None, meta: Optional[dict] = None):
        self.regressor = regressor
        self.features = list(features or FEATURES)
        self.meta = meta or {}

    def predict_frame(self, frame: pd.DataFrame) -> np.ndarray:
        ratio = self.regressor.predict(frame[self.features])
        base = baseline_fare(frame["route_distance_km"], frame["route_duration_min"])
        return np.maximum(ratio * base, MIN_FARE)

    def predict_one(self, dist_km: float, dur_min: float, hour: int, weather_flag: int) -> float:
        frame = pd.DataFrame([feature_row(dist_km, dur_min, hour, weather_flag)])
        return float(self.predict_frame(frame)[0])
