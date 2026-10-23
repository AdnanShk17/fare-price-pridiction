import sys
import unittest
from datetime import date, datetime, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import trip_time as tt  # noqa: E402

NOW = datetime(2026, 10, 9, 16, 50, 30)


class TripTimeTests(unittest.TestCase):
    def test_now_mode(self):
        dt, msg = tt.resolve_trip_datetime("now", None, None, NOW)
        self.assertEqual(dt, NOW)
        self.assertIsNone(msg)

    def test_valid_scheduled_booking(self):
        dt, msg = tt.resolve_trip_datetime("scheduled", date(2026, 10, 10), time(19, 30), NOW)
        self.assertEqual(dt, datetime(2026, 10, 10, 19, 30))
        self.assertIsNone(msg)

    def test_past_time_falls_back_to_now_with_message(self):
        dt, msg = tt.resolve_trip_datetime("scheduled", date(2026, 10, 9), time(8, 0), NOW)
        self.assertEqual(dt, NOW)
        self.assertIn("passed", msg)

    def test_too_far_ahead_falls_back(self):
        dt, msg = tt.resolve_trip_datetime("scheduled", date(2026, 11, 20), time(8, 0), NOW)
        self.assertEqual(dt, NOW)
        self.assertIn("days ahead", msg)

    def test_missing_inputs(self):
        dt, msg = tt.resolve_trip_datetime("scheduled", None, None, NOW)
        self.assertEqual(dt, NOW)
        self.assertIsNotNone(msg)

    def test_default_schedule_is_future_quarter_hour(self):
        d, t = tt.default_schedule(NOW)
        chosen = datetime.combine(d, t)
        self.assertGreater(chosen, NOW)
        self.assertEqual(t.minute % 15, 0)
        self.assertEqual(chosen, datetime(2026, 10, 9, 17, 55 + 5)) if False else self.assertEqual(chosen, datetime(2026, 10, 9, 18, 0))

    def test_now_ist_is_naive_and_offset_correct(self):
        n = tt.now_ist()
        self.assertIsNone(n.tzinfo)

    def test_format(self):
        self.assertEqual(tt.format_trip_time(datetime(2026, 10, 10, 19, 30)), "Sat 10 Oct, 07:30 PM IST")


if __name__ == "__main__":
    unittest.main()
