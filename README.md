# VIX forecasting baseline — ESE 538

Compare persistence, recursive ridge, and direct ridge at 5- and 20-trading-session horizons. Train on 1990–2015; select penalties and evaluate on 2016–2020. The 2021–2025 test period remains reserved; exclude 2026. 

## Setup

Use Python 3.12 (the recorded run used 3.12.7). From this directory:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-modeling.txt
```

The modeling requirements also cover the audit and evaluation scripts. Dependencies are pinned; a fresh-environment reproduction has not yet been verified.

## Data access

Obtain the daily VIX historical CSV from [Cboe](https://www.cboe.com/tradable-products/vix/vix-historical-data/) and save it as `data/VIX_History.csv`. Required columns: DATE, OPEN, HIGH, LOW, CLOSE.

The recorded snapshot was downloaded October 16, 2026, and spans January 2, 1990–October 16, 2026. Its SHA-256 is:

```text
a9742d4deab98f7644bda10df92db0b6afbca17ccc8b64139c52ad2ca0963d42
```

Exact reproduction requires that snapshot. A current download may contain additions or revisions; check the checksum recorded by the audit. Raw data are excluded from Git; retain the snapshot locally and follow applicable redistribution terms.

## Reproduce

Run in order:

```sh
.venv/bin/python scripts/audit_vix.py
.venv/bin/python scripts/check_evaluation.py
.venv/bin/python scripts/train_ridge.py
.venv/bin/python scripts/plot_validation_errors.py
.venv/bin/python -m unittest discover -s scripts -p 'test_*.py' -v
```

## Outputs and interpretation

- `reports/data_audit/`: report, quality issues, and calendar comparisons.
- `reports/evaluation_design/`: timing example, label maturity, and eligible/excluded origins.
- `reports/ridge_validation/`: MAE report, candidate scores, predictions, plot, recursive trace, and fitted parameters/version metadata.

Scripts regenerate reports and evidence; saved `verification.txt` files document prior test runs and are not automatically refreshed by these commands. Calendar exclusions are documented working assumptions. Validation scores informed penalty selection; they are not final-test estimates. `archive/` preserves earlier feasibility work and is unnecessary for reproduction.
