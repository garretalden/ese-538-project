#!/usr/bin/env python3
"""Train on 1990–2015; tune and score on 2016–2020. Never score final test.
Run: .venv/bin/python scripts/train_ridge.py
"""
import csv
import hashlib
import json
import os
from datetime import date, datetime, timezone
from importlib.metadata import version
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', '/tmp/ese538-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas_market_calendars as mcal
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from check_evaluation import complete_window, write_csv

ROOT = Path(__file__).resolve().parents[1]
HORIZONS = (5, 20)
LAG = 20
ALPHAS = (0.1, 1.0, 10.0, 100.0)
CUTOFF = date(2015, 12, 31)
END = date(2020, 12, 31)


def fit_model(x, y, alpha):
    return make_pipeline(StandardScaler(), Ridge(alpha=alpha, fit_intercept=True, solver='svd')).fit(x, y)


def rollout(model, inputs, steps=20):
    """Only origin inputs and the fitted model are accessible; raw-unit feedback."""
    window = np.array(inputs, dtype=float, copy=True)
    if window.ndim == 1:
        window = window[None, :]
    predictions = []
    for _ in range(steps):
        prediction = model.predict(window)
        predictions.append(prediction)
        window = np.column_stack((window[:, 1:], prediction))
    return np.column_stack(predictions)


def load_design():
    source = ROOT / 'data/VIX_History.csv'
    blob = source.read_bytes()
    with source.open() as stream:
        raw = list(csv.DictReader(stream))
    # Do not parse CLOSE for final test or excluded years.
    close = {}
    dates = []
    for row in raw:
        day = datetime.strptime(row['DATE'], '%m/%d/%Y').date()
        if day <= END:
            dates.append(day)
            close[day] = float(row['CLOSE'])
    assert dates == sorted(set(dates))
    assert all(np.isfinite(v) and v > 0 for v in close.values())
    calendars = [set(mcal.get_calendar(name).schedule(start_date='1990-01-01', end_date=END).index.date)
                 for name in ('CBOE_Index_Options', 'NYSE')]
    sessions = sorted(calendars[0] | calendars[1])
    available = set(close) & calendars[0] & calendars[1]
    validation = [i for i, d in enumerate(sessions) if d >= CUTOFF
                  and complete_window(sessions, available, i, LAG, 20)]
    assert all(CUTOFF < sessions[i+h] <= END for i in validation for h in HORIZONS)
    fitting = {h: [i for i in range(len(sessions))
                   if complete_window(sessions, available, i, LAG, h) and sessions[i+h] <= CUTOFF]
               for h in (1, 5, 20)}
    def inputs(indices):
        return np.array([[close[d] for d in sessions[i-LAG+1:i+1]] for i in indices])
    training = {h: (inputs(indices), np.array([close[sessions[i+h]] for i in indices]))
                for h, indices in fitting.items()}
    return source, blob, close, sessions, validation, fitting, training, inputs(validation)



def validation_table(metrics):
    lines = ['| Model | 5-day horizon | 20-day horizon |',
             '| --- | ---: | ---: |']
    for strategy, label in [('persistence', 'Persistence'), ('recursive', 'Recursive ridge'), ('direct', 'Direct ridge')]:
        values = [next(float(r['mae']) for r in metrics
                       if r['strategy'] == strategy and int(r['horizon']) == h) for h in HORIZONS]
        lines.append(f'| {label} | {values[0]:.6f} | {values[1]:.6f} |')
    return 'Validation MAE (VIX points); 1,240 common origins per horizon.\n\n' + '\n'.join(lines)


