"""Synthetic checks of fitting-boundary and missing-session behavior."""
import unittest
from datetime import date, timedelta
from check_evaluation import complete_window, mature


class EvaluationTests(unittest.TestCase):
    def test_label_must_be_observed_at_cutoff(self):
        cutoff = date(2015, 12, 31)
        self.assertTrue(mature(cutoff, cutoff))
        self.assertFalse(mature(date(2016, 1, 4), cutoff))
        self.assertFalse(mature(date(2021, 1, 4), date(2020, 12, 31)))

    def test_missing_session_is_not_compressed_away(self):
        sessions = [date(2020, 1, 1) + timedelta(days=i) for i in range(10)]
        available = set(sessions)
        self.assertTrue(complete_window(sessions, available, 3, 3, 4))
        available.remove(sessions[5])
        self.assertFalse(complete_window(sessions, available, 3, 3, 4))
        self.assertTrue(complete_window(sessions, available, 3, 3, 1))

    def test_no_negative_index_or_target_past_end(self):
        sessions = [date(2020, 1, 1) + timedelta(days=i) for i in range(10)]
        self.assertFalse(complete_window(sessions, set(sessions), 1, 3, 1))
        self.assertFalse(complete_window(sessions, set(sessions), 8, 3, 2))


if __name__ == '__main__':
    unittest.main()
