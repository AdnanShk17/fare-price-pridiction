import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

import database as db  # noqa: E402


def _save(path, session="s1", pickup="A"):
    return db.save_booking(pickup, "B", "", 10.5, 25, "Low", "Sunny", 100, 110, 60, 90, 95,
                           vehicle_type="Hatchback / Sedan", session_id=session, db_path=path)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "t.db"
        db.init_db(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_read_back(self):
        _save(self.path)
        df = db.get_bookings(db_path=self.path)
        self.assertEqual(len(df), 1)
        self.assertEqual(df.loc[0, "pickup"], "A")
        self.assertEqual(df.loc[0, "ml_fare"], 95)

    def test_sessions_are_isolated(self):
        _save(self.path, "s1")
        _save(self.path, "s2")
        self.assertEqual(len(db.get_bookings("s1", db_path=self.path)), 1)
        self.assertEqual(len(db.get_bookings(db_path=self.path)), 2)

    def test_sql_injection_is_stored_as_text(self):
        _save(self.path, pickup="x'); DROP TABLE cab_bookings;--")
        self.assertEqual(len(db.get_bookings(db_path=self.path)), 1)

    def test_unavailable_platform_fare_is_stored_as_null(self):
        db.save_booking("A", "B", "", 5, 10, "Low", "Sunny", 100, 110, None, None, 95,
                        vehicle_type="SUV Prime", session_id="s1", db_path=self.path)
        row = db.get_bookings("s1", db_path=self.path).loc[0]
        self.assertTrue(pd.isna(row["kaali_peeli_fare"]) and pd.isna(row["rapido_fare"]))

    def test_trip_time_is_saved(self):
        db.save_booking("A", "B", "", 5, 10, "Low", "Sunny", 1, 2, 3, 4, 5,
                        session_id="s1", trip_time="2026-10-10T19:30", db_path=self.path)
        self.assertEqual(db.get_bookings("s1", db_path=self.path).loc[0, "trip_time"], "2026-10-10T19:30")

    def test_long_text_is_truncated(self):
        _save(self.path, pickup="a" * 5000)
        self.assertEqual(len(db.get_bookings(db_path=self.path).loc[0, "pickup"]), 500)

    def test_migrates_old_schema(self):
        old = Path(self.tmp.name) / "old.db"
        conn = sqlite3.connect(old)
        conn.execute("CREATE TABLE cab_bookings (booking_id INTEGER PRIMARY KEY AUTOINCREMENT, pickup TEXT, "
                     "dropoff TEXT, stops TEXT, distance_km REAL, duration_min REAL, traffic_level TEXT, "
                     "weather TEXT, ola_fare REAL, uber_fare REAL, rapido_fare REAL, kaali_peeli_fare REAL, "
                     "ml_fare REAL, booking_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
        conn.commit()
        conn.close()
        db.init_db(old)
        _save(old)
        self.assertEqual(len(db.get_bookings("s1", db_path=old)), 1)


if __name__ == "__main__":
    unittest.main()
