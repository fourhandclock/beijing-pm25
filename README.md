# Beyond R²: Beijing PM2.5

**Stages 1 and 2 are implemented and have been run on the original UCI data.** Start with the [regression analysis](reports/stage2_analysis.md), [data audit](reports/stage1_summary.md), and [Stage 2 checks](reports/stage2_checks.md). The user approved moving into the core regression stage after the initial data audit. Optional extensions remain outside this stage.

The audit proposes **Wanliu**, selected by training-period completeness. Of 1,461 calendar days, 1,441 meet the declared analysis requirements: **725 training, 359 validation, and 357 test days**. These counts describe data readiness, not model performance.

**Provisional submission deadline: 25 November 2026**, as instructed by the user on 19 November; the submission time is not yet specified. The core regression comparison, diagnostics and analysis report are complete. Prioritize preparing the concise submission report and presentation next. Optional EWMA/ridge extensions come after those deliverables and only if time permits.

The fixed validation rule selected **M3**, with final-test **MAE 46.785 µg/m³** and **RMSE 60.935 µg/m³** across 357 days; the training-mean baseline has MAE 55.297 and RMSE 73.006. Neither planned primary HAC joint test passes the prespecified Holm adjustment (both adjusted p = 0.0618). Residual dependence remains substantial, high days are underestimated, and three test estimates are negative. These limitations are part of the result, not observations removed to improve scores.

## Setup and commands

