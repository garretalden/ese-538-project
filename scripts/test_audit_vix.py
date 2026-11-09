"""Run with: .venv/bin/python -m unittest discover -s scripts -p 'test_audit_vix.py'."""

import tempfile
import unittest
from pathlib import Path

from audit_vix import audit, calendar_check
from datetime import date


class AuditTests(unittest.TestCase):
    def run_audit(self, text):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.csv"
            source.write_text(text)
            result = audit(source, Path(directory) / "output")
            self.assertEqual(source.read_text(), text)
            for name in ("report.md", "audit.json", "issues.csv", "absent_weekdays.csv", "calendar_audit.csv"):
                self.assertTrue((Path(directory) / "output" / name).is_file())
            return result

    def test_period_boundaries_and_weekday_gap(self):
        result = self.run_audit(
            "DATE,OPEN,HIGH,LOW,CLOSE\n"
            "12/31/2020,10,12,9,11\n"
            "01/04/2021,10,12,9,11\n"
        )
        self.assertEqual(result["issue_count"], 0)
        self.assertEqual(result["periods"]["validation"]["rows"], 1)
        self.assertEqual(result["periods"]["reserved_test"]["rows"], 1)
        # January 1 is an expected holiday, not a missing session.
        self.assertEqual(result["market_calendar"]["expected_absent_weekday_closures"], 1)
        self.assertEqual(result["market_calendar"]["missing_expected_sessions"], [])
        self.assertEqual(result["absent_weekday_count"], 1)

    def test_labor_day_and_christmas(self):
        for dates, holiday, name in [
            ([date(2020, 9, 4), date(2020, 9, 8)], "2020-09-07", "Labor"),
            ([date(2020, 12, 24), date(2020, 12, 28)], "2020-12-25", "Christmas"),
        ]:
            summary, records = calendar_check(dates)
            record = next(r for r in records if r["date"] == holiday)
            self.assertEqual(record["classification"], "expected closure")
            self.assertIn(name, record["closure_name"])
            self.assertTrue(record["calendars_agree"])
            self.assertEqual(summary["missing_expected_sessions"], [])

    def test_missing_session_and_observed_closure(self):
        summary, records = calendar_check([
            date(2020, 9, 4), date(2020, 9, 7), date(2020, 9, 9)
        ])
        self.assertEqual(summary["missing_expected_sessions"], ["2020-09-08"])
        self.assertEqual(summary["observations_on_closures"], ["2020-09-07"])

    def test_early_close_and_extraordinary_closure(self):
        summary, _ = calendar_check([date(2020, 11, 27)])
        self.assertEqual(summary["expected_sessions"], 1)
        self.assertEqual(summary["observations_on_closures"], [])
        summary, records = calendar_check([date(2012, 10, 26), date(2012, 10, 31)])
        self.assertEqual(summary["expected_absent_weekday_closures"], 2)
        self.assertEqual(summary["missing_expected_sessions"], [])
        self.assertTrue(all(r["calendars_agree"] for r in records))

    def test_historical_calendar_disagreement(self):
        summary, records = calendar_check([date(2001, 9, 10), date(2001, 9, 17)])
        expected = [f"2001-09-{day}" for day in range(11, 15)]
        self.assertEqual(summary["calendar_disagreements"], expected)
        self.assertEqual(summary["missing_sessions_calendar_disagreement"], expected)
        self.assertEqual(summary["missing_sessions_both_calendars"], [])

    def test_known_defects(self):
        result = self.run_audit(
            "DATE,OPEN,HIGH,LOW,CLOSE\n"
            "01/04/2021,10,12,9,13\n"
            "01/04/2021,10,12,9,13\n"
            "01/02/2021,0,nan,9,\n"
            "bad,10,12,9,no\n"
        )
        self.assertFalse(result["dates_nondecreasing"])
        self.assertEqual(result["duplicate_dates"], {"2021-01-04": 2})
        self.assertEqual(result["exact_duplicate_rows"], 1)
        self.assertEqual(result["missing_cells"]["CLOSE"], 1)
        self.assertEqual(result["invalid_numeric_cells"]["HIGH"], 1)
        self.assertEqual(result["invalid_numeric_cells"]["CLOSE"], 1)
        self.assertEqual(result["issue_counts"]["inconsistent high/low bounds"], 2)
        self.assertEqual(result["issue_counts"]["invalid date"], 1)
        self.assertEqual(result["issue_counts"]["weekend observation"], 1)
        self.assertEqual(result["issue_counts"]["nonpositive value"], 1)


if __name__ == "__main__":
    unittest.main()
