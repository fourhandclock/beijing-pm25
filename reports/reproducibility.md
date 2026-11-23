# Reproducing the analysis and documents

Run commands from the repository root. Python **3.13.16** and the versions in
`requirements.lock` were used for verification. The package supports Python
3.11+, but that does not establish that every interpreter/OS combination works
with the recorded lock. The statistical design is fixed; reproduction verifies
its calculations without treating an already viewed test year as unseen.

## Environment and complete run

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python scripts/reproduce.py
```

The runner downloads/verifies the original archive and runs Stages 1–3 in order,
pytest, independent aggregation/model/extension checks, the AR(1) gap sensitivity,
result-preservation guards and the repository `verify` command. Each process has
a timeout. A failure stops the run; Ctrl-C cancels the active subprocess. Exact
commands, durations and output are written under `reports/reproduction/`, or a
location supplied with `--log-dir`. Historical verification evidence is retained
separately; current extension, preservation and document-check JSON records go
to `reports/verification/` rather than overwriting the Stage 4 evidence.

The document build has an optional, separate lock that includes the unchanged
scientific lock:

```bash
.venv/bin/python -m pip install -r requirements-submission.lock
.venv/bin/python scripts/reproduce.py --with-submission
```

To rebuild only the report and slides after a successful analysis:

```bash
.venv/bin/python -W error scripts/build_submission.py
.venv/bin/python -W error scripts/check_submission.py
```

The builder reads generated tables and uses the existing scientific figures.
Markdown/PDF report, PDF/PowerPoint slides and notes share their respective
content definitions. `submission/build_manifest.json` links numerical claims to
source rows and records input/output checksums. The document check inspects
those claims, PDF text/bounds, PowerPoint content/bounds and speaker notes.
Native PowerPoint rendering requires an Office-compatible viewer; the checked
PDF provides a portable presentation view.

## Original data and acquisition

Source: Chen, S. (2017), [Beijing Multi-Site Air Quality](https://doi.org/10.24432/C5RK5G),
UCI Machine Learning Repository, CC BY 4.0. The committed
[provenance](../data/raw/provenance.json) records the original acquisition,
license, station members and checksum. A fresh download must match:

```text
b04da438b2f331ac0ffd45aebdfec0d20d2367feb5f6948c4b1f7ce1191e33c4
```

The archive and processed CSVs are ignored by Git. Downloads preserve the
archive's bytes, verify/reuse an existing archive, and leave the committed
provenance unchanged when retrieving identical bytes. The download has network,
duration and size limits. No fabricated data replace a failed acquisition.
Installation and first acquisition need network access; subsequent analysis can
run offline.

A manually obtained original UCI wrapper or inner station ZIP can be imported:

```bash
.venv/bin/python -m beijing_pm25 download --import-archive /path/to/original.zip
```

A local import records its unverified download origin. Acquisition alone can
also run with the standard library using
`PYTHONPATH=src python3 -m beijing_pm25 download`.

## Individual checks and stale records

```bash
.venv/bin/python -m beijing_pm25 download
.venv/bin/python -W error -m beijing_pm25 stage1
.venv/bin/python -W error -m beijing_pm25 stage2
.venv/bin/python -W error -m beijing_pm25 stage3
.venv/bin/python -W error -m pytest -q
python3 scripts/verify_aggregation.py
.venv/bin/python -W error scripts/verify_models.py
.venv/bin/python -W error scripts/verify_extensions.py
.venv/bin/python -W error scripts/audit_ar1_calendar.py
.venv/bin/python scripts/check_frozen_stage2.py
.venv/bin/python scripts/check_stage3_preservation.py
.venv/bin/python -m beijing_pm25 verify
```

`verify` checks source, declared inputs, raw provenance and generated-artifact
hashes for recorded stages. `verify --stage 1`, `--stage 2` and `--stage 3` select
a stage and its prerequisites. In a fresh checkout, regenerate ignored processed
CSVs before interpreting a missing-file verification failure. After changing a
recorded source or input, rerun **Stage 1, then Stage 2, then Stage 3** to refresh
the dependency chain. The preservation guards check that the original frozen
Stage 2 evaluation and numerical Stage 3 results have not changed.

Daily files retain variable-specific counts, split/season labels and exclusion
reasons. Empty numeric cells mean missing values, not zeros. Units are µg/m³ for
PM2.5, °C for temperature/dew point, hPa for pressure, m/s for wind and mm/day
for rainfall under the interval-amount assumption. Use the complete calendar
for lags and ACFs: adjacent retained rows need not be consecutive days. Detailed
cleaning rules are in the [data audit](stage1_summary.md); inferential assumptions
and transformations are in the [statistical audit](stage4/statistical_audit.md).