Run these commands from this directory. Python 3.13 was used for the recorded run.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m beijing_pm25 download
.venv/bin/python -m beijing_pm25 stage1
.venv/bin/python -m beijing_pm25 stage2
.venv/bin/python -m beijing_pm25 verify
.venv/bin/python -m pytest -q -W error
python3 scripts/verify_aggregation.py
.venv/bin/python -W error scripts/verify_models.py
```

`requirements.lock` pins the runtime and test versions actually used. For another supported Python version (3.11 or newer), `.venv/bin/python -m pip install -e '.[dev]'` resolves compatible packages from `pyproject.toml`; this may differ from the recorded environment. Package installation and downloading require network access. Tests, verification and rerunning the audit work offline once dependencies and raw data are present.

To use a manually downloaded original UCI archive:

```bash
.venv/bin/python -m beijing_pm25 download --import-archive /path/to/beijing-multi-site.zip
```

Acquisition preserves the archive's bytes. It never overwrites an existing archive; repeated downloads verify and reuse it. A local import is clearly labeled as having an unverified original download origin. The command supports both UCI's outer ZIP and the original inner station-data ZIP. It records the SHA-256, retrieval time, source URL, license and member list. No data are fabricated when acquisition fails.

Without the analysis packages, acquisition alone still works with the standard library:

```bash
PYTHONPATH=src python3 -m beijing_pm25 download
```

Both stages finish in seconds in the recorded environment. The audit processes one station's hourly data at a time; regression uses only the selected station's eligible daily observations. Network operations have socket, total-duration and size limits. Ctrl-C cancels work and marks an interrupted analysis run; raw inputs are preserved. A failed/interrupted run is not reported as complete by `verify`.

`verify` checks both existing stages by default. Use `verify --stage 1` for only the data audit, or `verify --stage 2` for the regression stage and its Stage 1 prerequisites. Adding analysis modules/dependencies changes the recorded source/environment inputs, so rerun Stage 1 before Stage 2 after a code update. The initial Stage 1 report and manifest are preserved under `reports/archive/`; the raw archive and cleaning rules are unchanged.

## Data and decisions

Source: Chen, S. (2017). [Beijing Multi-Site Air Quality](https://doi.org/10.24432/C5RK5G). UCI Machine Learning Repository, CC BY 4.0. The source describes hourly observations at 12 sites, March 2013–February 2017, with meteorology matched from nearby weather stations. See [UCI's documentation](https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data) and `data/raw/provenance.json`.

The rules are declared in [config/stage1.json](config/stage1.json) and the code:

- Separate complete hourly and daily calendars for each station. Reject duplicate timestamps, mixed station labels, malformed timestamps and malformed numeric values. Retain missing calendar dates.
- Daily means of PM2.5, temperature, pressure and wind speed require at least **18 valid hours** each. Means use each variable's own valid observations.
- Daily rainfall totals require **24 valid hours**; partial/all-missing sums remain missing. At least 18 hours must also have all five core fields jointly observed for a day to enter analysis.
- Mask and count nonfinite values, negative pollutant/rain/wind measurements, nonpositive pressure and invalid wind directions. Preserve valid negative temperatures, zeros and high positive concentrations. Do not impute or remove unexplained extremes.
- Treat timestamps as local civil time, assumed Asia/Shanghai; the source page does not explicitly specify a timezone. Treat rainfall entries as hourly interval amounts when forming totals; this instrument interpretation is an assumption.
- Training: **2013-03-01 ≤ date < 2015-03-01**. Validation: **2015-03-01 ≤ date < 2016-03-01**. Test: **2016-03-01 ≤ date < 2017-03-01**.
- Select the station by eligible training-day count, then valid training PM2.5-hour count, then alphabetical name. Concentration levels and future coverage do not enter selection. All Stage 1 figures and response summaries use training observations only. Stage 2 diagnostic figures use training data; validation/test plots are labeled and the final test is evaluated only after freezing the selected model.

To change a declared rule, copy/edit the JSON configuration and record the reason before rerunning:

```bash
.venv/bin/python -m beijing_pm25 stage1 --config config/alternative.json
```

Configurations must remain inside the project. The default run is replaced only in generated directories, never in `data/raw/`. Keep separate project copies if comparing configurations. `verify` checks raw provenance, the configuration, recorded environment-lock inputs, analysis code and generated-artifact hashes; it detects stale results after edits.

## Outputs and code

| Path | Purpose |
| --- | --- |
| `data/raw/uci_beijing_multi_site.zip` | Original UCI wrapper, unchanged; auxiliary example CSVs are ignored |
| `data/raw/provenance.json` | Dataset source, retrieval details, citation and checksum |
| `data/processed/Wanliu_daily.csv` | All 1,461 dates, per-variable counts, split/season labels, eligibility and exclusion reasons |
| `data/processed/Wanliu_analysis_ready.csv` | The 1,441 eligible dates, preserving the same labels and counts |
| `results/tables/station_audit.csv` | Every station, training selection rank, availability and member checksum |
| `results/tables/hourly_missingness.csv` | Missing, absent and invalid cells by station, variable and interval |
| `results/tables/daily_completeness.csv` | Retained/excluded days by station and interval; exclusion categories can overlap |
| `results/tables/timestamp_gaps.csv` | Contiguous missing-hour ranges; header only when none exist |
| `results/tables/training_response_summary.csv` | Training-only original/log1p distributions; no response scale has been selected |
| `results/tables/training_calendar_acf.csv` | Paired-day lag correlations and sample sizes, preserving missing dates |
| `results/figures/` | Six scientific figures, each as PNG and SVG |
| `results/stage1_run.json` | Completion status, exact command/configuration, environment, retention and input/code/output hashes |
| `reports/stage1_summary.md` | Findings, cleaning decisions, limitations and next-stage proposal |
| `reports/implementation_checks.md` | Checks actually executed and their outcomes |
| `src/beijing_pm25/` | Acquisition, validation, aggregation, descriptions, plotting, report and CLI modules |
| `tests/` | Synthetic correctness fixtures; never presented as real observations |
| `scripts/verify_aggregation.py` | Independent standard-library check of the real-data ranking and selected daily aggregates |

Stage 2 adds these separate artifacts:

| Path | Purpose |
| --- | --- |
| `reports/stage2_protocol.md` | Response scale, hypotheses, inference and evaluation rules recorded before fitting |
| `config/stage2.json` | Fixed inference bandwidths, validation tolerance and training quantile |
| `results/stage2/frozen_model.json` | Selected model, training-only coefficients/means/baseline/cutoff, persisted before final test evaluation |
| `results/stage2/model_parameters.json` | Coefficients and exact design columns for all three training fits |
| `results/stage2/tables/model_fit.csv` | Training fit, common sample sizes, rank, conditioning and working AIC/BIC |
| `results/stage2/tables/coefficients.csv` | Classical t-based and primary HAC normal-approximation uncertainty for every coefficient |
| `results/stage2/tables/nested_anova.csv` | The two ordinary nested-model partial F comparisons, with assumed iid reference |
| `results/stage2/tables/hac_joint_tests.csv` | Joint chi-square Wald tests at 7/14/30 calendar-day bandwidths and primary Holm-adjusted p-values |
| `results/stage2/tables/hac_covariances.csv` | Every covariance entry, exposed for independent verification |
| `results/stage2/tables/residual_diagnostics.csv` | Dependence, heteroscedasticity, residual shape and influence summaries with calibration caveats in the report |
| `results/stage2/tables/training_influence.csv` | All training dates, leverage, internal studentization and Cook's distance; no automatic exclusions |
| `results/stage2/tables/training_residual_calendar.csv` | All training calendar dates, with omitted residuals left missing |
| `results/stage2/tables/training_residual_acf.csv` | Calendar-lag residual correlations and pair counts |
| `results/stage2/tables/m3_seasonal_wind_slopes.csv` | Seasonal wind associations and linear-contrast intervals |
| `results/stage2/tables/validation_selection.csv` | Candidate validation errors and the fixed 1% simplicity rule |
| `results/stage2/tables/performance.csv` | Training/validation/frozen-test errors, signed bias, high-day counts and negative estimates |
| `results/stage2/tables/predictions.csv` | Date-labeled estimates; final test includes only the chosen model and training-mean baseline |
| `results/stage2/figures/` | Nine standalone scientific figures, each as PNG and SVG |
| `results/stage2/run.json` | Completion status, configuration, dependencies, frozen model and input/code/output hashes |
| `reports/stage2_analysis.md` | Empirical findings, interpretation and limitations |
| `reports/stage2_checks.md` | Executed tests, real-data run and independent oracle outcomes |
| `scripts/verify_models.py` | Independent QR-based OLS/F/HAC/Wald/influence/performance verification, without project or statsmodels imports |

`pm25` is in µg/m³, `temperature` in °C, `pressure` in hPa, `wind_speed` in m/s, and `rainfall` in mm/day under the interval-amount assumption. Daily files include `n_*`, `n_joint_core_hours`, `hours_observed`, `analysis_eligible` and `exclusion_reason`. Empty daily numeric cells mean missing values, not zeros. Keep the full-calendar file for future lag/ACF work; do not treat adjacent rows in the filtered file as necessarily consecutive days.

## Interpretation and next stage

This is an observational, contemporaneous explanatory investigation. A same-day estimate using observed weather is not an advance forecast. Daily aggregation does not establish independence. The original response scale was chosen before fitting to keep coefficients interpretable in µg/m³; marginal skewness alone does not impose a log transform. The ordinary OLS and HAC covariance estimates are distinguished in every inferential table. Calendar gaps are preserved in HAC score products, residual ACFs and the serial diagnostic.

M3's training R² is 0.221 and adjusted R² is 0.211; residual lag-one correlation is 0.512. This is a limited explanatory model with remaining dependence, skewness and unequal-variance evidence, not a claim that all OLS assumptions hold. The two best validation MAEs differ by only 0.556 µg/m³, so selection is sensitive to a small improvement around the declared tolerance. Test signed error is +15.283 µg/m³ overall, but −160.945 on 17 high days defined by the training-only 234.655 µg/m³ cutoff. Statistical associations, inferential evidence and chronological estimation performance answer different questions.

The next deliverable is the concise submission report and presentation using these findings. EWMA bias correction, response-scale sensitivity, ridge and additional stations have not been started. Future adaptations after inspecting this test must be labeled exploratory. Plan against the provisional 25 November 2026 deadline above; no submission time has been confirmed.
