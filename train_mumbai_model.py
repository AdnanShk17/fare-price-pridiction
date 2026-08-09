import numpy as np
import pandas as pd
from math import radians, sin, cos, sqrt, atan2
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
import joblib
import json
import os

print("--- Starting Mumbai Cab Fare Dataset & Model Training Pipeline ---")

# 1. Haversine distance function (in km)
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

# 2. Key Mumbai Hub Coordinates
MUMBAI_HUBS = [
    (18.9400, 72.8353), # CST Station
    (18.9438, 72.8234), # Marine Drive
    (19.0178, 72.8478), # Dadar
    (19.0657, 72.8687), # BKC
    (19.0596, 72.8295), # Bandra
    (19.1197, 72.8464), # Andheri
    (19.0896, 72.8656), # Mumbai Airport T2
    (19.1264, 72.9080), # Powai
    (19.2183, 72.9781), # Thane
    (19.0771, 72.9986), # Vashi
]

np.random.seed(42)
num_samples = 5000

data = []
for _ in range(num_samples):
    # Select pickup hub and add random noise
    p_hub = MUMBAI_HUBS[np.random.randint(0, len(MUMBAI_HUBS))]
    p_lat = p_hub[0] + np.random.uniform(-0.02, 0.02)
    p_lon = p_hub[1] + np.random.uniform(-0.02, 0.02)
    
    # Select dropoff hub
    d_hub = MUMBAI_HUBS[np.random.randint(0, len(MUMBAI_HUBS))]
    d_lat = d_hub[0] + np.random.uniform(-0.02, 0.02)
    d_lon = d_hub[1] + np.random.uniform(-0.02, 0.02)
    
    dist_km = haversine(p_lat, p_lon, d_lat, d_lon)
    if dist_km < 0.5:
        dist_km = np.random.uniform(1.2, 3.5) # ensure reasonable trip distance
        
    passengers = np.random.choice([1, 2, 3, 4], p=[0.6, 0.25, 0.1, 0.05])
    hour = np.random.randint(0, 24)
    day_of_week = np.random.randint(0, 7)
    
    # Traffic estimation based on hour
    if 8 <= hour <= 11 or 17 <= hour <= 21:
        traffic_factor = np.random.uniform(1.3, 1.7) # Peak rush hours
    elif 22 <= hour or hour <= 5:
        traffic_factor = np.random.uniform(0.9, 1.1) # Night traffic
    else:
        traffic_factor = np.random.uniform(1.0, 1.25)
        
    # Duration estimation (in mins) based on distance and traffic
    avg_speed_kmh = 22 / traffic_factor # Mumbai avg speed ~22 km/h
    duration_min = (dist_km / avg_speed_kmh) * 60
    
    # Weather flag: 0=Sunny, 1=Rainy, 2=Heavy Rain
    weather_flag = np.random.choice([0, 1, 2], p=[0.75, 0.20, 0.05])
    weather_mult = 1.0 if weather_flag == 0 else (1.15 if weather_flag == 1 else 1.30)
    
    # Night surge multiplier (11 PM - 5 AM)
    night_mult = 1.25 if (hour >= 23 or hour <= 5) else 1.0
    
    # Mumbai Auto / Taxi fare formula base calculation:
    # Base fare ~ ₹28 for first 1.5 km, ~ ₹18.5/km after
    if dist_km <= 1.5:
        base_fare = 28.0
    else:
        base_fare = 28.0 + (dist_km - 1.5) * 18.5
        
    # Time charge ~ ₹1.5 per minute of trip
    time_charge = duration_min * 1.5
    
    # Total fare calculation with mild random variation
    fare = (base_fare + time_charge) * traffic_factor * weather_mult * night_mult
    fare += np.random.normal(0, 5.0) # Add realistic noise
    fare = max(fare, 28.0) # Minimum fare in Mumbai
    
    data.append({
        'pickup_latitude': round(p_lat, 6),
        'pickup_longitude': round(p_lon, 6),
        'dropoff_latitude': round(d_lat, 6),
        'dropoff_longitude': round(d_lon, 6),
        'passenger_count': int(passengers),
        'route_distance_km': round(dist_km, 2),
        'route_duration_min': round(duration_min, 1),
        'pickup_hour': int(hour),
        'day_of_week': int(day_of_week),
        'weather_flag': int(weather_flag),
        'fare_amount': round(fare, 2)
    })

df = pd.DataFrame(data)

# Save Mumbai dataset to CSV
dataset_path = os.path.join(os.path.dirname(__file__), "mumbai_cab_fare_train.csv")
df.to_csv(dataset_path, index=False)
print(f"[SUCCESS] Created Mumbai dataset: {dataset_path} ({len(df)} rows)")

# 3. Model Training
X = df[['pickup_latitude', 'pickup_longitude', 'dropoff_latitude', 'dropoff_longitude', 
        'passenger_count', 'route_distance_km', 'route_duration_min', 'pickup_hour', 
        'day_of_week', 'weather_flag']]
y = df['fare_amount']

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

model = RandomForestRegressor(n_estimators=100, max_depth=15, random_state=42)
model.fit(X_train, y_train)

# Evaluation
y_pred = model.predict(X_test)
mae = mean_absolute_error(y_test, y_pred)
rmse = np.sqrt(mean_squared_error(y_test, y_pred))
r2 = r2_score(y_test, y_pred)

print(f"Model Performance on Test Set:")
print(f"   MAE:  Rs.{mae:.2f}")
print(f"   RMSE: Rs.{rmse:.2f}")
print(f"   R2 Score: {r2:.4f}")

# Save trained model
model_file = os.path.join(os.path.dirname(__file__), "mumbai_cab_fare_model.pkl")
joblib.dump(model, model_file)
print(f"[SUCCESS] Saved trained model to {model_file}")

# Save metrics JSON for reporting
metrics = {
    "model_name": "RandomForestRegressor",
    "dataset_records": len(df),
    "mae": round(float(mae), 2),
    "rmse": round(float(rmse), 2),
    "r2_score": round(float(r2), 4),
    "target_currency": "INR (₹)",
    "city": "Mumbai, India"
}
metrics_file = os.path.join(os.path.dirname(__file__), "mumbai_model_metrics.json")
with open(metrics_file, "w") as f:
    json.dump(metrics, f, indent=4)

print("--- Mumbai Model Training Completed Successfully ---")
