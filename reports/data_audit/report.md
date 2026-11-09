# Part 2 — VIX data audit

## Verified from the loaded file

The audit loaded 9,296 rows from `VIX_History.csv`, with columns DATE, OPEN, HIGH, LOW, and CLOSE. Valid dates span 1990-01-02 through 2026-10-16; there are 9,296 unique dates and 0 invalid or missing date entries.

- Training: 6,550 rows, 1990-01-02 through 2015-12-31.
- Validation: 1,259 rows, 2016-01-04 through 2020-12-31.
- Reserved test: 1,282 rows, 2021-01-04 through 2025-12-31.
- Excluded 2026 onward: 205 rows.
- Before the study period: 0 rows.

Dates are nondecreasing: True. Duplicate dates: 0; exact duplicate rows beyond their first occurrence: 0. Missing cells by column: {'DATE': 0, 'OPEN': 0, 'HIGH': 0, 'LOW': 0, 'CLOSE': 0}. Nonnumeric or nonfinite numeric cells by column: {'OPEN': 0, 'HIGH': 0, 'LOW': 0, 'CLOSE': 0}.

The checks recorded 89 issues, including missing or malformed cells, duplicate or unordered dates, weekend observations, nonpositive prices, and inconsistent OHLC bounds. Counts by issue type: {'inconsistent high/low bounds': 47, 'missing expected session (CBOE calendar)': 8, 'observation on CBOE calendar closure': 34}. See `issues.csv` for dated details; a header-only file means no issues were detected by these checks. An empty issue file does not establish calendar completeness.

## Market-calendar reconciliation

The audit uses `pandas_market_calendars` 5.6.0 with `CBOE_Index_Options` as the primary session calendar and `NYSE` as a historical cross-check. The index-options calendar is a relevant comparison for the VIX index; it is not a certified record of historical VIX publication dates. Calendar rules are bundled with the installed package, not fetched live. See the [package documentation](https://pandas-market-calendars.readthedocs.io/en/latest/) and [Cboe calendar implementation](https://github.com/rsheftel/pandas_market_calendars/blob/master/pandas_market_calendars/calendars/cboe.py).

The comparison covers 1990-01-02 through 2026-10-16 inclusive, with 9,270 expected primary-calendar sessions. Among 303 absent weekdays, 295 are expected closures. Expected holidays are not flagged as missing observations. Early-close dates remain valid sessions. Session-date labels are compared directly; UTC market-open/close timestamps are not converted into observation dates. The primary calendar timezone is America/Chicago; this does not establish the CSV's publication timezone.

- Missing expected sessions according to the primary calendar (8): 1991-03-01, 1997-01-31, 1997-11-26, 1999-12-31, 2001-09-11, 2001-09-12, 2001-09-13, 2001-09-14.
- Missing sessions supported by both calendars (4): 1991-03-01, 1997-01-31, 1997-11-26, 1999-12-31.
- Primary-calendar missing sessions disputed by NYSE (4): 2001-09-11, 2001-09-12, 2001-09-13, 2001-09-14. Treat these as calendar discrepancies, not confirmed missing data.
- Observations on primary-calendar closures (34): 2004-06-11, 2022-05-30, 2022-06-20, 2022-07-04, 2022-09-05, 2022-11-24, 2023-01-16, 2023-02-20, 2023-05-29, 2023-06-19, 2023-07-04, 2023-09-04, 2023-11-23, 2024-01-15, 2024-02-19, 2024-05-27, 2024-06-19, 2024-07-04, 2024-09-02, 2024-11-28, 2025-01-09, 2025-01-20, 2025-02-17, 2025-05-26, 2025-06-19, 2025-07-04, 2025-09-01, 2025-11-27, 2026-01-19, 2026-02-16, 2026-05-25, 2026-06-19, 2026-07-03, 2026-09-07.
- Cboe/NYSE session disagreements (4): 2001-09-11, 2001-09-12, 2001-09-13, 2001-09-14.

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

Source SHA-256: `a9742d4deab98f7644bda10df92db0b6afbca17ccc8b64139c52ad2ca0963d42`.

Python: 3.12.7. Generated UTC: 2026-11-09T20:03:41.717515+00:00.

AI-use statement: Codex assisted in writing the audit code and report template. The reported counts are generated by the script; independent student review of the checks and calendar assumptions remains to be completed.
