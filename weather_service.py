"""Automatic weather from Open-Meteo (free, no API key).

Open-Meteo gives hourly forecasts, so the same call works for "now" and for an
advance booking up to a week ahead. Weather is used only to pick the fare model's
`weather_flag` (0 clear / 1 rain / 2 heavy rain) and to show the user what was detected.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
REQUEST_TIMEOUT_S = 8
USER_AGENT = "mumbai-fare-estimator/2.0 (student project)"

# WMO weather interpretation codes -> short description
WMO_DESCRIPTIONS = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle", 56: "Freezing drizzle", 57: "Heavy freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light rain showers", 81: "Rain showers", 82: "Violent rain showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm with hail",
}
def icon_for(code) -> str:
    """Emoji for a WMO weather code."""
    try:
        c = int(code)
    except (TypeError, ValueError):
        return "🌡️"
    if c == 0:
        return "☀️"
    if c == 1:
        return "🌤️"
    if c == 2:
        return "⛅"
    if c == 3:
        return "☁️"
    if c in (45, 48):
        return "🌫️"
    if 51 <= c <= 57:
        return "🌦️"
    if 61 <= c <= 67 or 80 <= c <= 82:
        return "🌧️"
    if 71 <= c <= 77 or c in (85, 86):
        return "❄️"
    if c >= 95:
        return "⛈️"
    return "🌡️"


_RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 66, 80, 81}
_HEAVY_CODES = {65, 67, 82, 95, 96, 99}
RAIN_MM_PER_HOUR = 0.2
HEAVY_RAIN_MM_PER_HOUR = 7.5  # roughly the meteorological threshold for "heavy" rain


class WeatherError(Exception):
    """Raised when weather data cannot be obtained."""


def describe(code: int) -> str:
    return WMO_DESCRIPTIONS.get(int(code), f"Weather code {int(code)}")


def classify_weather(precipitation_mm: float, code: int) -> int:
    """Map hourly precipitation + WMO code to the model's weather_flag (0/1/2)."""
    if precipitation_mm >= HEAVY_RAIN_MM_PER_HOUR or int(code) in _HEAVY_CODES:
        return 2
    if precipitation_mm >= RAIN_MM_PER_HOUR or int(code) in _RAIN_CODES:
        return 1
    return 0


def _at(hourly: dict, name: str, idx: int):
    """Value of an hourly series at idx, or None if the series is missing/short."""
    series = hourly.get(name)
    return series[idx] if series and idx < len(series) else None


def _round(value, digits=1):
    return None if value is None else round(float(value), digits)


def _hour_label(time_key: str) -> str:
    dt = datetime.strptime(time_key, "%Y-%m-%dT%H:%M")
    return f"{dt.hour % 12 or 12} {'AM' if dt.hour < 12 else 'PM'}"


def fetch_weather(lat: float, lon: float, when: datetime,
                  session: Optional[requests.Session] = None) -> dict:
    """Weather at (lat, lon) for the hour containing `when` (IST). Raises WeatherError."""
    params = {
        "latitude": round(float(lat), 4),
        "longitude": round(float(lon), 4),
        "hourly": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,precipitation,weather_code",
        "timezone": "Asia/Kolkata",
        "forecast_days": 8,
    }
    getter = session.get if session else requests.get
    try:
        resp = getter(OPEN_METEO_URL, params=params, timeout=REQUEST_TIMEOUT_S,
                      headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        hourly = resp.json()["hourly"]
        key = when.strftime("%Y-%m-%dT%H:00")
        idx = hourly["time"].index(key)
        precip = hourly["precipitation"][idx]
        code = hourly["weather_code"][idx]
        temp = hourly["temperature_2m"][idx]
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
        raise WeatherError(f"Weather lookup failed: {exc}") from exc

    if code is None:
        raise WeatherError("Forecast has no data for that hour")
    precip = 0.0 if precip is None else float(precip)
    flag = classify_weather(precip, code)

    outlook = []  # this hour and the next five
    for j in range(idx, min(idx + 6, len(hourly["time"]))):
        code_j = _at(hourly, "weather_code", j)
        if code_j is None:
            continue
        outlook.append({
            "label": _hour_label(hourly["time"][j]),
            "temperature_c": _round(_at(hourly, "temperature_2m", j), 0),
            "precipitation_mm": _round(_at(hourly, "precipitation", j) or 0.0),
            "icon": icon_for(code_j),
        })

    return {
        "success": True,
        "source": "Open-Meteo",
        "flag": flag,
        "description": describe(code),
        "icon": icon_for(code),
        "weather_code": int(code),
        "precipitation_mm": round(precip, 1),
        "temperature_c": None if temp is None else round(float(temp), 1),
        "feels_like_c": _round(_at(hourly, "apparent_temperature", idx)),
        "humidity_pct": _round(_at(hourly, "relative_humidity_2m", idx), 0),
        "wind_kmh": _round(_at(hourly, "wind_speed_10m", idx), 0),
        "outlook": outlook,
        "forecast_for": key,
    }
