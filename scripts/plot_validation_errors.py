#!/usr/bin/env python3
"""Plot saved 20-day direct ridge validation errors; no model retraining.
Run: .venv/bin/python scripts/plot_validation_errors.py
"""
import csv
import os
from datetime import date
from pathlib import Path

os.environ.setdefault('MPLCONFIGDIR', '/tmp/ese538-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / 'reports/ridge_validation'
    with (output / 'predictions.csv').open() as stream:
        rows = [r for r in csv.DictReader(stream)
                if r['strategy'] == 'direct' and int(r['horizon']) == 20]
    if not rows:
        raise ValueError('No 20-day direct ridge predictions; run scripts/train_ridge.py first.')
    rows.sort(key=lambda r: r['target_date'])
    dates = [date.fromisoformat(r['target_date']) for r in rows]
    errors = [float(r['prediction']) - float(r['actual']) for r in rows]
    assert len(dates) == len(set(dates)), 'Duplicate target dates'
    assert all(date(2016, 1, 1) <= d <= date(2020, 12, 31) for d in dates)
    assert all(abs(abs(e) - float(r['absolute_error'])) < 1e-10 for e, r in zip(errors, rows))
    with (output / 'direct_20_errors.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['origin', 'target_date', 'prediction', 'actual', 'signed_error'])
        writer.writerows([r['origin'], r['target_date'], r['prediction'], r['actual'], e]
                         for r, e in zip(rows, errors))
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.plot(dates, errors, color='#176b9b', linewidth=.8)
    ax.axhline(0, color='#555555', linewidth=.9, linestyle='--')
    ax.set(title='20-day direct ridge: validation forecast errors over time',
           xlabel='Target calendar date', ylabel='Predicted − observed VIX (points)')
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.grid(axis='y', alpha=.2)
    fig.text(.5, .025,
             f'Source: saved validation predictions · n={len(rows):,} · Positive = overprediction; negative = underprediction',
             ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .055, 1, 1))
    for extension in ('png', 'svg'):
        fig.savefig(output / f'direct_20_errors.{extension}', dpi=180)
    plt.close(fig)
    print(f'Generated signed-error plot and CSV for {len(rows):,} validation predictions in {output}')


if __name__ == '__main__':
    main()
