import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

import route_engine as re_  # noqa: E402

OK_PAYLOAD = {
    "code": "Ok",
    "routes": [{"distance": 12345.0, "duration": 1500.0,
                "geometry": {"coordinates": [[72.83, 18.94], [72.85, 19.0]]}}],
}


def _resp(payload, status=200):
    r = mock.Mock()
    r.json.return_value = payload
    r.raise_for_status.side_effect = None if status == 200 else requests.HTTPError("boom")
    return r


class RouteEngineTests(unittest.TestCase):
    def test_build_points_skips_none_and_limits(self):
        pts = re_.build_points((19.0, 72.8), (19.1, 72.9), [None, (19.05, 72.85)])
        self.assertEqual(len(pts), 3)
        with self.assertRaises(ValueError):
            re_.build_points((19, 72.8), (19.1, 72.9), [(19.01, 72.8)] * 4)
        with self.assertRaises(ValueError):
            re_.build_points((95, 72.8), (19.1, 72.9))

    def test_success_parsing(self):
        session = mock.Mock()
        session.get.return_value = _resp(OK_PAYLOAD)
        res = re_.get_osrm_route(18.94, 72.83, 19.0, 72.85, session=session)
        self.assertTrue(res["success"])
        self.assertEqual(res["distance_km"], 12.35)
        self.assertEqual(res["duration_min"], 25.0)
        self.assertEqual(res["path_coordinates"][0], [18.94, 72.83])  # lat, lon order

    def test_falls_back_on_http_error_and_flags_it(self):
        session = mock.Mock()
        session.get.return_value = _resp({}, status=500)
        res = re_.get_osrm_route(18.94, 72.83, 19.0, 72.85, session=session)
        self.assertFalse(res["success"])
        self.assertIsNotNone(res["warning"])
        self.assertGreater(res["distance_km"], 0)

    def test_falls_back_on_network_error_and_bad_code(self):
        session = mock.Mock()
        session.get.side_effect = requests.ConnectionError("down")
        self.assertFalse(re_.get_osrm_route(18.94, 72.83, 19.0, 72.85, session=session)["success"])
        session.get.side_effect = None
        session.get.return_value = _resp({"code": "NoRoute"})
        self.assertFalse(re_.get_osrm_route(18.94, 72.83, 19.0, 72.85, session=session)["success"])

    def test_fetch_raises_so_failures_are_never_cached(self):
        session = mock.Mock()
        session.get.side_effect = requests.Timeout("slow")
        with self.assertRaises(re_.RouteError):
            re_.fetch_osrm_route([(18.94, 72.83), (19.0, 72.85)], session=session)

    def test_algorithm_summary_has_no_wrong_claims(self):
        text = str(re_.get_routing_algorithms_summary())
        self.assertNotIn("O(log V)", text)
        self.assertNotIn("O(E)", text)


if __name__ == "__main__":
    unittest.main()
