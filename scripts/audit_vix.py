#!/usr/bin/env python3
"""Audit the frozen VIX CSV without modifying it or evaluating forecasts.

Run: .venv/bin/python scripts/audit_vix.py
Requires pandas_market_calendars. Outputs are written to reports/data_audit/.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import platform
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from importlib.metadata import version

import pandas_market_calendars as mcal


ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["DATE", "OPEN", "HIGH", "LOW", "CLOSE"]
PERIODS = {
    "training": (date(1990, 1, 1), date(2015, 12, 31)),
    "validation": (date(2016, 1, 1), date(2020, 12, 31)),
    "reserved_test": (date(2021, 1, 1), date(2025, 12, 31)),
}


def calendar_check(dates):
    """Compare session labels, not UTC timestamps; early closes remain sessions."""
    observed = set(dates)
    start, end = min(observed), max(observed)
    calendars = {name: mcal.get_calendar(name) for name in ("CBOE_Index_Options", "NYSE")}
    schedules = {name: cal.schedule(start_date=start, end_date=end) for name, cal in calendars.items()}
    sessions = {name: set(schedule.index.date) for name, schedule in schedules.items()}
    primary, reference = sessions["CBOE_Index_Options"], sessions["NYSE"]
    names = calendars["CBOE_Index_Options"].regular_holidays.holidays(
        start=start, end=end, return_name=True
    )
    holiday_names = {stamp.date(): str(name) for stamp, name in names.items()}
    records = []
    day = start
    while day <= end:
        present, expected, nyse = day in observed, day in primary, day in reference
        if (not present and day.weekday() < 5) or (present and not expected) or expected != nyse:
            classification = (
                "missing expected session" if expected and not present else
                "observation on calendar closure" if present and not expected else
                "expected closure" if not present and not expected else
                "calendar disagreement"
            )
            records.append({
                "date": day.isoformat(), "classification": classification,
                "observed": present, "cboe_session": expected, "nyse_session": nyse,
                "calendars_agree": expected == nyse,
                "closure_name": holiday_names.get(day, "other calendar closure" if not expected else ""),
            })
        day += timedelta(days=1)
    summary = {
        "package": "pandas_market_calendars", "package_version": version("pandas_market_calendars"),
        "pandas_version": version("pandas"), "primary_calendar": "CBOE_Index_Options",
        "reference_calendar": "NYSE", "calendar_timezone": str(calendars["CBOE_Index_Options"].tz),
        "comparison_start": start.isoformat(), "comparison_end": end.isoformat(),
        "expected_sessions": len(primary),
        "expected_absent_weekday_closures": sum(r["classification"] == "expected closure" for r in records),
        "missing_expected_sessions": sorted(d.isoformat() for d in primary - observed),
        "missing_sessions_both_calendars": sorted(d.isoformat() for d in (primary & reference) - observed),
        "missing_sessions_calendar_disagreement": sorted(d.isoformat() for d in (primary - observed) - reference),
        "observations_on_closures": sorted(d.isoformat() for d in observed - primary),
        "calendar_disagreements": sorted(d.isoformat() for d in primary ^ reference),
    }
    return summary, records


def audit(source, output):
    content = source.read_bytes()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    if reader.fieldnames != FIELDS:
        raise ValueError(f"Expected columns {FIELDS}; found {reader.fieldnames}")
    rows = list(reader)
    if not rows:
        raise ValueError("CSV contains no observations")
    issues = []
    dates = []
    missing = Counter({field: 0 for field in FIELDS})
    invalid = Counter({field: 0 for field in FIELDS[1:]})

    def flag(line, day, field, kind):
        # Do not include observed prices in issue exports.
        issues.append({"csv_line": line, "date": day, "field": field, "issue": kind})

    for line, row in enumerate(rows, start=2):
        if None in row or any(value is None for value in row.values()):
            flag(line, row.get("DATE", ""), "row", "incorrect field count")
        for field in FIELDS:
            if not (row.get(field) or "").strip():
                missing[field] += 1
                flag(line, row.get("DATE", ""), field, "missing cell")
        try:
            day = datetime.strptime(row["DATE"], "%m/%d/%Y").date()
        except (ValueError, TypeError):
            flag(line, row.get("DATE", ""), "DATE", "invalid date")
            day = None
        if day is not None:
            dates.append(day)
            if day.weekday() >= 5:
                flag(line, day.isoformat(), "DATE", "weekend observation")
        numbers = {}
        for field in FIELDS[1:]:
            if not (row.get(field) or "").strip():
                continue
            try:
                value = float(row[field])
                if not math.isfinite(value):
                    raise ValueError("nonfinite")
                numbers[field] = value
                if value <= 0:
                    flag(line, row.get("DATE", ""), field, "nonpositive value")
            except ValueError:
                invalid[field] += 1
                flag(line, row.get("DATE", ""), field, "nonnumeric or nonfinite")
        if len(numbers) == 4 and not (
            numbers["LOW"] <= min(numbers["OPEN"], numbers["CLOSE"])
            <= max(numbers["OPEN"], numbers["CLOSE"]) <= numbers["HIGH"]
        ):
            flag(line, row.get("DATE", ""), "OHLC", "inconsistent high/low bounds")

    counts = Counter(dates)
    duplicates = {day.isoformat(): count for day, count in sorted(counts.items()) if count > 1}
    for day, count in duplicates.items():
        flag("", day, "DATE", f"duplicate date ({count} observations)")
    ordered = all(a <= b for a, b in zip(dates, dates[1:]))
    if not ordered:
        flag("", "", "DATE", "dates not in chronological order")
    if not dates:
        raise ValueError("No valid dates found")
    calendar_summary, calendar_records = calendar_check(dates)
    gaps = [record for record in calendar_records
            if not record["observed"] and date.fromisoformat(record["date"]).weekday() < 5]
    for day in calendar_summary["missing_expected_sessions"]:
        flag("", day, "DATE", "missing expected session (CBOE calendar)")
    for day in calendar_summary["observations_on_closures"]:
        flag("", day, "DATE", "observation on CBOE calendar closure")
    periods = {}
    for name, (start, end) in PERIODS.items():
        selected = [day for day in dates if start <= day <= end]
        periods[name] = {"rows": len(selected), "first_date": min(selected).isoformat() if selected else None,
                         "last_date": max(selected).isoformat() if selected else None}
    excluded = sum(day >= date(2026, 1, 1) for day in dates)
    before_study = sum(day < date(1990, 1, 1) for day in dates)
    result = {
        "source": str(source.resolve()), "source_sha256": hashlib.sha256(content).hexdigest(),
        "generated_utc": datetime.now(timezone.utc).isoformat(), "python_version": platform.python_version(),
        "columns": reader.fieldnames, "loaded_rows": len(rows), "valid_date_rows": len(dates),
        "unique_dates": len(counts), "first_date": min(dates).isoformat(), "last_date": max(dates).isoformat(),
        "dates_nondecreasing": ordered, "duplicate_dates": duplicates,
        "exact_duplicate_rows": sum(n - 1 for n in Counter(tuple(row.get(f) for f in FIELDS) for row in rows).values()),
        "missing_cells": dict(missing), "invalid_numeric_cells": dict(invalid),
        "issue_counts": dict(Counter(item["issue"] for item in issues)), "issue_count": len(issues),
        "absent_weekday_count": len(gaps), "periods": periods, "market_calendar": calendar_summary,
        "excluded_2026_onward_rows": excluded, "before_study_rows": before_study,
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    for name, records, fields in [
        ("issues.csv", issues, ["csv_line", "date", "field", "issue"]),
        ("absent_weekdays.csv", gaps, ["date", "classification", "observed", "cboe_session", "nyse_session", "calendars_agree", "closure_name"]),
        ("calendar_audit.csv", calendar_records, ["date", "classification", "observed", "cboe_session", "nyse_session", "calendars_agree", "closure_name"]),
    ]:
        with (output / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(records)
    period_text = "\n".join(
        f"- {name.replace('_', ' ').capitalize()}: {p['rows']:,} rows, {p['first_date']} through {p['last_date']}."
        for name, p in periods.items()
    )
    report = f"""# Part 2 — VIX data audit

