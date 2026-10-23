import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

import poi_service as ps  # noqa: E402

# a ~12 km north-south route through Mumbai (lat, lon), 25 vertices
PATH = [(19.00 + i * 0.0045, 72.84) for i in range(25)]
NOW = datetime(2026, 10, 9, 19, 0)


def el(name, lat, lon=72.84, **tags):
    return {"type": "node", "lat": lat, "lon": lon, "tags": {"name": name, **tags}}


class PoiTests(unittest.TestCase):
    def test_categorize(self):
        self.assertEqual(ps.categorize({"shop": "mall"}), "mall")
        self.assertEqual(ps.categorize({"amenity": "restaurant"}), "food")
        self.assertEqual(ps.categorize({"amenity": "cafe"}), "cafe")
        self.assertEqual(ps.categorize({"tourism": "viewpoint"}), "attraction")
        self.assertEqual(ps.categorize({"historic": "fort"}), "attraction")
        self.assertIsNone(ps.categorize({"amenity": "bank"}))

    def test_parse_skips_unnamed_dedupes_and_uses_way_centers(self):
        data = {"elements": [
            el("Cafe A", 19.01, amenity="cafe"),
            el("Cafe A", 19.01, amenity="cafe"),                       # duplicate
            {"type": "node", "lat": 19.02, "lon": 72.84, "tags": {"amenity": "cafe"}},  # unnamed
            {"type": "way", "center": {"lat": 19.03, "lon": 72.84}, "tags": {"name": "Big Mall", "shop": "mall"}},
            el("Bank", 19.04, amenity="bank"),                          # irrelevant
        ]}
        places = ps.parse_elements(data)
        self.assertEqual(sorted(p["name"] for p in places), ["Big Mall", "Cafe A"])

    def test_simplify_and_segments(self):
        long_path = [(19.0 + i * 0.001, 72.8) for i in range(2000)]
        s = ps.simplify_path(long_path, 60)
        self.assertLessEqual(len(s), 60)
        self.assertEqual((s[0], s[-1]), (long_path[0], long_path[-1]))
        short = ps.split_segments(PATH)               # ~12 km -> one segment
        self.assertEqual(len(short), 1)
        far = [(18.9 + i * 0.01, 72.9) for i in range(120)]  # ~130 km
        segs = ps.split_segments(far)
        self.assertTrue(2 <= len(segs) <= ps.MAX_SEGMENTS)
        self.assertEqual(segs[0][0], far[0])
        self.assertEqual(segs[-1][-1], far[-1])

    def test_query_contains_radius_categories_and_limits(self):
        q = ps.build_query([PATH[:3]], 500, ["food", "mall"])
        self.assertIn("around:500,19.00000,72.84000", q)
        self.assertIn("restaurant", q)
        self.assertIn('"shop"="mall"', q)
        self.assertNotIn("tourism", q)
        self.assertIn(f"out center {ps.RESULTS_PER_SEGMENT}", q)
        with self.assertRaises(ValueError):
            ps.build_query([PATH[:3]], 500, ["nonsense"])

    def test_rank_adds_timing_and_prefers_notable_close_places(self):
        raw = ps.parse_elements({"elements": [
            el("Famous Diner", 19.050, amenity="restaurant", wikidata="Q1", website="x", opening_hours="Mo-Su 10:00-23:00"),
            el("Plain Diner", 19.050, 72.8402, amenity="restaurant"),
            el("Far Diner", 19.050, 72.8450, amenity="restaurant", wikidata="Q2"),   # ~500 m off route
        ]})
        ranked = ps.rank_pois(raw, PATH, duration_min=30, trip_dt=NOW, per_category=3)
        names = [p["name"] for p in ranked["food"]]
        self.assertEqual(len(names), 3)
        top = max(ranked["food"], key=lambda p: p["score"])
        self.assertEqual(top["name"], "Famous Diner")
        famous = next(p for p in ranked["food"] if p["name"] == "Famous Diner")
        # ~5.5 km along a ~12 km route -> about 45% of the 30 min trip
        self.assertTrue(10 <= famous["minutes_into_trip"] <= 17, famous["minutes_into_trip"])
        self.assertEqual(famous["pass_time"].date(), NOW.date())
        self.assertGreater(famous["pass_time"], NOW)
        far = next(p for p in ranked["food"] if p["name"] == "Far Diner")
        self.assertGreater(far["off_route_m"], 300)

    def test_max_off_route_filter(self):
        raw = ps.parse_elements({"elements": [el("Far", 19.05, 72.86, amenity="cafe"), el("Near", 19.05, amenity="cafe")]})
        ranked = ps.rank_pois(raw, PATH, 30, NOW, max_off_route_m=300)
        self.assertEqual([p["name"] for p in ranked["cafe"]], ["Near"])

    def test_results_are_spread_along_the_route(self):
        elements = [el(f"Cafe {i}", 19.00 + i * 0.024, amenity="cafe", website="w", wikidata="Q") for i in range(5)]
        elements += [el(f"Clump {i}", 19.0010 + i * 0.00001, amenity="cafe", website="w", wikidata="Q", brand="b") for i in range(12)]
        ranked = ps.rank_pois(ps.parse_elements({"elements": elements}), PATH, 30, NOW, per_category=5)
        fractions = [p["route_fraction"] for p in ranked["cafe"]]
        self.assertGreater(max(fractions) - min(fractions), 0.5)   # not all bunched at the start

    def test_fetch_falls_back_to_mirror_and_raises_when_all_fail(self):
        ok = mock.Mock()
        ok.json.return_value = {"elements": [el("Cafe A", 19.01, amenity="cafe")]}
        ok.raise_for_status.return_value = None
        session = mock.Mock()
        session.post.side_effect = [requests.Timeout("main down"), ok]
        places = ps.fetch_pois(PATH, 500, ["cafe"], session=session)
        self.assertEqual(len(places), 1)
        self.assertEqual(session.post.call_count, 2)

        session = mock.Mock()
        session.post.side_effect = requests.ConnectionError("down")
        with self.assertRaises(ps.PoiError):
            ps.fetch_pois(PATH, 500, ["cafe"], session=session)

    def test_meal_context(self):
        self.assertEqual(ps.meal_context(20)[1], "Dinner time")
        self.assertEqual(ps.meal_context(20)[2][0], "food")
        self.assertEqual(ps.meal_context(8)[2][0], "cafe")
        self.assertIn("Late night", ps.meal_context(2)[1])


if __name__ == "__main__":
    unittest.main()