def main():
    output = ROOT / 'reports/ridge_validation'
    output.mkdir(parents=True, exist_ok=True)
    source, blob, close, sessions, origins, fitting, training, xv = load_design()
    # Cross-check against Part 3 evidence before scoring.
    with (ROOT / 'reports/evaluation_design/eligible_origins.csv').open() as stream:
        prior = {r['origin'] for r in csv.DictReader(stream) if r['period'] == 'validation'}
    assert prior == {sessions[i].isoformat() for i in origins}
    targets = {h: np.array([close[sessions[i+h]] for i in origins]) for h in HORIZONS}
    candidates, models, predictions = [], {}, {}
    for strategy, horizons in [('recursive', (1,)), ('direct', HORIZONS)]:
        for h in horizons:
            x, y = training[h]
            for alpha in ALPHAS:
                model = fit_model(x, y, alpha)
                np.testing.assert_allclose(model.named_steps['standardscaler'].mean_, x.mean(axis=0))
                assert model.named_steps['standardscaler'].n_samples_seen_ == len(x)
                key = (strategy, h, alpha)
                models[key] = model
                forecasts = rollout(model, xv) if strategy == 'recursive' else model.predict(xv)
                predictions[key] = forecasts
                scores = {k: float(np.mean(np.abs(targets[k] - (forecasts[:, k-1] if strategy == 'recursive' else forecasts))))
                          for k in (HORIZONS if strategy == 'recursive' else (h,))}
                candidates.append({'strategy': strategy, 'training_horizon': h, 'alpha': alpha,
                    'selection_mae': float(np.mean(list(scores.values()))),
                    'mae_5': scores.get(5, ''), 'mae_20': scores.get(20, ''),
                    'training_cases': len(x), 'validation_cases': len(origins)})
    selected = {}
    for strategy, h in [('recursive', 1), ('direct', 5), ('direct', 20)]:
        chosen = min((r for r in candidates if r['strategy'] == strategy and r['training_horizon'] == h),
                     key=lambda r: (r['selection_mae'], -r['alpha']))
        selected[(strategy, h)] = chosen['alpha']
    metrics, records = [], []
    for strategy in ('persistence', 'recursive', 'direct'):
        for h in HORIZONS:
            train_h = 1 if strategy == 'recursive' else h
            alpha = selected.get((strategy, train_h))
            pred = (xv[:, -1] if strategy == 'persistence' else
                    predictions[(strategy, train_h, alpha)][:, h-1] if strategy == 'recursive' else
                    predictions[(strategy, train_h, alpha)])
            assert np.isfinite(pred).all()
            metrics.append({'strategy': strategy, 'horizon': h, 'alpha': alpha,
                'lag': LAG if strategy != 'persistence' else 1, 'mae': float(np.mean(np.abs(pred-targets[h]))),
                'units': 'VIX points', 'cases': len(origins),
                'first_origin': sessions[origins[0]], 'last_origin': sessions[origins[-1]],
                'first_target': sessions[origins[0]+h], 'last_target': sessions[origins[-1]+h]})
            records.extend({'strategy': strategy, 'horizon': h, 'origin': sessions[i], 'target_date': sessions[i+h],
                            'actual': targets[h][j], 'prediction': pred[j], 'absolute_error': abs(pred[j]-targets[h][j])}
                           for j, i in enumerate(origins))
    for name, data in [('candidate_scores.csv', candidates), ('metrics.csv', metrics), ('predictions.csv', records)]:
        write_csv(output / name, data, list(data[0]))
    # Independently recompute from the serialized predictions, using Python scalars.
    with (output / 'predictions.csv').open() as stream:
        exported = list(csv.DictReader(stream))
    for metric in metrics:
        subset = [r for r in exported if r['strategy'] == metric['strategy'] and int(r['horizon']) == metric['horizon']]
        independent = sum(abs(float(r['prediction'])-float(r['actual'])) for r in subset)/len(subset)
        assert abs(independent-metric['mae']) < 1e-12
    model = models[('recursive', 1, selected[('recursive', 1)])]
    window = xv[0].copy()
    provenance = [str(d) for d in sessions[origins[0]-LAG+1:origins[0]+1]]
    trace = []
    for step in range(1, 21):
        prediction = float(model.predict(window[None, :])[0])
        trace.append({'origin': sessions[origins[0]], 'step': step, 'forecast_date': sessions[origins[0]+step],
                      'input_values': json.dumps(window.tolist()), 'input_sources': json.dumps(provenance),
                      'prediction': prediction})
        window = np.append(window[1:], prediction)
        provenance = provenance[1:] + [f'prediction_step_{step}']
    np.testing.assert_allclose([r['prediction'] for r in trace], rollout(model, xv[:1])[0])
    write_csv(output / 'recursive_trace.csv', trace, list(trace[0]))
    # Store fitted coefficients and training scalers as readable, portable evidence.
    parameters = {}
    for (strategy, h), alpha in selected.items():
        model = models[(strategy, h, alpha)]
        scaler, ridge = model.named_steps['standardscaler'], model.named_steps['ridge']
        parameters[f'{strategy}_{h}'] = {'alpha': alpha, 'mean': scaler.mean_.tolist(), 'scale': scaler.scale_.tolist(),
            'coefficient': ridge.coef_.tolist(), 'intercept': float(ridge.intercept_), 'training_cases': len(fitting[h])}
    metadata = {'source_sha256': hashlib.sha256(blob).hexdigest(), 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'versions': {name: version(name) for name in ('numpy', 'pandas', 'pandas_market_calendars', 'scikit-learn', 'matplotlib')},
        'lag': LAG, 'alpha_grid': ALPHAS, 'models': parameters,
        'verification': {'training_label_maturity': True, 'training_only_scalers': True,
            'part3_common_origins_match': True, 'exported_mae_recomputed': True, 'trace_matches_rollout': True},
        'final_test_evaluated': False}
    (output / 'run.json').write_text(json.dumps(metadata, indent=2)+'\n')
    fig, ax = plt.subplots(figsize=(7, 4.4))
    for strategy, color in [('persistence', '#666666'), ('recursive', '#176b9b'), ('direct', '#c05c21')]:
        values = [next(r['mae'] for r in metrics if r['strategy'] == strategy and r['horizon'] == h) for h in HORIZONS]
        ax.plot(HORIZONS, values, 'o-', label=strategy.capitalize(), color=color)
    ax.set(xlabel='Forecast horizon (trading sessions)', ylabel='Validation MAE (VIX points)',
           title='VIX validation accuracy: 2016–2020', xticks=HORIZONS)
    ax.grid(axis='y', alpha=.2)
    ax.legend()
    fig.text(.5, .015, f'Source: frozen Cboe CSV · {len(origins):,} common origins · penalties selected on validation', ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .05, 1, 1))
    fig.savefig(output / 'validation_mae.png', dpi=180)
    fig.savefig(output / 'validation_mae.svg')
    plt.close(fig)
    lines = '\n'.join(f"- {r['strategy'].capitalize()}, {r['horizon']} days: **{r['mae']:.6f} VIX points**; n={r['cases']:,}; alpha={r['alpha'] if r['alpha'] is not None else 'not applicable'}." for r in metrics)
    report = f'''# Part 4 — Working baseline and ridge validation

Three fitted ridge models produce four strategy/horizon results: one shared one-day recursive model rolled to 5 and 20 sessions, and two direct models. Persistence provides a parameter-free reference.

## Actual validation results

{validation_table(metrics)}

The training period is January 1990–December 2015. Validation targets lie within January 2016–December 2020, on the 1,240 common origins from Part 3. Exact origin/target ranges are in `metrics.csv`. Predictions use daily updated observed input windows but fixed training coefficients and scalers. There is no final refit or final-test evaluation.

## Selection and interpretation

Use 20 raw CLOSE inputs including the origin, standardized using each model's eligible training examples only. An intercept is fitted. Search alpha values 0.1, 1, 10, and 100. Select each direct model by its own horizon's MAE; select the shared recursive model by equal-weight mean MAE at 5 and 20. Exact ties prefer larger alpha. All candidate results are in `candidate_scores.csv`; these are validation-selected scores, not independent estimates from the reserved test. No uncertainty intervals or significance claims are made.

The calendar convention and exclusions from Part 3 are retained. Missing or disputed windows are excluded, observations on joint calendar closures are unused, and the raw CSV is unchanged. Training labels must mature by December 31, 2015; training sample counts differ by target horizon. No future observed values enter a recursive rollout: each predicted raw CLOSE is appended before the next step's fixed preprocessing.

## Evidence and reproduction

`predictions.csv` contains every dated actual, prediction, and absolute error. `recursive_trace.csv` records 20 steps at the first validation origin, including each input value and its observed-date or prediction-step provenance. `run.json` records selected model coefficients, training scalers, package versions, source checksum, and executed checks.

Install dependencies: `uv pip install --python .venv/bin/python -r requirements-modeling.txt`.

Run `.venv/bin/python scripts/check_evaluation.py`, then `.venv/bin/python scripts/train_ridge.py`. Run model tests with `.venv/bin/python -m unittest discover -s scripts -p test_ridge.py -v`. All reported MAEs are independently recomputed from the exported prediction file. Test output is saved in `verification.txt` when run.

AI assistance: Codex wrote the implementation and drafted this report. Automated checks were run; independent student review of the timing example and rollout trace remains required. Calendar rules remain an explicit working convention.
'''
    (output / 'report.md').write_text(report)
    assert source.read_bytes() == blob
    print(lines)


if __name__ == '__main__':
    main()