## Verified from the loaded file

The audit loaded {len(rows):,} rows from `{source.name}`, with columns DATE, OPEN, HIGH, LOW, and CLOSE. Valid dates span {result['first_date']} through {result['last_date']}; there are {len(counts):,} unique dates and {len(rows) - len(dates)} invalid or missing date entries.

{period_text}
- Excluded 2026 onward: {excluded:,} rows.
- Before the study period: {before_study:,} rows.

Dates are nondecreasing: {ordered}. Duplicate dates: {len(duplicates)}; exact duplicate rows beyond their first occurrence: {result['exact_duplicate_rows']}. Missing cells by column: {dict(missing)}. Nonnumeric or nonfinite numeric cells by column: {dict(invalid)}.

The checks recorded {len(issues)} issues, including missing or malformed cells, duplicate or unordered dates, weekend observations, nonpositive prices, and inconsistent OHLC bounds. Counts by issue type: {result['issue_counts']}. See `issues.csv` for dated details; a header-only file means no issues were detected by these checks. An empty issue file does not establish calendar completeness.

## Market-calendar reconciliation

The audit uses `pandas_market_calendars` {calendar_summary['package_version']} with `CBOE_Index_Options` as the primary session calendar and `NYSE` as a historical cross-check. The index-options calendar is a relevant comparison for the VIX index; it is not a certified record of historical VIX publication dates. Calendar rules are bundled with the installed package, not fetched live. See the [package documentation](https://pandas-market-calendars.readthedocs.io/en/latest/) and [Cboe calendar implementation](https://github.com/rsheftel/pandas_market_calendars/blob/master/pandas_market_calendars/calendars/cboe.py).

The comparison covers {calendar_summary['comparison_start']} through {calendar_summary['comparison_end']} inclusive, with {calendar_summary['expected_sessions']:,} expected primary-calendar sessions. Among {len(gaps)} absent weekdays, {calendar_summary['expected_absent_weekday_closures']} are expected closures. Expected holidays are not flagged as missing observations. Early-close dates remain valid sessions. Session-date labels are compared directly; UTC market-open/close timestamps are not converted into observation dates. The primary calendar timezone is {calendar_summary['calendar_timezone']}; this does not establish the CSV's publication timezone.

- Missing expected sessions according to the primary calendar ({len(calendar_summary['missing_expected_sessions'])}): {', '.join(calendar_summary['missing_expected_sessions']) or 'none'}.
- Missing sessions supported by both calendars ({len(calendar_summary['missing_sessions_both_calendars'])}): {', '.join(calendar_summary['missing_sessions_both_calendars']) or 'none'}.
- Primary-calendar missing sessions disputed by NYSE ({len(calendar_summary['missing_sessions_calendar_disagreement'])}): {', '.join(calendar_summary['missing_sessions_calendar_disagreement']) or 'none'}. Treat these as calendar discrepancies, not confirmed missing data.
- Observations on primary-calendar closures ({len(calendar_summary['observations_on_closures'])}): {', '.join(calendar_summary['observations_on_closures']) or 'none'}.
- Cboe/NYSE session disagreements ({len(calendar_summary['calendar_disagreements'])}): {', '.join(calendar_summary['calendar_disagreements']) or 'none'}.

`absent_weekdays.csv` now classifies each absent weekday and includes holiday names where supplied by the primary calendar. `calendar_audit.csv` additionally records observations on closure dates and calendar disagreements. The `calendars_agree` column identifies where the reference supports the primary classification. Disagreements require review rather than automatic correction. The check is bounded by observed endpoints and cannot detect missing observations outside that interval.

No forward filling, interpolation, sorting, deduplication, outlier removal, or other cleaning was applied.

## Source, units, and observation rules

The proposal identifies the source as public Cboe VIX historical data, downloaded October 16, 2026: https://www.cboe.com/tradable-products/vix/vix-historical-data/ . This provenance and download date come from the proposal, not embedded CSV metadata. The chosen signal is daily CLOSE, interpreted as the VIX closing level in VIX index points, not a return or percentage change. OPEN, HIGH, and LOW are audited but are not proposed model features.

The file supplies dates without timestamps or timezone metadata. No timezone conversion or aggregation is performed; the supplied daily close is used as one observation per recorded date. The forecasting assumption is that a day's close becomes available after that day's closing value is published. The exact publication time, release delay, historical revisions, and point-in-time availability have not been verified from this file. No claim of intraday availability is made.

The planned study uses 1990–2025 and excludes 2026 onward. Structural and numeric-validity checks cover the entire loaded file, including reserved test rows. This audit does not compute test price distributions, plots, forecast errors, or model-selection statistics. The 2021–2025 test period remains reserved for final forecasting evaluation.

## Unresolved alignment issue

Trading-day horizons require a documented treatment of the remaining calendar discrepancies. This check strengthens the earlier weekday screen by recognizing calendar holidays and extraordinary closures, but package rules can be incomplete for historical periods and exchange sessions need not exactly match index-publication dates. Review primary/reference disagreements and remaining exceptions before treating row offsets as trading-session horizons. No flagged date is automatically inserted or deleted.

## Reproduction and evidence

Install dependencies with `uv pip install --python .venv/bin/python -r requirements-audit.txt`, then run `.venv/bin/python scripts/audit_vix.py` from the project root. Optional arguments: `--source PATH` and `--output-dir PATH`. Outputs are this report, `audit.json`, `issues.csv`, `absent_weekdays.csv`, and `calendar_audit.csv`.

Source SHA-256: `{result['source_sha256']}`.

Python: {platform.python_version()}. Generated UTC: {result['generated_utc']}.

AI-use statement: Codex assisted in writing the audit code and report template. The reported counts are generated by the script; independent student review of the checks and calendar assumptions remains to be completed.
"""
    (output / "report.md").write_text(report)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == result["source_sha256"], "Source changed during audit"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data/VIX_History.csv")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports/data_audit")
    args = parser.parse_args()
    summary = audit(args.source, args.output_dir)
    print(f"Audited {summary['loaded_rows']:,} rows; {summary['issue_count']} issues recorded.")
    print(f"Report: {args.output_dir / 'report.md'}")
