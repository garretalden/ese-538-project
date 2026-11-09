#!/usr/bin/env python3
"""Generate baseline Part 3 evidence; no model fitting or test-price analysis.
Run: .venv/bin/python scripts/check_evaluation.py
"""
import csv
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from importlib.metadata import version

import pandas_market_calendars as mcal

ROOT = Path(__file__).resolve().parents[1]
HORIZONS = (5, 10, 20)
LAGS = (20,)
ALPHAS = (0.1, 1.0, 10.0, 100.0)


def mature(target, cutoff):
    return target <= cutoff


def complete_window(sessions, available, i, lag, horizon):
    return (i >= lag - 1 and i + horizon < len(sessions)
            and all(d in available for d in sessions[i-lag+1:i+horizon+1]))


def write_csv(path, records, fields):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)


def main():
    source = ROOT / 'data/VIX_History.csv'
    output = ROOT / 'reports/evaluation_design'
    output.mkdir(parents=True, exist_ok=True)
    blob = source.read_bytes()
    with source.open() as stream:
        rows = list(csv.DictReader(stream))
    dates = [datetime.strptime(r['DATE'], '%m/%d/%Y').date() for r in rows]
    assert dates == sorted(set(dates)), 'Dates must be sorted and unique'
    # Test prices are never converted or summarized. Dates only determine eligibility.
    development = {d: float(r['CLOSE']) for d, r in zip(dates, rows) if d <= date(2020, 12, 31)}
    calendars = {name: set(mcal.get_calendar(name).schedule(
        start_date='1990-01-01', end_date='2025-12-31').index.date)
        for name in ('CBOE_Index_Options', 'NYSE')}
    primary, reference = calendars.values()
    sessions = sorted(primary | reference)
    available = set(dates) & primary & reference
    max_lag, max_horizon = max(LAGS), max(HORIZONS)
    fit_counts = {}
    boundaries = []
    for label, cutoff in [('training', date(2015, 12, 31)), ('final_refit', date(2020, 12, 31))]:
        fit_counts[label] = {}
        for h in (1,) + HORIZONS:
            eligible = [i for i, origin in enumerate(sessions)
                        if complete_window(sessions, available, i, max_lag, h)
                        and mature(sessions[i+h], cutoff)]
            assert all(sessions[i+h] <= cutoff for i in eligible)
            fit_counts[label][h] = len(eligible)
            for i, origin in enumerate(sessions):
                if origin <= cutoff and (cutoff - origin).days <= 35 and i+h < len(sessions):
                    boundaries.append({'fit': label, 'cutoff': cutoff, 'origin': origin,
                        'horizon': h, 'target': sessions[i+h],
                        'label_mature': mature(sessions[i+h], cutoff),
                        'window_complete': complete_window(sessions, available, i, max_lag, h)})
    scored, exclusions = [], []
    for label, start, end, first_origin in [
        ('validation', date(2016, 1, 1), date(2020, 12, 31), date(2015, 12, 31)),
        ('reserved_test', date(2021, 1, 1), date(2025, 12, 31), date(2020, 12, 31)),
    ]:
        for i, origin in enumerate(sessions):
            if not first_origin <= origin <= end:
                continue
            if i + max_horizon >= len(sessions) or sessions[i+max_horizon] > end:
                exclusions.append({'period': label, 'origin': origin, 'reason': '20-session target beyond period'})
                continue
            if not complete_window(sessions, available, i, max_lag, max_horizon):
                exclusions.append({'period': label, 'origin': origin, 'reason': 'missing observation or calendar disagreement in window'})
                continue
            for h in HORIZONS:
                target = sessions[i+h]
                assert start <= target <= end
                assert sessions[i-max_lag+1] <= origin < target
                scored.append({'period': label, 'origin': origin, 'horizon': h,
                               'input_start': sessions[i-max_lag+1], 'target': target})
        origin_sets = [{r['origin'] for r in scored if r['period'] == label and r['horizon'] == h} for h in HORIZONS]
        assert origin_sets[0] == origin_sets[1] == origin_sets[2]
    example_origin = date(2015, 12, 31)
    i = sessions.index(example_origin)
    assert complete_window(sessions, available, i, max_lag, max_horizon)
    example = [{'role': 'input', 'step': n-max_lag+1, 'date': day, 'close': development[day]}
               for n, day in enumerate(sessions[i-max_lag+1:i+1])]
    example += [{'role': 'future session (not an input)', 'step': step,
                 'date': sessions[i+step], 'close': development[sessions[i+step]]}
                for step in range(1, max_horizon+1)]
    # Independent explicit date expectations make this more than a self-consistency check.
    expected_targets = {5: date(2016, 1, 8), 10: date(2016, 1, 15), 20: date(2016, 2, 1)}
    assert {h: sessions[i+h] for h in HORIZONS} == expected_targets
    config = {'source_sha256': hashlib.sha256(blob).hexdigest(), 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'calendar_version': version('pandas_market_calendars'), 'horizons': HORIZONS, 'lag_grid': LAGS,
        'ridge_alpha_grid': ALPHAS, 'fit_eligible_counts': fit_counts,
        'common_origin_counts': {p: sum(r['period'] == p and r['horizon'] == 5 for r in scored)
                                 for p in ('validation', 'reserved_test')},
        'checks': {'ordered_unique_dates': True, 'mature_fit_labels': True,
                   'evaluation_targets_within_period': True, 'common_origins_all_horizons': True,
                   'explicit_example_dates_match': True},
        'status': 'Timing checks executed; model results are generated separately by train_ridge.py; bootstrap remains planned'}
    (output / 'checks.json').write_text(json.dumps(config, indent=2) + '\n')
    write_csv(output / 'eligible_origins.csv', scored, ['period', 'origin', 'horizon', 'input_start', 'target'])
    write_csv(output / 'excluded_origins.csv', exclusions, ['period', 'origin', 'reason'])
    write_csv(output / 'label_maturity.csv', boundaries, ['fit', 'cutoff', 'origin', 'horizon', 'target', 'label_mature', 'window_complete'])
    write_csv(output / 'timing_example.csv', example, ['role', 'step', 'date', 'close'])
    report = f'''# Part 3 — Evaluation design and leakage check

## Design from the proposal

Train on January 1990–December 2015; validate on January 2016–December 2020; reserve January 2021–December 2025 for final testing. Exclude 2026. Predict daily VIX CLOSE levels at 5, 10, and 20 trading-session horizons. The checkpoint prioritizes 5 and 20, as requested in the proposal feedback. Primary accuracy is mean absolute error (MAE), the average absolute forecast-minus-observation difference, in VIX points. Persistence predicts the origin's CLOSE at every horizon and has no fitted parameters.

Fit candidate ridge models once using training data and hold their coefficients fixed during validation. After validation choices are frozen, refit once using training plus validation, with labels observed by December 31, 2020. Hold coefficients and preprocessing parameters fixed throughout testing. At each daily origin, update only the input window with newly observed closes. Earlier test observations may become later test inputs; test outcomes never select settings or refit parameters. No validation or test accuracy is computed in this Part 3 artifact. The earlier data audit inspected test data quality, but no test forecast results have been inspected by these scripts.

## Explicit implementation defaults (additional to the proposal)

For the initial 5- and 20-session comparison, fix the lag count at 20 and search ridge penalties {{0.1, 1, 10, 100}}: four candidates per fitted model. The lag count is a prespecified choice, not a validation-selected result. A lag count p means [CLOSE(t-p+1), ..., CLOSE(t)], including the origin close. Use raw closing levels, an intercept, and standardized input columns; estimate means and standard deviations only from the eligible fitting examples. Apply those fixed transformations to validation and refit them only at the final fitting boundary. Do not normalize the target, interpolate, or use two-sided smoothing. A zero-variance feature uses a scale of one.

Select each direct model's penalty by its own horizon's validation MAE. Select the shared one-session recursive model's penalty by equal-weight mean validation MAE across 5 and 20 sessions. Both strategies use the identical 20-close input window and the same four-penalty grid. Resolve exact ties by larger penalty. Train separate direct models for 5 and 20 sessions and one shared recursive model; roll the latter to both horizons. The 10-session horizon remains a future study task, although its date alignment is checked here. These rules were fixed before running the comparison; measured results are reported separately in Part 4.

All candidate lag counts use the same eligible fitting origins determined by the maximum 20-lag window for their particular target horizon. Require each training label to have matured by its fit cutoff; horizons can therefore have different training sample counts. A recursive training label is the next session's close. During a recursive forecast, append only the model's prediction, drop the oldest input, and repeat; never append an actual close after the origin. At the next real forecast origin, rebuild the window from observations then available. The model-based rollout trace is generated by scripts/train_ridge.py for Part 4; this script verifies date timing only.

## Calendar and common-origin rule

Use the union of CBOE_Index_Options and NYSE session dates as the audit timeline, but require agreement and an observed row throughout every retained input-to-target window. This conservative rule quarantines calendar disagreements rather than deciding them silently. Rows on closures in both calendars are unused. Missing-session values are never filled. Source data are unchanged. This is an explicit working analysis convention, not a verified historical VIX publication calendar; investigate remaining exceptions before final modeling and rerun these checks if the policy changes.

Use the same origins for every method, candidate lag count, and all three horizons. An evaluation origin is eligible only when its 20-lag input window and every session through its 20-session target are complete and undisputed, and all targets lie within the evaluation period. Allow the previous period's last session as the first origin (December 31, 2015 or December 31, 2020), after its close is available. Earlier observations may supply lag inputs. Tail origins whose 20-session target exceeds the evaluation end are excluded, even for shorter horizons. There are {config['common_origin_counts']['validation']} validation origins and {config['common_origin_counts']['reserved_test']} reserved-test origins per horizon under this rule. These are date-eligibility counts, not scored results. `eligible_origins.csv` and `excluded_origins.csv` provide the dated evidence.

## Dated input/target and label-maturity evidence

Example origin: December 31, 2015, after the close. Its 20 input closes span {sessions[i-19]} through {example_origin}, inclusive. The origin close is {development[example_origin]:g}. No January 2016 observation belongs to this input window.

Count the subsequent sessions: January 4, 5, 6, 7, and 8 give the five-session target January 8, 2016. January 15 is the tenth session. January 18 is a calendar closure, so February 1 is the twentieth session. `timing_example.csv` lists all 20 input dates and all 20 future session dates, with development CLOSE values, so the student can check the count manually. Explicit expected dates are asserted by the script; independent student hand verification is still required.

The December 31, 2015 origin's January 2016 labels are not available at the training cutoff and cannot enter training. Likewise, December 31, 2020 origins with January 2021 targets cannot enter the final refit. For each horizon, labels on the cutoff itself are mature; later labels are not. `label_maturity.csv` enumerates the final 35 calendar days of origins at both fitting boundaries, with target dates, maturity flags, and window completeness. Maturity and complete inputs are both required for fitting. The same maturity restriction applies before fitting scalers or tuning models.

## Overlapping outcomes and uncertainty (planned)

Daily rolling forecasts have overlapping outcome windows, so do not treat errors as independent or shuffle observations into folds. For final uncertainty, use a paired moving-block bootstrap over chronological origin-level absolute-error vectors, resampling the same blocks for every method and horizon. Use 2,000 replicates, seed 538, primary block length 20 origins, and sensitivity lengths 40 and 60. Form overlapping blocks only within uninterrupted runs of eligible calendar-session origins; never bridge an excluded gap. Sample blocks with replacement, concatenate and truncate to the original sample size, and calculate 95% percentile intervals for MAE and paired MAE differences. If no run supports a requested block length, report that setting as unavailable rather than silently shortening blocks. Dependence can extend beyond 20 sessions, which is why block-length sensitivity is required. No intervals have yet been calculated.

## Reproduction and status

Install `requirements-audit.txt`, then run `.venv/bin/python scripts/check_evaluation.py`. Inputs are the frozen CSV and installed market-calendar rules; the source SHA-256 is `{config['source_sha256']}`. Calendar package version: {config['calendar_version']}. Generated: {config['generated_utc']}.

`checks.json` records executed checks and fitting/eligibility counts. Companion CSVs contain the evidence cited above. Passing checks establish date ordering, label maturity, complete eligible windows, shared origins, and target-period containment. They do not establish predictive accuracy, validate a fitted scaler or recursive model implementation, or certify the calendar. Model fitting and results are generated separately in reports/ridge_validation for Part 4.

AI assistance: Codex wrote the timing checks and drafted this report. Automated assertions were run; the student must independently verify the example, assumptions, and eventual model implementation. Proposal-derived design and additional defaults are identified separately above.
'''
    (output / 'report.md').write_text(report)
    assert source.read_bytes() == blob
    print(json.dumps(config, indent=2))


if __name__ == '__main__':
    main()
