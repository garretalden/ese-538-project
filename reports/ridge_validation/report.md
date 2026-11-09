# Part 4 — Working baseline and ridge validation

Three fitted ridge models produce four strategy/horizon results: one shared one-day recursive model rolled to 5 and 20 sessions, and two direct models. Persistence provides a parameter-free reference.

## Actual validation results

Validation MAE (VIX points); 1,240 common origins per horizon.

| Model | 5-day horizon | 20-day horizon |
| --- | ---: | ---: |
| Persistence | 2.355185 | 4.145597 |
| Recursive ridge | 2.349980 | 4.039266 |
| Direct ridge | 2.348840 | 4.033395 |

The training period is January 1990–December 2015. Validation targets lie within January 2016–December 2020, on the 1,240 common origins from Part 3. Exact origin/target ranges are in `metrics.csv`. Predictions use daily updated observed input windows but fixed training coefficients and scalers. There is no final refit or final-test evaluation.

## Selection and interpretation

Use 20 raw CLOSE inputs including the origin, standardized using each model's eligible training examples only. An intercept is fitted. Search alpha values 0.1, 1, 10, and 100. Select each direct model by its own horizon's MAE; select the shared recursive model by equal-weight mean MAE at 5 and 20. Exact ties prefer larger alpha. All candidate results are in `candidate_scores.csv`; these are validation-selected scores, not independent estimates from the reserved test. No uncertainty intervals or significance claims are made.

The calendar convention and exclusions from Part 3 are retained. Missing or disputed windows are excluded, observations on joint calendar closures are unused, and the raw CSV is unchanged. Training labels must mature by December 31, 2015; training sample counts differ by target horizon. No future observed values enter a recursive rollout: each predicted raw CLOSE is appended before the next step's fixed preprocessing.

## Evidence and reproduction

`predictions.csv` contains every dated actual, prediction, and absolute error. `recursive_trace.csv` records 20 steps at the first validation origin, including each input value and its observed-date or prediction-step provenance. `run.json` records selected model coefficients, training scalers, package versions, source checksum, and executed checks.

Install dependencies: `uv pip install --python .venv/bin/python -r requirements-modeling.txt`.

Run `.venv/bin/python scripts/check_evaluation.py`, then `.venv/bin/python scripts/train_ridge.py`. Run model tests with `.venv/bin/python -m unittest discover -s scripts -p test_ridge.py -v`. All reported MAEs are independently recomputed from the exported prediction file. Test output is saved in `verification.txt` when run.

AI assistance: Codex wrote the implementation and drafted this report. Automated checks were run; independent student review of the timing example and rollout trace remains required. Calendar rules remain an explicit working convention.
