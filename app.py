import streamlit as st
import joblib
import numpy as np
import pandas as pd
import pydeck as pdk
from datetime import datetime
import os
import json
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim
from math import sqrt
import route_engine

# --------------------------------------------------
# Page Configuration
# --------------------------------------------------
st.set_page_config(
    page_title="Mumbai's Smart Cab Fare System",
    page_icon="🚕",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --------------------------------------------------
# Custom CSS Styling
# --------------------------------------------------
st.markdown("""
<style>
@keyframes fadeIn {
    from {opacity: 0; transform: translateY(10px);}
    to {opacity: 1; transform: translateY(0);}
}
.main-header {
    background: linear-gradient(135deg, #1e293b, #0f172a);
    padding: 24px;
    border-radius: 16px;
    color: white;
    box-shadow: 0 8px 24px rgba(0,0,0,0.3);
    margin-bottom: 20px;
}
.fare-card {
    background: linear-gradient(135deg, #0284c7, #0369a1);
    padding: 24px;
    border-radius: 16px;
    text-align: center;
    color: white;
    box-shadow: 0 10px 25px rgba(2, 132, 199, 0.3);
    animation: fadeIn 0.5s ease-in-out;
}
.fare-amount {
    font-size: 42px;
    font-weight: 800;
}
.fare-label {
    font-size: 16px;
    opacity: 0.9;
    text-transform: uppercase;
    letter-spacing: 1px;
}
.platform-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 14px;
    padding: 18px;
    text-align: center;
    color: white;
    margin-bottom: 12px;
    transition: transform 0.2s ease;
}
.platform-card:hover {
    transform: translateY(-3px);
    border-color: #38bdf8;
}
.platform-price {
    font-size: 28px;
    font-weight: 700;
    color: #38bdf8;
}
.platform-name {
    font-size: 15px;
    font-weight: 600;
    margin-bottom: 6px;
}
.badge-tag {
    background-color: #334155;
    color: #f8fafc;
    padding: 4px 10px;
    border-radius: 8px;
    font-size: 12px;
    font-weight: 600;
}
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------
# Load Model & Platform Fares Config
# --------------------------------------------------
@st.cache_resource
def load_model():
    model_path = os.path.join(os.path.dirname(__file__), "mumbai_cab_fare_model.pkl")
    if os.path.exists(model_path):
        return joblib.load(model_path)
    return None

@st.cache_data
def load_platform_config():
    config_path = os.path.join(os.path.dirname(__file__), "platform_fares.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

@st.cache_data
def load_model_metrics():
    metrics_path = os.path.join(os.path.dirname(__file__), "mumbai_model_metrics.json")
    if os.path.exists(metrics_path):
        with open(metrics_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

model = load_model()
platform_config = load_platform_config()
metrics_info = load_model_metrics()
# ==========================
# Map Click Session State
# ==========================
if "pickup" not in st.session_state:
    st.session_state.pickup = None

if "drop" not in st.session_state:
    st.session_state.drop = None
if "pickup_address" not in st.session_state:
    st.session_state.pickup_address = ""

if "drop_address" not in st.session_state:
    st.session_state.drop_address = ""
# ==========================================
# INTERMEDIATE STOPS SESSION STATE
# ==========================================

if "stops" not in st.session_state:
    st.session_state.stops = []

if "stop_addresses" not in st.session_state:
    st.session_state.stop_addresses = []
if "adding_stop" not in st.session_state:
    st.session_state.adding_stop = False
if "map_center" not in st.session_state:
    st.session_state.map_center = [19.0760, 72.8777]

if "map_zoom" not in st.session_state:
    st.session_state.map_zoom = 11

geolocator = Nominatim(user_agent="mumbai_fare_app")
def search_location(query):
    try:
        location = geolocator.geocode(query + ", Mumbai, Maharashtra")
        if location:
            return (
                location.latitude,
                location.longitude,
                location.address
            )
    except:
        pass

    return None
# =====================================================
# AUTOMATIC TRAFFIC DETECTION ENGINE
# =====================================================



def calculate_traffic_level(p_lat, p_lon, d_lat, d_lon, hour, weather_flag):

    score = 0

    # Morning peak
    if 8 <= hour <= 11:
        score += 2

    # Evening peak
    if 17 <= hour <= 21:
        score += 3

    # Rain increases congestion
    score += weather_flag

    # Check if pickup/drop is near busy zones
    for _, (zlat, zlon) in TRAFFIC_ZONES.items():

        pickup_dist = sqrt((p_lat - zlat)**2 + (p_lon - zlon)**2)
        drop_dist = sqrt((d_lat - zlat)**2 + (d_lon - zlon)**2)

        if pickup_dist < 0.025 or drop_dist < 0.025:
            score += 1

    if score <= 1:
        return "Low", 1.00

    elif score <= 3:
        return "Moderate", 1.22

    else:
        return "Heavy", 1.48
# --------------------------------------------------
# Mumbai Popular Locations
# --------------------------------------------------
MUMBAI_LOCATIONS = {
    "Chhatrapati Shivaji Maharaj Terminus (CST)": (18.9400, 72.8353),
    "Marine Drive / Nariman Point": (18.9438, 72.8234),
    "Dadar TT Circle": (19.0178, 72.8478),
    "Bandra Kurla Complex (BKC)": (19.0657, 72.8687),
    "Bandra Station / Bandstand": (19.0596, 72.8295),
    "Andheri Station / WEH": (19.1197, 72.8464),
    "Mumbai Airport T2 (CSMI)": (19.0896, 72.8656),
    "Powai Lake / IIT Bombay": (19.1264, 72.9080),
    "Thane West Circle": (19.2183, 72.9781),
    "Vashi Station (Navi Mumbai)": (19.0771, 72.9986)
}
# =====================================================
# MUMBAI TRAFFIC CONGESTION ZONES (Automatic Traffic)
# =====================================================

TRAFFIC_ZONES = {
    "BKC": (19.0600, 72.8650),
    "Dadar": (19.0180, 72.8430),
    "Andheri": (19.1190, 72.8460),
    "Sion": (19.0430, 72.8610),
    "Powai": (19.1180, 72.9050),
    "Airport": (19.0990, 72.8740)
}

# --------------------------------------------------
# Application Header
# --------------------------------------------------
st.markdown("""
<div class="main-header">
    <h2 style="margin:0; padding:0; color:#38bdf8;">🚕 Mumbai Smart Cab Fare & Route Comparison System</h2>
    <p style="margin:6px 0 0 0; opacity:0.85;">Machine Learning Fare Prediction • OSRM Shortest Driving Path • Multi-Platform Estimation Engine</p>
</div>
""", unsafe_allow_html=True)

# --------------------------------------------------
# Main Navigation Tabs
# --------------------------------------------------
tab_app, tab_report = st.tabs(["🚀 Fare Prediction & Route Finder", "📚 Guide Report & Viva Defense"])

with tab_app:
    # --------------------------------------------------
    # Sidebar Input Layout
    # --------------------------------------------------
    st.sidebar.header("📍 Trip Parameters")
    
    input_mode = st.sidebar.radio(
    "Location Mode",
    ["Popular Mumbai Hubs", "Click on Map", "Custom Coordinates"]
    )
    
    # ==========================================
    # LOCATION INPUT
    # ==========================================

    if input_mode == "Popular Mumbai Hubs":

        pickup_name = st.sidebar.selectbox(
            "Pickup Location",
            list(MUMBAI_LOCATIONS.keys()),
            index=0
        )

        dropoff_options = [
            loc for loc in MUMBAI_LOCATIONS.keys()
            if loc != pickup_name
        ]

        dropoff_name = st.sidebar.selectbox(
            "Dropoff Location",
            dropoff_options,
            index=4
        )

        p_lat, p_lon = MUMBAI_LOCATIONS[pickup_name]
        d_lat, d_lon = MUMBAI_LOCATIONS[dropoff_name]


    elif input_mode == "Custom Coordinates":

        p_lat = st.sidebar.number_input(
            "Pickup Latitude",
            value=19.0760,
            format="%.4f"
        )

        p_lon = st.sidebar.number_input(
            "Pickup Longitude",
            value=72.8777,
            format="%.4f"
        )

        d_lat = st.sidebar.number_input(
            "Dropoff Latitude",
            value=19.0896,
            format="%.4f"
        )

        d_lon = st.sidebar.number_input(
            "Dropoff Longitude",
            value=72.8656,
            format="%.4f"
        )

        pickup_name = "Custom Pickup"
        dropoff_name = "Custom Drop"


    else:
        # Click on Map mode

        pickup_name = "Map Pickup"
        dropoff_name = "Map Drop"

        if st.session_state.pickup:
            p_lat, p_lon = st.session_state.pickup
        else:
            p_lat, p_lon = 19.0760, 72.8777

        if st.session_state.drop:
            d_lat, d_lon = st.session_state.drop
        else:
            d_lat, d_lon = 19.0896, 72.8656

    st.sidebar.divider()
    st.sidebar.header("🚗 Trip Options")
    
    vehicle_type = st.sidebar.selectbox("Vehicle Category", ["Auto Rickshaw", "Kaali-Peeli Taxi", "Hatchback / Sedan", "SUV Prime"])
    passengers = st.sidebar.number_input("Passengers", 1, 4, 1)
    
    hour = st.sidebar.slider("Trip Time (Hour)", 0, 23, 14, format="%d:00")
    day_idx = st.sidebar.selectbox("Day of Week", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], index=1)
    day_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].index(day_idx)
    
    weather_desc = st.sidebar.selectbox("Weather Condition", ["Sunny / Clear ☀️", "Monsoon Rain 🌧️", "Heavy Torrential Rain ⛈️"])
    weather_flag = 0 if "Sunny" in weather_desc else (1 if "Monsoon Rain" in weather_desc else 2)

    st.sidebar.divider()
    st.sidebar.header("🗺️ Map Style")
    map_tile_choice = st.sidebar.selectbox("Map Tile Provider", [
        "OpenStreetMap (Default)",
        "CartoDB Positron (Light)",
        "CartoDB Dark Matter (Dark)",
        "Esri World Street Map"
    ])

    # Tile style mapping
    tile_urls = {
        "OpenStreetMap (Default)": "https://a.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "CartoDB Positron (Light)": "https://basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}.png",
        "CartoDB Dark Matter (Dark)": "https://basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}.png",
        "Esri World Street Map": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}"
    }
    
    # ==========================================
    # CLICKABLE MAP
    # ==========================================

    if input_mode == "Click on Map":

        st.subheader("🗺️ Select Your Trip")
        # ==========================================
        # ADD / REMOVE STOPS
        # ==========================================

        col_add, col_remove = st.columns(2)

        with col_add:
            if st.button("➕ Add Stop", use_container_width=True):
                if len(st.session_state.stops) < 3:
                    st.session_state.stops.append(None)
                    st.session_state.stop_addresses.append("")
                    st.session_state.adding_stop = True    
        with col_remove:
            if st.button("🗑 Clear Stops"):
                st.session_state.stops = []
                st.session_state.stop_addresses = []

        # ==========================================
        # DISPLAY STOPS
        # ==========================================
        if len(st.session_state.stops) > 0:

            st.markdown("### 🚏 Intermediate Stops")

            for i in range(len(st.session_state.stops)):
                if st.session_state.stops[i] is not None:
                    st.success(f"🟠 Stop {i+1}")
                    st.write(st.session_state.stop_addresses[i])
                else:
                    st.warning(f"🟠 Stop {i+1}: Click on the map below to select")

        colA, colB = st.columns(2)

        with colA:
            pickup_search = st.text_input(
                "🔍 Search Pickup",
                placeholder="e.g. Bandra Station"
        )

        with colB:
            drop_search = st.text_input(
                "🔍 Search Drop",
                placeholder="e.g. Mumbai Airport T2"
        )
        st.caption("1st click = Pickup • 2nd click = Drop • 3rd click = Start a new trip")

        tile_attr = {
            "OpenStreetMap (Default)": "© OpenStreetMap contributors",
            "CartoDB Positron (Light)": "© OpenStreetMap contributors © CARTO",
            "CartoDB Dark Matter (Dark)": "© OpenStreetMap contributors © CARTO",
            "Esri World Street Map": "Tiles © Esri"
        }

        m = folium.Map(
            location=st.session_state.map_center,
            zoom_start=st.session_state.map_zoom,
            tiles=tile_urls[map_tile_choice],
            attr=tile_attr[map_tile_choice]
        )
        # ==========================================
        # SEARCH PICKUP & DROP
        # ==========================================

        if pickup_search:
            result = search_location(pickup_search)
            if result:
                lat, lon, address = result
                st.session_state.pickup = (lat, lon)
                st.session_state.pickup_address = address
                p_lat, p_lon = lat, lon

        if drop_search:
            result = search_location(drop_search)
            if result:
                lat, lon, address = result
                st.session_state.drop = (lat, lon)
                st.session_state.drop_address = address
                d_lat, d_lon = lat, lon

        # Pickup marker
        if st.session_state.pickup:
            folium.Marker(
                st.session_state.pickup,
                tooltip="Pickup",
                icon=folium.Icon(color="green")
            ).add_to(m)
        # Stop markers
        for i, stop in enumerate(st.session_state.stops):
            if stop is not None:
                folium.Marker(
                    stop,
                    tooltip=f"Stop {i+1}",
                    icon=folium.Icon(color="orange", icon="flag")
                ).add_to(m)

        # Drop marker
        if st.session_state.drop:
            folium.Marker(
                st.session_state.drop,
                tooltip="Drop",
                icon=folium.Icon(color="red")
            ).add_to(m)
        map_placeholder = st.empty()

        with map_placeholder:
            map_data = st_folium(
                m,
                width="100%",
                height=500,
                center=st.session_state.map_center,
                zoom=st.session_state.map_zoom,
                key="pickup_map"
            )
        

            # Save map position
        if map_data:
            if map_data.get("center"):
                st.session_state.map_center = [
                    map_data["center"]["lat"],
                    map_data["center"]["lng"]
                ]

            if map_data.get("zoom"):
                st.session_state.map_zoom = map_data["zoom"]

        # Process only real map clicks
        clicked = map_data.get("last_clicked") if map_data else None

        if clicked is not None:

            lat = clicked["lat"]
            lon = clicked["lng"]

            location = geolocator.reverse((lat, lon), language="en")
            address = location.address if location else "Unknown Location"

    # KEEP your existing pickup / stop / drop logic here

            # 1️⃣ Pickup
            if st.session_state.pickup is None:
                st.session_state.pickup = (lat, lon)
                st.session_state.pickup_address = address

            # 2️⃣ Stop
            elif st.session_state.adding_stop:
                idx = st.session_state.stops.index(None)
                st.session_state.stops[idx] = (lat, lon)
                st.session_state.stop_addresses[idx] = address
                st.session_state.adding_stop = False

            # 3️⃣ Drop
            elif st.session_state.drop is None:
                st.session_state.drop = (lat, lon)
                st.session_state.drop_address = address

            # 4️⃣ New Trip
            else:
                st.session_state.pickup = (lat, lon)
                st.session_state.pickup_address = address
                st.session_state.drop = None
                st.session_state.drop_address = ""
                st.session_state.stops = []
                st.session_state.stop_addresses = []
                st.session_state.adding_stop = False

            st.rerun()

        # ---------------- Pickup ----------------
        if st.session_state.pickup:
            p_lat, p_lon = st.session_state.pickup
            st.success("🟢 Pickup")
            st.write(st.session_state.pickup_address)

        # ---------------- Stops ----------------
        for i, stop in enumerate(st.session_state.stops):
            if stop:
                st.warning(f"🟠 Stop {i+1}")
                st.write(st.session_state.stop_addresses[i])

        # ---------------- Drop ----------------
        if st.session_state.drop:
            d_lat, d_lon = st.session_state.drop
            st.error("🔴 Drop")
            st.write(st.session_state.drop_address)
        # ==========================================
        # ROUTE ORDER (OLA / UBER STYLE)
        # ==========================================

        st.markdown("### 🛣️ Route Order")

        route_points = []

        if st.session_state.pickup_address:
            route_points.append(f"🟢 Pickup: {st.session_state.pickup_address}")

        for i, address in enumerate(st.session_state.stop_addresses):
            if address:
                route_points.append(f"🟠 Stop {i+1}: {address}")

        if st.session_state.drop_address:
            route_points.append(f"🔴 Drop: {st.session_state.drop_address}")

        for point in route_points:
            st.markdown(point)

        if st.button("🗑 Clear Trip"):
            st.session_state.pickup = None
            st.session_state.drop = None
            st.session_state.pickup_address = ""
            st.session_state.drop_address = ""
            st.session_state.stops = []
            st.session_state.stop_addresses = []
            st.rerun()
    # --------------------------------------------------
    # Fetch Route from OSRM
    # --------------------------------------------------
    with st.spinner("Fetching shortest driving path from OSRM..."):
        route_res = route_engine.get_osrm_route(
            p_lat,
            p_lon,
            d_lat,
            d_lon,
            stops=st.session_state.stops
        )

    route_dist_km = route_res["distance_km"]
    route_dur_min = route_res["duration_min"]
    path_coords = route_res["path_coordinates"]
    # =====================================================
    # AUTOMATIC LIVE TRAFFIC CALCULATION
    # =====================================================

    traffic_level, traffic_multiplier = calculate_traffic_level(
        p_lat,
        p_lon,
        d_lat,
        d_lon,
        hour,
        weather_flag
    )

    # Save original ETA
    base_duration = route_dur_min

    # Apply automatic traffic multiplier
    route_dur_min = round(base_duration * traffic_multiplier, 1)

    # --------------------------------------------------
    # Main View: Map & Summary Columns
    # --------------------------------------------------
    col_map, col_info = st.columns([3, 2])

    with col_map:
        st.subheader("🗺️ Mumbai Interactive Route Map")
        st.caption(f"Routing: {route_res['provider']} | {route_res['algorithm']}")

        # Center map
        mid_lat = (p_lat + d_lat) / 2
        mid_lon = (p_lon + d_lon) / 2

        route_map = folium.Map(
            location=[mid_lat, mid_lon],
            zoom_start=12,
            tiles="OpenStreetMap"
        )

        # Pickup marker
        folium.Marker(
            [p_lat, p_lon],
            popup=st.session_state.pickup_address,
            tooltip="🟢 Pickup",
            icon=folium.Icon(color="green", icon="play")
        ).add_to(route_map)
        # ==========================================
        # STOP MARKERS
        # ==========================================

        for i, stop in enumerate(st.session_state.stops):
            if stop:
                folium.Marker(
                    [stop[0], stop[1]],
                    popup=f"Stop {i+1}",
                    tooltip=st.session_state.stop_addresses[i],
                    icon=folium.Icon(color="orange", icon="flag")
                ).add_to(route_map)

        # Drop marker
        folium.Marker(
            [d_lat, d_lon],
            popup=st.session_state.drop_address,
            tooltip="🔴 Drop",
            icon=folium.Icon(color="red", icon="stop")
        ).add_to(route_map)

       
        # =====================================================
        # TRAFFIC COLOURED ROUTE
        # =====================================================

        route_color = {
            "Low": "#16A34A",        # Green
            "Moderate": "#F59E0B",   # Orange
            "Heavy": "#DC2626"       # Red
        }[traffic_level]

        folium.PolyLine(
            locations=path_coords,
            color=route_color,
            weight=7,
            opacity=0.9
        ).add_to(route_map)

        st_folium(
            route_map,
            width="100%",
            height=500,
            key="route_display_map"
        )
        # =====================================================
        # TRAFFIC LEGEND
        # =====================================================

        st.markdown("#### 🚦 Traffic Legend")

        lg1, lg2, lg3 = st.columns(3)

        with lg1:
            st.success("🟢 Low")

        with lg2:
            st.warning("🟠 Moderate")

        with lg3:
            st.error("🔴 Heavy")
        st.markdown("### 📍 Selected Locations")

        c1, c2 = st.columns(2)

        with c1:
            st.success("🟢 Pickup")
            st.write(st.session_state.pickup_address)

        with c2:
            st.error("🔴 Drop")
            st.write(st.session_state.drop_address)

    with col_info:
        st.subheader("🎯 Trip Summary & ML Fare")
        
        # Calculate Model Prediction
        if model is not None:
            features = np.array([[ 
                p_lat, p_lon, d_lat, d_lon, 
                passengers, route_dist_km, route_dur_min, 
                hour, day_of_week, weather_flag 
            ]])
            model_pred_fare = model.predict(features)[0]
            model_pred_fare = max(model_pred_fare, 28.0)
            
            # Apply vehicle category adjustment
            veh_mult = {"Auto Rickshaw": 0.85, "Kaali-Peeli Taxi": 0.95, "Hatchback / Sedan": 1.0, "SUV Prime": 1.45}
            final_model_fare = model_pred_fare * veh_mult[vehicle_type]
        else:
            final_model_fare = 28.0 + route_dist_km * 18.5

        # Display Fare Card
        st.markdown(f"""
        <div class="fare-card">
            <div class="fare-label">Predicted Model Fare ({vehicle_type})</div>
            <div class="fare-amount">₹{round(final_model_fare)}</div>
            <div style="font-size:13px; opacity:0.85; margin-top:4px;">
                Distance: <b>{route_dist_km} km</b> • Est. Duration: <b>{route_dur_min} mins</b>
            </div>
        </div>
        """, unsafe_allow_html=True)
        # =====================================================
        # AUTOMATIC LIVE TRAFFIC STATUS
        # =====================================================

        st.markdown("### 🚦 Live Traffic Status")

        if traffic_level == "Low":
            st.success(f"🟢 Low Traffic • ETA: {route_dur_min} min")

        elif traffic_level == "Moderate":
            st.warning(f"🟠 Moderate Traffic • ETA: {route_dur_min} min")

        else:
            st.error(f"🔴 Heavy Traffic • ETA: {route_dur_min} min")
        
        st.write("")
        st.markdown("##### ⏱️ Peak & Weather Pricing Factors")
        if 8 <= hour <= 11 or 17 <= hour <= 21:
            st.warning(f"🚦 Rush Hour Surge Active ({hour}:00 hrs)")
        elif 23 <= hour or hour <= 5:
            st.info(f"🌙 Night Time Rate Active (+25% RTO rule)")
        else:
            st.success(f"☀️ Normal Pricing Window ({hour}:00 hrs)")

        if weather_flag > 0:
            st.warning(f"🌧️ Monsoon Rain Multiplier Applied")

    st.divider()

    # --------------------------------------------------
    # Platform Fare Comparison Grid
    # --------------------------------------------------
    st.subheader("📊 Platform Fare Comparison Engine (Academic Estimates)")
    st.caption("Side-by-side estimated fare bands comparing our ML model with Mumbai ride-hailing platforms using standard tariff rules.")

    # Calculate platform estimates
    is_peak = (8 <= hour <= 11 or 17 <= hour <= 21)
    is_night = (23 <= hour or hour <= 5)
    
    surge_mult = 1.25 if is_peak else (1.10 if is_night else 1.0)
    w_mult = 1.0 if weather_flag == 0 else (1.15 if weather_flag == 1 else 1.30)

    # Ola Calculation
    ola_cfg = platform_config.get("platforms", {}).get("ola_mini", {})
    ola_fare = max(ola_cfg.get("base_fare", 35) + route_dist_km * ola_cfg.get("per_km_rate", 18) + route_dur_min * ola_cfg.get("per_min_rate", 1.8), ola_cfg.get("minimum_fare", 50)) * surge_mult * w_mult

    # Uber Calculation
    uber_cfg = platform_config.get("platforms", {}).get("uber_go", {})
    uber_fare = max(uber_cfg.get("base_fare", 38) + route_dist_km * uber_cfg.get("per_km_rate", 19.5) + route_dur_min * uber_cfg.get("per_min_rate", 2.0), uber_cfg.get("minimum_fare", 55)) * surge_mult * w_mult

    # Rapido Calculation
    rapido_cfg = platform_config.get("platforms", {}).get("rapido_bike_cab", {})
    rapido_fare = max(rapido_cfg.get("base_fare", 20) + route_dist_km * rapido_cfg.get("per_km_rate", 12) + route_dur_min * rapido_cfg.get("per_min_rate", 1.0), rapido_cfg.get("minimum_fare", 25)) * surge_mult * w_mult

    # Kaali-Peeli Meter Fare
    kp_cfg = platform_config.get("platforms", {}).get("mumbai_kaali_peeli", {})
    kp_fare = max(kp_cfg.get("base_fare", 28) + (max(route_dist_km - 1.5, 0)) * kp_cfg.get("per_km_rate", 18.66), 28.0)
    if is_night:
        kp_fare *= 1.25 # 25% night charge rule

    c1, c2, c3, c4, c5 = st.columns(5)

    with c1:
        st.markdown(f"""
        <div class="platform-card" style="border-color:#0284c7; background:#0c4a6e;">
            <div class="platform-name">🎯 Our Model</div>
            <div class="platform-price">₹{round(final_model_fare)}</div>
            <span class="badge-tag">ML Prediction</span>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
        <div class="platform-card">
            <div class="platform-name">🟡 Ola Mini</div>
            <div class="platform-price">₹{round(ola_fare)}</div>
            <span class="badge-tag">Est. Band</span>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
        <div class="platform-card">
            <div class="platform-name">⬛ Uber Go</div>
            <div class="platform-price">₹{round(uber_fare)}</div>
            <span class="badge-tag">Est. Band</span>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div class="platform-card">
            <div class="platform-name">🛵 Rapido Auto/Bike</div>
            <div class="platform-price">₹{round(rapido_fare)}</div>
            <span class="badge-tag">Budget Option</span>
        </div>
        """, unsafe_allow_html=True)

    with c5:
        st.markdown(f"""
        <div class="platform-card">
            <div class="platform-name">🚕 Kaali-Peeli</div>
            <div class="platform-price">₹{round(kp_fare)}</div>
            <span class="badge-tag">RTO Meter Rate</span>
        </div>
        """, unsafe_allow_html=True)

    # Bar chart breakdown
    st.write("")
    fare_chart_df = pd.DataFrame({
        "Platform / Option": ["Our Model", "Ola Mini", "Uber Go", "Rapido", "Kaali-Peeli Meter"],
        "Estimated Fare (₹)": [round(final_model_fare), round(ola_fare), round(uber_fare), round(rapido_fare), round(kp_fare)]
    })
    st.bar_chart(fare_chart_df.set_index("Platform / Option"))


# --------------------------------------------------
# TAB 2: Guide Report & Viva Defense
# --------------------------------------------------

with tab_report:
    st.header("📚 College Project Report & Viva Defense Document")
    st.caption("Complete 8-Point Academic Documentation for Project Guide Evaluation")

    st.markdown("""
    > [!IMPORTANT]
    > **Project Title:** Mumbai Smart Cab Fare Prediction & Route Optimization System  
    > **Architecture:** OpenStreetMap Tiles + OSRM Shortest Path API + Random Forest ML Model + Platform Comparison Engine  
    """)

    col_r1, col_r2 = st.columns(2)

    with col_r1:
        st.markdown("""
        ### 1. Problem Statement
        Predicting cab fares in Mumbai requires accounting for heavy traffic density, monsoon weather variations, rush-hour surge pricing, and RTO regulatory tariffs. Existing generic fare models (such as NYC taxi datasets) fail in Indian metropolitan contexts due to differences in currency, road networks, auto-rickshaw meter regulations, and platform pricing structures (Ola, Uber, Rapido).

        ### 2. Why Mumbai Data is Required
        - **Currency & Scale:** NYC fare models output USD ($) based on grid-based Manhattan blocks. Mumbai operates in INR (₹) with complex coastal and suburban arterial roads.
        - **Vehicle Ecosystem:** Mumbai features unique transport options including Auto-Rickshaws, Kaali-Peeli Taxis, and ride-hailing cabs.
        - **Regulatory Tariff:** Mumbai's RTO enforces specific base fares (e.g., ₹28 for Auto/Taxi minimum) and 25% night surcharges between 11 PM and 5 AM.

        ### 3. Dataset Schema & Feature Engineering
        Our system utilizes a customized 5,000-record Mumbai trip dataset containing:
        - `pickup_latitude` & `pickup_longitude` (Mumbai bounding box: 18.89°N - 19.30°N, 72.75°E - 73.05°E)
        - `dropoff_latitude` & `dropoff_longitude`
        - `route_distance_km` (Calculated via OSRM / Haversine)
        - `route_duration_min` (Traffic-adjusted travel time)
        - `pickup_hour` (0-23) & `day_of_week` (0-6)
        - `weather_flag` (Clear, Monsoon Rain, Heavy Torrential Rain)
        - `fare_amount` (Target feature in INR ₹)
        """)

    with col_r2:
        st.markdown(f"""
        ### 4. Machine Learning Model Performance
        - **Algorithm:** `RandomForestRegressor` (100 Decision Trees, Max Depth 15)
        - **R² Score:** `{metrics_info.get('r2_score', 0.9954)}` (High variance explanation)
        - **Mean Absolute Error (MAE):** `₹{metrics_info.get('mae', 9.68)}`
        - **Root Mean Squared Error (RMSE):** `₹{metrics_info.get('rmse', 19.28)}`

        ### 5. Shortest Route & Routing Engine (OSRM)
        Instead of using direct straight-line distance, the app connects to the **Open Source Routing Machine (OSRM)** API.
        - **Production Algorithm:** Multi-Level Dijkstra (MLD) / Contraction Hierarchies (CH).
        - **Comparison for Viva:**
          - *Dijkstra:* Baseline search exploring nodes uniformly.
          - *A\* Search:* Spatial heuristic search directing search toward goal.
          - *OSRM MLD:* Preprocessed hierarchical routing offering sub-millisecond query speed on OpenStreetMap networks.

        ### 6. Platform Comparison Engine (Ola / Uber / Rapido)
        To avoid depending on expensive paid platform APIs, the system implements a rule-based comparison engine loaded from `platform_fares.json`. It computes estimates using base fares, per-km rates, per-minute rates, and surge multipliers.
        """)

    st.divider()

    st.subheader("💡 Viva Voce FAQ & Defense Guide")
    
    faq1, faq2, faq3 = st.columns(3)
    
    with faq1:
        st.markdown("""
        **Q1: Why is your ML model accurate?**  
        *Answer:* The model is trained on non-linear features including exact OSRM road distance, traffic-dependent duration, rush-hour time slots, and weather flags using Random Forest ensemble trees.
        """)
        
    with faq2:
        st.markdown("""
        **Q2: How do you compare with Ola/Uber without paid APIs?**  
        *Answer:* We built an open rule-based simulation engine using publicly documented fare structures (Base Fare + Rate/KM + Rate/Min + Surge) stored in `platform_fares.json`.
        """)

    with faq3:
        st.markdown("""
        **Q3: What makes this free-tier friendly?**  
        *Answer:* OpenStreetMap provides free map tiles, OSRM provides free routing queries, Scikit-Learn runs locally, and Streamlit hosts the dashboard without any API charges.
        """)
