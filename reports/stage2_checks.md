# Stage 2 implementation and numerical checks

Stage 2 was implemented after the Stage 1 audit was reviewed, with the response, regressors, covariance bandwidths, multiplicity adjustment and selection rule recorded in `stage2_protocol.md` before the first empirical fit. This section records the historical Stage 2 checks; the subsequent numerical audit is in `stage4_verification.md` and current document checks are in `stage5_refinement.md`.

## Environment and executed commands

Python 3.13.16, NumPy 2.5.5, pandas 2.3.3, SciPy 1.18.1, statsmodels 0.15.0, Matplotlib 3.11.2 and pytest 9.2.0. All resolved runtime/test dependencies are pinned in `requirements.lock`.

Run from the project directory:

```bash
.venv/bin/python -m pip --disable-pip-version-check --no-cache-dir install --timeout 20 --retries 1 -e '.[dev]'
.venv/bin/python -m pytest -q -W error --tb=short
.venv/bin/python -W error -m beijing_pm25 stage1
.venv/bin/python -W error -m beijing_pm25 stage2
.venv/bin/python -W error scripts/verify_models.py
.venv/bin/python -m beijing_pm25 verify
```

The existing Stage 1 source archive was reused, not downloaded again or overwritten. The initial Stage 1 report and manifest were saved in `reports/archive/` before refreshing code/environment references. Later reruns reproduced the same declared models and scores; no response, feature, cutoff, tolerance or inference-bandwidth decision was changed in response to final-test results.

## Automated tests

**58 passed, with warnings treated as errors** (10.65 seconds in the final recorded full-suite check).

The original 38 acquisition/aggregation tests remain. Twenty Stage 2 cases add these checks:

- All three OLS solutions and both partial F calculations agree with independent least squares and the F survival function. Mean centering preserves fitted values in all three nested model families.
- Calendar-aware HAC agrees with statsmodels on uninterrupted calendars at lags 0, 3 and 7. A hand-calculated intercept-only example with a missing date distinguishes calendar lags from compressed-row lags. Misaligned dates are rejected.
- Joint Wald statistics agree with direct restriction calculations. The primary two-hypothesis Holm family is separated from bandwidth sensitivities. Covariances are positive semidefinite in the fixture, and seasonal wind contrasts use the correct coefficients.
- The serial auxiliary regression uses actual calendar lags and has the independently counted number of eligible rows.
- Validation selection respects the 1% simplicity rule and rejects test-labeled scores. Test response/weather changes cannot update frozen training means, thresholds or coefficients. Only the chosen model and fixed mean baseline are scored on test dates.
- Error signs, negative predictions and empty high-day subgroups are handled explicitly. Configuration choices outside the implemented original-scale specification are rejected.
- A complete offline workflow uses an explicitly synthetic hourly station, creates both stages and all figure types, and verifies that `frozen_model.json` exists with exactly the evaluated specification before test evaluation is called. It preserves the raw bytes, retains missing calendar dates, detects artifact tampering, and marks an intentionally failed rerun as failed instead of leaving a stale complete status.

Synthetic test fixtures are never substituted for the original dataset or presented as empirical findings.

## Original-data results

All fits use the same **725 Wanliu training days**; validation has 359 days and final test has 357 days. Matrix ranks are 5/8/11 for M1/M2/M3. The fixed validation MAE rule chooses **M3**.

| Quantity | Result |
| --- | --- |
| M3 training R² / adjusted R² | 0.221460 / 0.210556 |
| M3 final-test MAE / RMSE | 46.784656 / 60.934771 µg/m³ |
| Training-mean baseline test MAE / RMSE | 55.297393 / 73.005863 µg/m³ |
| M3 overall mean signed test error | +15.283401 µg/m³ |
| Training daily 95th-percentile cutoff | 234.654545 µg/m³ |
| High test days / mean signed high-day error | 17 / −160.944617 µg/m³ |
| Negative M3 test estimates retained | 3 |
| M3 lag-one training residual correlation | 0.511654 (719 calendar pairs) |
| Primary HAC joint p-values: H1 / H2 | 0.035939 / 0.030923 |
| Primary Holm-adjusted p-values: H1 / H2 | 0.061845 / 0.061845 |

The adjusted tests do not cross alpha 0.05; this is insufficient evidence against the planned joint nulls under that rule, not proof of zero seasonal relationships. The fitted errors remain dependent, right-skewed and variable in spread. These are reported model limitations, not occasions to remove observations or retune against test scores.

Stage 2 produces **35 hashed artifacts**: fourteen CSV tables, the frozen model, all-model parameters, eighteen figure exports (nine PNG + nine SVG), and the generated analysis report. Both stages run with warnings treated as errors. The `verify` command checks Stage 1 prerequisites plus Stage 2 source/configuration/protocol inputs and every generated artifact. Failed/interrupted runs cannot pass this verification.

## Independent empirical oracle

`scripts/verify_models.py` imports neither statsmodels nor the project's analysis helpers. It reads the saved daily CSV with the standard library, independently builds the design matrices and training means, and solves using SciPy's pivoted-QR least squares rather than the production fit's SVD route.

The independent calculation matches:

- All **three** coefficient vectors, both nested F statistics/p-values, and all **nine** HAC covariance matrices. The HAC oracle pairs observed dates explicitly instead of using the production score-padding algorithm.
- All six joint Wald statistics/p-values and the step-down Holm adjustment for the two primary hypotheses.
- Leverage and Cook's distance on every training date, the calendar-lag serial auxiliary sample/statistic, Koenker/Breusch–Pagan statistics and moment-based Jarque–Bera statistics.
- Training-only means/cutoff, the validation choice, all **5,050** saved estimates and their error signs, every overall/high/below-cutoff MAE/RMSE/mean signed error, subgroup sizes and negative-estimate counts.
- The absence of unselected candidate test predictions and the unchanged original raw-archive checksum.

The oracle saves its run hash, script hash, timestamp and result to `independent_model_check.json`. Numerical agreement checks implementation; it does **not** validate observational causal assumptions, diagnostic-test calibration under dependence, or future generalization.

The residual and final-test PNG exports were visually inspected for readable labels, units, calendar alignment and visible negative estimates/extreme-day failures. Training correlations, residual time/ACF, wind intervals and validation comparison are exported alongside the full diagnostic panels. The next practical step is the submission report/presentation; optional EWMA, ridge and other-station work remains deferred. No commits, pushes, pull requests or publication were performed.
