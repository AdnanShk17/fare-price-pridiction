"""FareCompass - compare cab fares across Mumbai (Streamlit web app)."""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import folium
import joblib
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import fare_logic as fl
import geo_utils
import poi_service
import route_engine
import trip_time as tm
import ui_components as ui
import weather_service
from branding import APP_NAME, APP_TAGLINE, CITY
from database import get_bookings, init_db, save_booking

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent
MAX_STOPS = 3
MAP_HEIGHT = 580
MUMBAI_CENTER = [19.0760, 72.8777]

st.set_page_config(
    page_title=f"{APP_NAME} | {APP_TAGLINE}",
    page_icon="🚕",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown(ui.css(), unsafe_allow_html=True)

# --------------------------------------------------------------------------
# Static options
# --------------------------------------------------------------------------
VEHICLES = {"🛺 Auto": "Auto Rickshaw", "🚕 Taxi": "Kaali-Peeli Taxi", "🚗 Sedan": "Hatchback / Sedan", "🚙 SUV": "SUV Prime"}
DEFAULT_VEHICLE = "🚗 Sedan"
WEATHER_CHOICES = [("☀️ Clear", 0), ("🌧️ Rain", 1), ("⛈️ Heavy rain", 2)]
PROVIDERS = {
    "ola_mini": ("🟡", "Ola"),
    "uber_go": ("⬛", "Uber"),
    "rapido_bike_cab": ("🛵", "Rapido"),
    "mumbai_kaali_peeli": ("🚕", "Kaali-Peeli Taxi"),
}
# OpenStreetMap's standard tiles need no key (fine for development / light use). For a production launch set
# MAP_TILE_URL / MAP_TILE_ATTR to a provider you have a licence or key for (MapTiler, Stadia, Mapbox, self-hosted...).
TILE_URL = os.environ.get("MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
TILE_ATTR = os.environ.get("MAP_TILE_ATTR", "© OpenStreetMap contributors")
# Softens the colourful OSM tiles so the map looks calmer next to the interface (applies inside the map frame).
MAP_STYLE = "<style>.leaflet-tile-pane{filter:grayscale(.45) saturate(.9) brightness(1.03);}</style>"
TRIP_COLUMNS = {
    "booking_time": "Saved on", "trip_time": "Trip time", "pickup": "Pickup", "dropoff": "Drop-off", "stops": "Stops",
    "vehicle_type": "Ride type", "distance_km": "Distance (km)", "duration_min": "Time (min)", "traffic_level": "Traffic",
    "weather": "Weather", "ml_fare": "Estimate (₹)", "ola_fare": "Ola (₹)", "uber_fare": "Uber (₹)",
    "rapido_fare": "Rapido (₹)", "kaali_peeli_fare": "Taxi (₹)",
}


# --------------------------------------------------------------------------
# Cached services
# --------------------------------------------------------------------------
@st.cache_resource
def load_fare_estimator():
    path = BASE_DIR / "mumbai_cab_fare_model.pkl"
    try:
        return joblib.load(path)
    except Exception as exc:  # missing / incompatible file -> use the rule-based formula
        logger.warning("Fare estimator file unavailable (%s); using the rule-based formula", exc)
        return None


@st.cache_data
def load_metrics() -> dict:
    path = BASE_DIR / "mumbai_model_metrics.json"
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


@st.cache_data(ttl=1800, show_spinner=False)
def _osrm_cached(points: tuple) -> dict:
    return route_engine.fetch_osrm_route(points)  # raises RouteError (never cached)


def get_route(points: list) -> dict:
    key = tuple((round(lat, 6), round(lon, 6)) for lat, lon in points)
    try:
        return _osrm_cached(key)
    except route_engine.RouteError as exc:
        return route_engine.fallback_route(points, str(exc))


@st.cache_data(ttl=3600, show_spinner=False)
def cached_search(query: str):
    return geo_utils.search_location(query)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_reverse(lat: float, lon: float) -> str:
    return geo_utils.reverse_geocode(lat, lon)


@st.cache_data(ttl=900, show_spinner=False)
def _weather_cached(lat: float, lon: float, hour_key: str) -> dict:
    return weather_service.fetch_weather(lat, lon, datetime.strptime(hour_key, "%Y-%m-%dT%H:00"))


def get_weather(lat: float, lon: float, when) -> dict:
    try:
        return _weather_cached(round(lat, 2), round(lon, 2), when.strftime("%Y-%m-%dT%H:00"))
    except weather_service.WeatherError as exc:
        return {"success": False, "error": str(exc)}


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _poi_cached(path_key: tuple, radius_m: int, categories: tuple) -> list:
    return poi_service.fetch_pois(list(path_key), radius_m, categories)  # raises PoiError (never cached)


def get_pois(path: list, radius_m: int, categories: list):
    key = tuple((round(a, 5), round(b, 5)) for a, b in poi_service.simplify_path(path))
    try:
        return _poi_cached(key, int(radius_m), tuple(categories)), None
    except poi_service.PoiError as exc:
        return [], str(exc)


try:
    platform_config = fl.load_config()
except (OSError, ValueError) as exc:
    st.error(f"The service is temporarily unavailable (configuration error: {exc}).")
    st.stop()

fare_estimator = load_fare_estimator()
init_db()


# --------------------------------------------------------------------------
# Session state + callbacks
# --------------------------------------------------------------------------
def init_state() -> None:
    sched_date, sched_time = tm.default_schedule()
    defaults = {
        "sched_date": sched_date, "sched_time": sched_time,
        "session_id": uuid.uuid4().hex,
        "pickup": None, "drop": None, "pickup_address": "", "drop_address": "",
        "stops": [], "stop_addresses": [], "adding_stop": False,
        "last_click": None, "search_msg": None, "trip_saved": False,
        "map_center": list(MUMBAI_CENTER), "map_zoom": 11,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


def clear_stops() -> None:
    st.session_state.stops = []
    st.session_state.stop_addresses = []
    st.session_state.adding_stop = False


def clear_trip() -> None:
    # last_click is deliberately kept: the map component keeps re-sending its last click,
    # and forgetting it here would re-apply that stale click as a new pickup.
    ss = st.session_state
    ss.pickup = ss.drop = None
    ss.pickup_address = ss.drop_address = ""
    ss.search_msg = None
    clear_stops()


def clear_point(kind: str) -> None:
    ss = st.session_state
    ss[kind] = None
    ss[f"{kind}_address"] = ""


def remove_stop(index: int) -> None:
    ss = st.session_state
    if 0 <= index < len(ss.stops):
        ss.stops.pop(index)
        ss.stop_addresses.pop(index)
    ss.adding_stop = None in ss.stops


def add_stop() -> None:
    ss = st.session_state
    if len(ss.stops) < MAX_STOPS and None not in ss.stops:
        ss.stops.append(None)
        ss.stop_addresses.append("")
    ss.adding_stop = None in ss.stops


def add_poi_as_stop(lat: float, lon: float, name: str) -> None:
    ss = st.session_state
    if None in ss.stops:
        idx = ss.stops.index(None)
        ss.stops[idx], ss.stop_addresses[idx] = (lat, lon), name
    elif len(ss.stops) < MAX_STOPS:
        ss.stops.append((lat, lon))
        ss.stop_addresses.append(name)
    ss.adding_stop = None in ss.stops


def set_from_search(kind: str) -> None:
    ss = st.session_state
    query = (ss.get(f"{kind}_search") or "").strip()
    result = cached_search(query) if query else None
    if not result:
        ss.search_msg = f"We couldn't find “{query}” in {CITY}. Try a nearby landmark or area name." if query \
            else "Type a place name first."
        return
    lat, lon, address = result
    ss[kind], ss[f"{kind}_address"] = (lat, lon), address
    ss.map_center, ss.map_zoom = [lat, lon], 14
    ss.search_msg = None


def handle_map_click(map_data) -> bool:
    """Apply a NEW map click to the next empty slot (pickup -> stop -> drop). True if state changed."""
    clicked = map_data.get("last_clicked") if map_data else None
    if not clicked:
        return False
    lat, lon = float(clicked["lat"]), float(clicked["lng"])
    key = (round(lat, 6), round(lon, 6))
    ss = st.session_state
    if ss.last_click == key:  # the map component re-sends its last click on every rerun
        return False
    ss.last_click = key

    if ss.adding_stop and None in ss.stops and ss.pickup is not None:
        slot = "stop"
    elif ss.pickup is None:
        slot = "pickup"
    elif ss.drop is None:
        slot = "drop"
    else:
        return False  # route is complete - use Reset / the ✕ buttons to change it
    address = cached_reverse(round(lat, 5), round(lon, 5))
    if slot == "stop":
        idx = ss.stops.index(None)
        ss.stops[idx], ss.stop_addresses[idx] = (lat, lon), address
        ss.adding_stop = None in ss.stops
    else:
        ss[slot], ss[f"{slot}_address"] = (lat, lon), address
    return True


# --------------------------------------------------------------------------
# Planner (left column)
# --------------------------------------------------------------------------
def render_planner() -> dict:
    ss = st.session_state
    with st.container(border=True):
        st.markdown(ui.section_title("Plan your ride", "Tap the map or search to set your route"), unsafe_allow_html=True)

        if ss.pickup is None:
            banner = ui.step_banner("Tap the map to set your pickup point", "1")
        elif ss.adding_stop and None in ss.stops:
            banner = ui.step_banner(f"Tap the map to place stop {ss.stops.index(None) + 1}", "•")
        elif ss.drop is None:
            banner = ui.step_banner("Now tap the map to set your drop-off point", "2")
        else:
            banner = ui.step_banner("Route ready - compare fares below", done=True)
        st.markdown(banner, unsafe_allow_html=True)

        # ---- pickup
        st.markdown(ui.label("Pickup"), unsafe_allow_html=True)
        c1, c2 = st.columns([4, 1])
        c1.text_input("Pickup location", key="pickup_search", placeholder="Search a place in Mumbai",
                      label_visibility="collapsed")
        c2.button("Search", key="pickup_go", on_click=set_from_search, args=("pickup",))
        if ss.pickup:
            c1, c2 = st.columns([6, 1])
            c1.markdown(ui.location_chip("#16A34A", "Pickup", ss.pickup_address), unsafe_allow_html=True)
            c2.button("✕", key="clear_pickup", on_click=clear_point, args=("pickup",), help="Remove pickup")

        # ---- stops
        for i, (stop, address) in enumerate(zip(ss.stops, ss.stop_addresses)):
            c1, c2 = st.columns([6, 1])
            c1.markdown(ui.location_chip("#F59E0B", f"Stop {i + 1}", address if stop else "Tap the map to place this stop"),
                        unsafe_allow_html=True)
            c2.button("✕", key=f"remove_stop_{i}", on_click=remove_stop, args=(i,), help="Remove stop")
        b1, b2 = st.columns(2)
        b1.button("＋ Add a stop", key="add_stop", on_click=add_stop,
                  disabled=ss.pickup is None or (len(ss.stops) >= MAX_STOPS and None not in ss.stops))
        if ss.stops:
            b2.button("Clear stops", key="clear_stops", on_click=clear_stops)

        # ---- drop-off
        st.markdown(ui.label("Drop-off"), unsafe_allow_html=True)
        c1, c2 = st.columns([4, 1])
        c1.text_input("Drop-off location", key="drop_search", placeholder="Search a place in Mumbai",
                      label_visibility="collapsed")
        c2.button("Search", key="drop_go", on_click=set_from_search, args=("drop",))
        if ss.drop:
            c1, c2 = st.columns([6, 1])
            c1.markdown(ui.location_chip("#DC2626", "Drop-off", ss.drop_address), unsafe_allow_html=True)
            c2.button("✕", key="clear_drop", on_click=clear_point, args=("drop",), help="Remove drop-off")
        if ss.search_msg:
            st.warning(ss.search_msg)

        # ---- when
        st.markdown(ui.label("When"), unsafe_allow_html=True)
        when_choice = st.radio("When", ["Leave now", "Schedule for later"], horizontal=True, label_visibility="collapsed")
        now = tm.now_ist()
        if when_choice == "Leave now":
            trip_dt, time_msg = now, None
        else:
            if ss.sched_date < now.date():  # page left open overnight
                ss.sched_date, ss.sched_time = tm.default_schedule(now)
            d1, d2 = st.columns(2)
            d1.date_input("Date", min_value=now.date(), max_value=now.date() + timedelta(days=tm.MAX_ADVANCE_DAYS),
                          key="sched_date")
            d2.time_input("Time", key="sched_time", step=900)
            trip_dt, time_msg = tm.resolve_trip_datetime("scheduled", ss.sched_date, ss.sched_time, now)
        if time_msg:
            st.warning(time_msg)

        # ---- ride type
        st.markdown(ui.label("Ride type"), unsafe_allow_html=True)
        vehicle_label = st.radio("Ride type", list(VEHICLES), index=list(VEHICLES).index(DEFAULT_VEHICLE),
                                 horizontal=True, label_visibility="collapsed")

        with st.expander("⚙️ Preferences"):
            manual_weather = st.toggle("Set weather manually", key="manual_weather",
                                       help="By default the weather is detected automatically for your trip time.")
            manual_choice = None
            if manual_weather:
                manual_choice = st.selectbox("Weather", [w[0] for w in WEATHER_CHOICES], key="manual_weather_choice")
            show_suggestions = st.checkbox("Show food, shopping & sights along the route", value=True, key="show_suggestions")
            categories = st.multiselect("What to look for", list(poi_service.CATEGORY_LABELS),
                                        default=list(poi_service.CATEGORY_LABELS),
                                        format_func=lambda c: poi_service.CATEGORY_LABELS[c])
            radius = st.slider("Distance from route (m)", 200, 1000, 500, step=100)

        st.button("Reset trip", key="reset_trip", on_click=clear_trip)

    return {
        "trip_dt": trip_dt, "scheduled": when_choice != "Leave now",
        "vehicle_label": vehicle_label, "vehicle_type": VEHICLES[vehicle_label],
        "manual_weather": manual_weather, "manual_choice": manual_choice,
        "show_suggestions": show_suggestions, "categories": categories, "radius": radius,
    }


def resolve_weather(cfg: dict) -> dict:
    """Detected (or manually chosen) weather for the trip hour."""
    if not cfg["manual_weather"]:
        lat, lon = st.session_state.pickup or MUMBAI_CENTER
        info = get_weather(lat, lon, cfg["trip_dt"])
        if info["success"]:
            return {"flag": info["flag"], "desc": info["description"], "icon": info["icon"], "info": info,
                    "auto": True, "failed": False}
        failed = True
    else:
        failed = False
    label = cfg["manual_choice"] or WEATHER_CHOICES[0][0]
    icon, flag = next((w[0].split(" ")[0], w[1]) for w in WEATHER_CHOICES if w[0] == label)
    return {"flag": flag, "desc": label.split(" ", 1)[1], "icon": icon, "info": None, "auto": False, "failed": failed}


# --------------------------------------------------------------------------
# Quote + map + results
# --------------------------------------------------------------------------
def compute_quote(route_res: dict, cfg: dict, weather: dict) -> dict:
    (p_lat, p_lon), (d_lat, d_lon) = st.session_state.pickup, st.session_state.drop
    hour, flag = cfg["trip_dt"].hour, weather["flag"]
    traffic_level, traffic_mult = fl.traffic_level(p_lat, p_lon, d_lat, d_lon, hour, flag)
    dist = route_res["distance_km"]
    duration = round(route_res["duration_min"] * traffic_mult, 1)

    base_fares = fl.all_platform_fares(platform_config, dist, duration, hour, flag)
    fares = fl.vehicle_fares(platform_config, dist, duration, hour, flag, cfg["vehicle_type"])
    base_estimate = (fare_estimator.predict_one(dist, duration, hour, flag) if fare_estimator is not None
                     else fl.fair_price(base_fares))
    return {
        "distance_km": dist, "duration_min": duration, "traffic": traffic_level, "fares": fares,
        "estimate": round(base_estimate * fl.VEHICLE_MULTIPLIERS[cfg["vehicle_type"]]),
        "arrival": cfg["trip_dt"] + timedelta(minutes=duration),
    }


def base_map(location, zoom) -> "folium.Map":
    m = folium.Map(location=location, zoom_start=zoom, tiles=TILE_URL, attr=TILE_ATTR, control_scale=True)
    m.get_root().header.add_child(folium.Element(MAP_STYLE))
    return m


def render_map(route_res, ranked: dict, stop_pts: list, stop_labels: list) -> None:
    ss = st.session_state
    if route_res is None:  # ---- selection phase
        m = base_map(ss.map_center, ss.map_zoom)
        if ss.pickup:
            folium.Marker(ss.pickup, tooltip="Pickup", icon=folium.Icon(color="green", icon="play")).add_to(m)
        for i, stop in enumerate(ss.stops):
            if stop is not None:
                folium.Marker(stop, tooltip=f"Stop {i + 1}", icon=folium.Icon(color="orange", icon="flag")).add_to(m)
        if ss.drop:
            folium.Marker(ss.drop, tooltip="Drop-off", icon=folium.Icon(color="red", icon="stop")).add_to(m)
        data = st_folium(m, width="100%", height=MAP_HEIGHT, center=ss.map_center, zoom=ss.map_zoom,
                         key="map_select", returned_objects=["last_clicked", "center", "zoom"])
        if data:
            if data.get("center"):
                ss.map_center = [data["center"]["lat"], data["center"]["lng"]]
            if data.get("zoom"):
                ss.map_zoom = data["zoom"]
    else:  # ---- route phase
        (p_lat, p_lon), (d_lat, d_lon) = ss.pickup, ss.drop
        m = base_map([(p_lat + d_lat) / 2, (p_lon + d_lon) / 2], 12)
        path = route_res["path_coordinates"]
        dashed = None if route_res["success"] else "8"
        folium.PolyLine(path, color="#FFFFFF", weight=10, opacity=0.9).add_to(m)
        folium.PolyLine(path, color="#1D4ED8", weight=5, opacity=0.95, dash_array=dashed).add_to(m)
        folium.Marker([p_lat, p_lon], tooltip=f"Pickup: {ss.pickup_address}"[:120],
                      icon=folium.Icon(color="green", icon="play")).add_to(m)
        for i, (stop, label) in enumerate(zip(stop_pts, stop_labels)):
            folium.Marker(list(stop), tooltip=f"Stop {i + 1}: {label}"[:120],
                          icon=folium.Icon(color="orange", icon="flag")).add_to(m)
        folium.Marker([d_lat, d_lon], tooltip=f"Drop-off: {ss.drop_address}"[:120],
                      icon=folium.Icon(color="red", icon="stop")).add_to(m)
        for cat, places in ranked.items():
            color, glyph = poi_service.CATEGORY_MARKERS[cat]
            for p in places:
                folium.Marker([p["lat"], p["lon"]], tooltip=f"{poi_service.CATEGORY_LABELS[cat].split(' ')[0]} {p['name']}",
                              popup=f"{p['name']} · about {p['minutes_into_trip']} min into the trip",
                              icon=folium.Icon(color=color, icon=glyph, prefix="glyphicon")).add_to(m)
        m.fit_bounds([[min(c[0] for c in path), min(c[1] for c in path)],
                      [max(c[0] for c in path), max(c[1] for c in path)]])
        data = st_folium(m, width="100%", height=MAP_HEIGHT, key="map_route", returned_objects=["last_clicked"])

    if handle_map_click(data):
        st.rerun()
    st.caption("Tip: pinch or scroll to zoom. Tap the map to place your next point.")


def pricing_period(hour: int):
    if fl.is_peak_hour(hour):
        return "Rush-hour rates", "Higher demand period"
    if fl.is_night_hour(hour):
        return "Night rates", "Night surcharge may apply"
    return "Standard rates", "Regular demand"


def render_poi(p: dict) -> None:
    c1, c2 = st.columns([6, 1])
    meta = (f"About {p['minutes_into_trip']} min into the trip (≈ {p['pass_time']:%I:%M %p}) · "
            f"{p['off_route_m']} m from your route")
    if p["opening_hours"]:
        meta += f" · Hours: {p['opening_hours']}"
    c1.markdown(ui.poi_row(p["name"], p["cuisine"], meta), unsafe_allow_html=True)
    stops_full = None not in st.session_state.stops and len(st.session_state.stops) >= MAX_STOPS
    c2.button("＋ Stop", key=f"stop_{p['category']}_{p['id']}", on_click=add_poi_as_stop,
              args=(p["lat"], p["lon"], p["name"]), disabled=stops_full, help="Add this place as a stop on your route")


def render_suggestions(cfg: dict, ranked: dict, poi_error, route_res: dict) -> None:
    st.markdown(ui.section_title("Along your route", "Food, shopping and sights near your journey"), unsafe_allow_html=True)
    if not cfg["show_suggestions"]:
        st.caption("Suggestions are switched off. Turn them on under Preferences.")
        return
    if not cfg["categories"]:
        st.info("Choose at least one category under Preferences.")
        return
    if not route_res["success"]:
        st.info("Suggestions need a live driving route, which isn't available right now.")
        return
    if poi_error:
        st.warning("We couldn't load nearby places right now. Please try again in a minute.")
        return
    emoji, headline, order = poi_service.meal_context(cfg["trip_dt"].hour)
    categories = [c for c in order if ranked.get(c)]
    if not categories:
        st.info(f"No named places found within {cfg['radius']} m of this route. Try a larger distance under Preferences.")
        return
    st.info(f"{emoji} **{headline}** — here is what you will pass on the way.")
    for tab, cat in zip(st.tabs([poi_service.CATEGORY_LABELS[c] for c in categories]), categories):
        with tab:
            for p in ranked[cat]:
                render_poi(p)
    st.caption("Places are listed from OpenStreetMap, which has no ratings or crowd data. They are ordered by how "
               "well-known and how close they are to your route. Opening hours may be missing or out of date.")


def render_results(q: dict, cfg: dict, weather: dict, route_res: dict, ranked: dict, poi_error) -> None:
    ss = st.session_state
    trip_dt = cfg["trip_dt"]
    st.markdown(ui.section_title("Ride options", f"Estimated fares for {cfg['vehicle_label'].split(' ', 1)[1]} · "
                                                  f"{tm.format_trip_time(trip_dt)}"), unsafe_allow_html=True)
    available = {k: v for k, v in q["fares"].items() if v is not None}
    cheapest = min(available, key=available.get) if available else None
    cards = [ui.ride_card("🧭", f"{APP_NAME} Estimate", "Typical market fare", q["estimate"], "Benchmark", estimate=True)]
    for key in fl.PLATFORM_KEYS:
        icon, name = PROVIDERS[key]
        price = q["fares"][key]
        if price is None:
            cards.append(ui.ride_card(icon, name, cfg["vehicle_label"].split(" ", 1)[1], None,
                                      f"Not offered for {cfg['vehicle_label'].split(' ', 1)[1]}"))
        else:
            cards.append(ui.ride_card(icon, name, cfg["vehicle_label"].split(" ", 1)[1], price,
                                      "Lowest fare" if key == cheapest else "Estimated fare", best=key == cheapest))
    if cheapest:
        saving = max(available.values()) - available[cheapest]
        st.markdown(ui.savings_banner(PROVIDERS[cheapest][1], available[cheapest], saving), unsafe_allow_html=True)
    st.markdown(ui.rides_grid(cards), unsafe_allow_html=True)

    s1, s2 = st.columns([1, 3])
    if s1.button("💾 Save this trip", type="primary", key="save_trip"):
        stop_labels = [a for s, a in zip(ss.stops, ss.stop_addresses) if s is not None]
        info = weather["info"]
        weather_label = fl.WEATHER_LABELS[weather["flag"]]
        if info:
            weather_label += f" ({info['description']}, {info['precipitation_mm']} mm/h)"
        r = lambda v: None if v is None else round(v)  # noqa: E731
        save_booking(
            pickup=ss.pickup_address, dropoff=ss.drop_address, stops=", ".join(stop_labels),
            distance=q["distance_km"], duration=q["duration_min"], traffic=q["traffic"], weather=weather_label,
            ola=r(q["fares"]["ola_mini"]), uber=r(q["fares"]["uber_go"]),
            rapido=r(q["fares"]["rapido_bike_cab"]), kp=r(q["fares"]["mumbai_kaali_peeli"]),
            ml=q["estimate"], vehicle_type=cfg["vehicle_type"], session_id=ss.session_id,
            trip_time=trip_dt.isoformat(timespec="minutes"),
        )
        s2.success("Trip saved - find it under **My trips**.")

    # ---- trip summary
    st.markdown(ui.section_title("Trip summary"), unsafe_allow_html=True)
    period, period_sub = pricing_period(trip_dt.hour)
    st.markdown(ui.tiles_row([
        ui.tile("📏", "Distance", f"{q['distance_km']:g} km", "Driving route"),
        ui.tile("⏱️", "Travel time", f"{round(q['duration_min'])} min", f"Arrive by {q['arrival']:%I:%M %p}"),
        ui.tile("🚦", "Traffic", q["traffic"], "Estimated for your time"),
        ui.tile("🏷️", "Pricing", period, period_sub),
    ]), unsafe_allow_html=True)

    # ---- conditions
    st.markdown(ui.section_title("Weather & conditions", "Used to estimate fares for your trip time"), unsafe_allow_html=True)
    info = weather["info"]
    when_text = "Scheduled trip" if cfg["scheduled"] else "Leaving now"
    tiles = [ui.tile("🗓️", "Trip time", f"{trip_dt:%I:%M %p}", f"{trip_dt:%a %d %b} · {when_text}")]
    if info:
        temp = "–" if info["temperature_c"] is None else f"{info['temperature_c']:.0f}°C"
        feels = f"Feels like {info['feels_like_c']:.0f}°C" if info["feels_like_c"] is not None else ""
        tiles.append(ui.tile(info["icon"], "Weather", f"{temp} · {info['description']}", feels))
        tiles.append(ui.tile("🌧️", "Rain", f"{info['precipitation_mm']:g} mm/h",
                             "Rain pricing applies" if weather["flag"] else "No rain expected"))
        wind = "–" if info["wind_kmh"] is None else f"{info['wind_kmh']:.0f} km/h"
        humidity = f"Humidity {info['humidity_pct']:.0f}%" if info["humidity_pct"] is not None else ""
        tiles.append(ui.tile("💨", "Wind", wind, humidity))
    else:
        tiles.append(ui.tile(weather["icon"], "Weather", weather["desc"], "Set manually"))
    st.markdown(ui.tiles_row(tiles), unsafe_allow_html=True)
    if weather["failed"]:
        st.warning("We couldn't fetch the live weather, so we used clear-weather pricing. "
                   "You can set the weather under Preferences.")
    if info and info.get("outlook"):
        st.markdown(ui.label("Next few hours"), unsafe_allow_html=True)
        st.markdown(ui.outlook_strip(info["outlook"]), unsafe_allow_html=True)

    st.divider()
    render_suggestions(cfg, ranked, poi_error, route_res)


def render_trips() -> None:
    st.markdown(ui.section_title("My trips", "Trips you saved in this session"), unsafe_allow_html=True)
    trips = get_bookings(session_id=st.session_state.session_id)
    if trips.empty:
        st.info("You haven't saved any trips yet. Plan a ride and choose **Save this trip**.")
        return
    shown = trips[[c for c in TRIP_COLUMNS if c in trips.columns]].rename(columns=TRIP_COLUMNS)
    st.dataframe(shown, hide_index=True)
    st.download_button("⬇️ Download trips (CSV)", shown.to_csv(index=False).encode("utf-8"),
                       file_name="my_trips.csv", mime="text/csv")


def render_performance() -> None:
    m = load_metrics()
    st.markdown(ui.section_title("Fare estimator performance",
                                 "How closely the estimator reproduces fares on trips it has never seen"),
                unsafe_allow_html=True)
    if not m:
        st.info("Performance data isn't available yet. Run `python train_mumbai_model.py` to generate it.")
        return

    st.markdown(ui.tiles_row([
        ui.tile("🎯", "R² score", f"{m['r2_score']:.4f}", "1.0 = perfect fit"),
        ui.tile("💰", "Average error (MAE)", f"₹{m['mae']:g}", f"{m.get('mape_pct', '–')}% of the fare"),
        ui.tile("📉", "RMSE", f"₹{m['rmse']:g}", "Penalises large misses"),
        ui.tile("🗂️", "Trips analysed", f"{m['dataset_records']:,}", "Simulated Mumbai trips"),
    ]), unsafe_allow_html=True)
    st.info("**How to read this:** scores are measured on "
            f"{m.get('data_source', 'simulated')} trips the estimator was not trained on "
            f"({m.get('evaluation', 'held-out routes')}). They show how well it reproduces the fare rules, "
            "not how close it is to real receipts.")

    c1, c2 = st.columns(2)
    plot, importance = BASE_DIR / "actual_vs_predicted.png", BASE_DIR / "feature_importance.png"
    with c1:
        st.markdown(ui.section_title("Actual vs predicted fare", "Points on the dashed line are perfect predictions"),
                    unsafe_allow_html=True)
        if plot.exists():
            st.image(str(plot))
        else:
            st.warning("Graph not found. Run `python train_mumbai_model.py`.")
    with c2:
        st.markdown(ui.section_title("What adjusts the fare", "Importance of each input in adjusting the base distance-and-time fare (rain, rush hour, night…)"),
                    unsafe_allow_html=True)
        if importance.exists():
            st.image(str(importance))
        else:
            st.warning("Graph not found. Run `python train_mumbai_model.py`.")

    st.markdown(ui.section_title("Details"), unsafe_allow_html=True)
    d1, d2 = st.columns(2)
    with d1:
        lin = m.get("linear_baseline")
        rows = [("Estimator", m.get("model_name", "–")), ("Trees / max depth", f"{m.get('n_estimators', '–')} / {m.get('max_depth', '–')}"),
                ("Inputs", ", ".join(m.get("features", []))),
                ("Cross-validated error", f"₹{m.get('cv_mae_mean', '–')} ± {m.get('cv_mae_std', '–')}"),
                ("Last trained", m.get("trained_on", "–"))]
        if lin:
            rows.append(("Simple baseline (distance + time only)", f"MAE ₹{lin['mae']} · R² {lin['r2_score']}"))
        st.dataframe(pd.DataFrame(rows, columns=["Item", "Value"]), hide_index=True)
    with d2:
        bands = m.get("mae_by_distance_band", {})
        if bands:
            table = pd.DataFrame([{"Trip distance": k, "Average error (₹)": v["mae"], "Error (% of fare)": v["mape_pct"],
                                   "R²": v["r2_score"]} for k, v in bands.items()])
            st.dataframe(table, hide_index=True)


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------
nav_slot = st.empty()
tab_plan, tab_trips, tab_perf = st.tabs(["🚖 Plan a ride", "🧾 My trips", "📊 Performance"])

with tab_plan:
    left, right = st.columns([5, 7], gap="large")
    with left:
        cfg = render_planner()
    weather = resolve_weather(cfg)

    ss = st.session_state
    stop_pts = [s for s in ss.stops if s is not None]
    stop_labels = [a for s, a in zip(ss.stops, ss.stop_addresses) if s is not None]
    ready = ss.pickup is not None and ss.drop is not None
    too_close = ready and not stop_pts and fl.haversine_km(*ss.pickup, *ss.drop) < 0.05

    route_res, ranked, poi_error, raw_places = None, {}, None, []
    with right:
        if ready and not too_close:
            with st.spinner("Finding the best route…"):
                route_res = get_route(route_engine.build_points(ss.pickup, ss.drop, stop_pts))
            if route_res["warning"]:
                st.warning("Live routing is unavailable, so distance and time are approximate.")
            if cfg["show_suggestions"] and cfg["categories"] and route_res["success"]:
                with st.spinner("Looking for places along your route…"):
                    raw_places, poi_error = get_pois(route_res["path_coordinates"], cfg["radius"], cfg["categories"])
        if raw_places and route_res is not None and not poi_error:
            ranked = poi_service.rank_pois(raw_places, route_res["path_coordinates"],
                                           route_res["duration_min"], cfg["trip_dt"], per_category=5,
                                           max_off_route_m=cfg["radius"])
        render_map(route_res, ranked, stop_pts, stop_labels)

    if too_close:
        st.warning("Pickup and drop-off are the same place. Please choose two different locations.")
    elif route_res is not None:
        quote = compute_quote(route_res, cfg, weather)
        st.divider()
        render_results(quote, cfg, weather, route_res, ranked, poi_error)
    else:
        st.markdown(ui.section_title("How it works"), unsafe_allow_html=True)
        st.markdown(ui.how_it_works(), unsafe_allow_html=True)

with tab_trips:
    render_trips()

with tab_perf:
    render_performance()

chips = [f"📍 {CITY}", f"🕒 {tm.format_trip_time(cfg['trip_dt'])}"]
winfo = weather["info"]
chips.append(f"{weather['icon']} " + (f"{winfo['temperature_c']:.0f}°C · {weather['desc']}"
                                     if winfo and winfo["temperature_c"] is not None else weather["desc"]))
nav_slot.markdown(ui.navbar(chips), unsafe_allow_html=True)
st.markdown(ui.footer(), unsafe_allow_html=True)
