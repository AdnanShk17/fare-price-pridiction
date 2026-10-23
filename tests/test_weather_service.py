import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

import weather_service as ws  # noqa: E402

PAYLOAD = {"hourly": {
    "time": ["2026-10-09T15:00", "2026-10-09T16:00", "2026-10-09T17:00", "2026-10-09T18:00"],
    "temperature_2m": [31.2, 30.4, 28.0, None],
    "precipitation": [0.0, 1.4, 12.0, None],
    "weather_code": [1, 61, 65, 3],
}}


def _session(payload=None, exc=None):
    s = mock.Mock()
    if exc:
        s.get.side_effect = exc
    else:
        r = mock.Mock()
        r.json.return_value = payload
        r.raise_for_status.return_value = None
        s.get.return_value = r
    return s


class WeatherTests(unittest.TestCase):
    def test_classification(self):
        self.assertEqual(ws.classify_weather(0.0, 0), 0)
        self.assertEqual(ws.classify_weather(0.0, 3), 0)        # overcast is not rain
        self.assertEqual(ws.classify_weather(0.3, 3), 1)        # measurable rain
        self.assertEqual(ws.classify_weather(0.0, 61), 1)       # rain code
        self.assertEqual(ws.classify_weather(8.0, 61), 2)       # heavy by intensity
        self.assertEqual(ws.classify_weather(0.0, 95), 2)       # thunderstorm

    def test_reads_the_requested_hour(self):
        r = ws.fetch_weather(19.07, 72.87, datetime(2026, 10, 9, 16, 50), _session(PAYLOAD))
        self.assertEqual((r["flag"], r["description"], r["precipitation_mm"], r["temperature_c"]),
                         (1, "Light rain", 1.4, 30.4))
        r = ws.fetch_weather(19.07, 72.87, datetime(2026, 10, 9, 17, 5), _session(PAYLOAD))
        self.assertEqual(r["flag"], 2)

    def test_full_conditions_icons_and_outlook(self):
        full = {"hourly": {
            "time": ["2026-10-09T16:00", "2026-10-09T17:00", "2026-10-09T18:00"],
            "temperature_2m": [30.4, 28.0, 27.2], "apparent_temperature": [34.1, 31.0, 30.0],
            "relative_humidity_2m": [78, 85, 88], "wind_speed_10m": [14.2, 18.9, 20.0],
            "precipitation": [1.4, 12.0, 0.0], "weather_code": [61, 65, 3],
        }}
        r = ws.fetch_weather(19.07, 72.87, datetime(2026, 10, 9, 16, 10), _session(full))
        self.assertEqual((r["feels_like_c"], r["humidity_pct"], r["wind_kmh"], r["icon"]), (34.1, 78.0, 14.0, "🌧️"))
        self.assertEqual([o["label"] for o in r["outlook"]], ["4 PM", "5 PM", "6 PM"])
        self.assertEqual(r["outlook"][1]["precipitation_mm"], 12.0)

    def test_old_payload_without_extra_fields_still_works(self):
        r = ws.fetch_weather(19.07, 72.87, datetime(2026, 10, 9, 16, 0), _session(PAYLOAD))
        self.assertIsNone(r["humidity_pct"])
        self.assertIsNone(r["wind_kmh"])
        self.assertTrue(len(r["outlook"]) >= 1)

    def test_icons(self):
        self.assertEqual(ws.icon_for(0), "☀️")
        self.assertEqual(ws.icon_for(95), "⛈️")
        self.assertEqual(ws.icon_for(None), "🌡️")

    def test_null_precipitation_and_temperature_handled(self):
        r = ws.fetch_weather(19.07, 72.87, datetime(2026, 10, 9, 18, 0), _session(PAYLOAD))
        self.assertEqual((r["flag"], r["precipitation_mm"], r["temperature_c"]), (0, 0.0, None))

    def test_hour_outside_forecast_raises(self):
        with self.assertRaises(ws.WeatherError):
            ws.fetch_weather(19.07, 72.87, datetime(2026, 12, 1, 9, 0), _session(PAYLOAD))

    def test_network_and_bad_payload_raise_weather_error(self):
        with self.assertRaises(ws.WeatherError):
            ws.fetch_weather(19, 72, datetime(2026, 10, 9, 16), _session(exc=requests.Timeout("slow")))
        with self.assertRaises(ws.WeatherError):
            ws.fetch_weather(19, 72, datetime(2026, 10, 9, 16), _session({"error": True}))


if __name__ == "__main__":
    unittest.main()
