import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fare_logic as fl  # noqa: E402


class FareLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = fl.load_config()

    def test_haversine_known_distance(self):
        # CST -> Bandra is roughly 13-15 km in a straight line
        d = fl.haversine_km(18.9400, 72.8353, 19.0596, 72.8295)
        self.assertTrue(12 < d < 15, d)
        self.assertAlmostEqual(fl.haversine_km(19, 72, 19, 72), 0.0)

    def test_peak_and_night_windows(self):
        self.assertTrue(fl.is_peak_hour(8) and fl.is_peak_hour(11) and fl.is_peak_hour(21))
        self.assertFalse(fl.is_peak_hour(14) or fl.is_peak_hour(7))
        self.assertTrue(fl.is_night_hour(0) and fl.is_night_hour(4))
        self.assertFalse(fl.is_night_hour(12))
        self.assertFalse(any(fl.is_peak_hour(h) and fl.is_night_hour(h) for h in range(24)))

    def test_kaali_peeli_meter(self):
        kp = self.cfg["platforms"]["mumbai_kaali_peeli"]
        self.assertAlmostEqual(fl.platform_fare(kp, 1.0, 5, 14, 0), 28.0)          # minimum fare
        self.assertAlmostEqual(fl.platform_fare(kp, 11.5, 30, 14, 0), 28 + 10 * 18.66)
        # meter taxis have no rain / peak multiplier
        self.assertAlmostEqual(fl.platform_fare(kp, 11.5, 30, 9, 2), 28 + 10 * 18.66)

    def test_multipliers_increase_fare(self):
        ola = self.cfg["platforms"]["ola_mini"]
        base = fl.platform_fare(ola, 10, 30, 14, 0)
        self.assertGreater(fl.platform_fare(ola, 10, 30, 9, 0), base)    # peak
        self.assertGreater(fl.platform_fare(ola, 10, 30, 2, 0), base)    # night
        rain = fl.platform_fare(ola, 10, 30, 14, 1)
        heavy = fl.platform_fare(ola, 10, 30, 14, 2)
        self.assertTrue(base < rain < heavy)

    def test_minimum_fare_applies(self):
        ola = self.cfg["platforms"]["ola_mini"]
        self.assertGreaterEqual(fl.platform_fare(ola, 0.1, 1, 14, 0), ola["minimum_fare"])

    def test_traffic_level(self):
        far = (19.30, 73.10)  # far from every busy zone
        self.assertEqual(fl.traffic_level(*far, *far, 14, 0)[0], "Low")
        self.assertEqual(fl.traffic_level(*far, *far, 18, 0)[0], "Moderate")
        self.assertEqual(fl.traffic_level(19.06, 72.865, 19.119, 72.846, 18, 2)[0], "Heavy")

    def test_fair_price_and_features(self):
        fares = fl.all_platform_fares(self.cfg, 10, 30, 9, 0)
        self.assertEqual(set(fares), set(fl.PLATFORM_KEYS))
        self.assertAlmostEqual(fl.fair_price(fares), sum(fares.values()) / 4)
        row = fl.feature_row(10, 30, 9, 1)
        self.assertEqual(list(row), fl.FEATURES)
        self.assertEqual((row["is_peak"], row["is_night"]), (1, 0))

    def test_config_validation(self):
        import json
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump({"platforms": {"ola_mini": {}}}, fh)
        with self.assertRaises(ValueError):
            fl.load_config(fh.name)

    def test_platform_fares_change_with_vehicle_category(self):
        args = (self.cfg, 10, 30, 16, 0)
        auto = fl.vehicle_fares(*args, "Auto Rickshaw")
        sedan = fl.vehicle_fares(*args, "Hatchback / Sedan")
        suv = fl.vehicle_fares(*args, "SUV Prime")
        for key in ("ola_mini", "uber_go"):
            self.assertLess(auto[key], sedan[key])      # auto cheaper than sedan
            self.assertGreater(suv[key], sedan[key])    # SUV dearer than sedan
        # sedan = the platform's base rates
        self.assertAlmostEqual(sedan["ola_mini"], fl.all_platform_fares(*args)["ola_mini"])

    def test_unavailable_categories_are_none(self):
        suv = fl.vehicle_fares(self.cfg, 10, 30, 16, 0, "SUV Prime")
        self.assertIsNone(suv["mumbai_kaali_peeli"])
        self.assertIsNone(suv["rapido_bike_cab"])
        auto = fl.vehicle_fares(self.cfg, 10, 30, 16, 0, "Auto Rickshaw")
        self.assertIsNone(auto["mumbai_kaali_peeli"])
        self.assertIsNotNone(auto["rapido_bike_cab"])

    def test_every_vehicle_has_at_least_one_platform(self):
        for vehicle in fl.VEHICLE_MULTIPLIERS:
            fares = fl.vehicle_fares(self.cfg, 10, 30, 16, 0, vehicle)
            self.assertTrue(any(v is not None for v in fares.values()), vehicle)

    def test_service_area(self):
        self.assertTrue(fl.in_service_area(19.07, 72.88))
        self.assertFalse(fl.in_service_area(18.52, 73.85))  # Pune


class ModelTests(unittest.TestCase):
    """Uses the shipped model; skipped if it has not been trained yet."""

    def setUp(self):
        import joblib
        path = Path(__file__).resolve().parents[1] / "mumbai_cab_fare_model.pkl"
        if not path.exists():
            self.skipTest("model not trained")
        self.model = joblib.load(path)
        self.cfg = fl.load_config()

    def test_close_to_rule_based_price_in_range(self):
        for dist, dur, hour, weather in [(5, 20, 14, 0), (12, 45, 9, 1), (30, 70, 19, 2), (8, 20, 2, 0)]:
            truth = fl.fair_price(fl.all_platform_fares(self.cfg, dist, dur, hour, weather))
            pred = self.model.predict_one(dist, dur, hour, weather)
            self.assertLess(abs(pred - truth) / truth, 0.08, (dist, dur, hour, weather, pred, truth))

    def test_weather_not_double_counted(self):
        base = self.model.predict_one(12, 35, 14, 0)
        heavy = self.model.predict_one(12, 35, 14, 2)
        self.assertLess(heavy / base, 1.45)  # old app applied the effect twice (~1.77x)

    def test_extrapolates_beyond_training_range(self):
        truth = fl.fair_price(fl.all_platform_fares(self.cfg, 250, 300, 14, 0))
        pred = self.model.predict_one(250, 300, 14, 0)
        self.assertLess(abs(pred - truth) / truth, 0.10)

    def test_minimum_fare(self):
        self.assertGreaterEqual(self.model.predict_one(0.2, 1, 14, 0), fl.MIN_FARE)


if __name__ == "__main__":
    unittest.main()
