# Implementation checks — Stage 1

The checks below were actually executed in the project virtual environment. Synthetic test fixtures and the original empirical UCI dataset are kept separate.

## Environment and acquisition

- Python 3.13.16; pandas 2.3.3; NumPy 2.5.5; Matplotlib 3.11.2; pytest 9.2.0. Exact transitive runtime/test versions are in `requirements.lock`.
- The initial restricted-network request could not resolve UCI. The authorized direct download succeeded; `data/raw/provenance.json` records the resolved original source, access time, original-byte hash and size. The data were not reconstructed or replaced with example rows.
- The original wrapper contains a nested station ZIP, an image and auxiliary `data.csv`/`test.csv`. Only the 12 original station CSVs enter the analysis.

Successful setup/acquisition commands, run from `beijing-pm25/`:

```bash
python3 -m venv .venv
env PYTHONPATH=src python3 -m beijing_pm25 download --timeout 20
.venv/bin/python -m pip --disable-pip-version-check --no-cache-dir install --timeout 20 --retries 1 -e '.[dev]'
```

The local acquisition command also supports a genuinely offline import. Tests verify that imports preserve the exact bytes and are labeled with an unverified original download origin.

## Automated correctness tests

```bash
.venv/bin/python -m pytest -q -W error
```

**Result: 38 passed**, with warnings treated as errors (3.26 seconds in the recorded check).

The tests cover independently computed daily means and rainfall totals; 17/18-hour boundary behavior; partial/all-missing rainfall; complete-calendar alignment after a missing day; joint-hour completeness; mixed-station rejection; duplicate-hour rejection; malformed numeric/calendar fields; masking/counting invalid values while retaining extremes and negative temperatures; sorting unordered input; chronological boundaries; leap day and seasonal labels; station selection using training coverage only; deterministic ties; gap-preserving calendar correlations checked against Python's standard-library correlation; training-only response summaries; immutable acquisition; nested archive handling; raw tamper detection; failed-import cleanup; a complete offline two-station run with actual figures; and changed-output detection.

## Original-data run and independent verification

```bash
.venv/bin/python -W error -m beijing_pm25 stage1
.venv/bin/python -m beijing_pm25 verify
python3 scripts/verify_aggregation.py
```

- Full audit: **12 stations, 420,768 source hourly rows**. Each station has 35,064 unique, regularly aligned hourly records. No absent timestamp rows or duplicate timestamps were found. Missing measurement cells remain present and are audited separately.
- Wanliu ranks first with **725 eligible training days**. The full-calendar file has 1,461 dates; the analysis file has **1,441 days**, with 20 excluded. Eligible split counts are 725 training, 359 validation, 357 test.
- The pipeline completed with warnings treated as errors. It generated **21 hashed artifacts**: six audit/description tables, two daily datasets, twelve figure files (six PNG + six SVG), and the Stage 1 report. Exact command, source/configuration hashes, versions and runtime are in `results/stage1_run.json`.
- `verify` passed for the preserved raw archive and provenance, recorded configuration/lock/handoff inputs, current analysis modules, and all 21 generated outputs.
- The independent oracle uses only `csv`, `datetime`, `statistics` and other standard-library utilities. It re-reads the original archive independently of the pandas loader, matches the full 12-station training ranking/counts, and checks **all 1,461 selected-station dates**, their means, rainfall totals, valid-hour counts, joint counts, split labels and eligibility. **Passed**; see `independent_aggregation_check.json`.
- All six PNG figures were visually inspected for readable labels, dates, counts and retained extremes. Figures use training data only. Tiny nonzero missingness percentages are labeled `<0.1%` rather than displayed as zero.

The response's lag-one training correlation is descriptive, not a test on regression residuals. No regression, ANOVA, robust coefficient test, holdout error or adaptive-correction result was computed. No commits, pushes, pull requests, publication or upload was performed.
