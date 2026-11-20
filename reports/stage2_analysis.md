# Stage 2 — regression, seasonal tests and model adequacy

**Wanliu; original-scale daily PM2.5; completed on the original UCI dataset.** Model decisions follow the [protocol](stage2_protocol.md), written before the first empirical fit. The user approved this stage. The provisional submission deadline is 25 November 2026.

## Main findings

The validation rule selected **M3**. Its frozen final-test MAE is **46.785 µg/m³** and RMSE is **60.935 µg/m³**, across 357 eligible days. The training-mean baseline has MAE 55.297 and RMSE 73.006; the selected model's relative MAE reduction is 15.4% (negative would indicate worse performance).

- **H1_season**: primary calendar-HAC Wald χ²(3) = 8.548, p = 0.0359; Holm-adjusted p = 0.0618. At alpha 0.05, this is insufficient evidence against this joint null.
- **H2_wind_by_season**: primary calendar-HAC Wald χ²(3) = 8.881, p = 0.0309; Holm-adjusted p = 0.0618. At alpha 0.05, this is insufficient evidence against this joint null.
- The selected model's lag-one training residual correlation is 0.512. This quantifies remaining temporal structure; the diagnostic p-values below have assumptions and are not an independence certificate.
- On the 17 final-test high-pollution days, mean prediction minus observation is -160.945 µg/m³, indicating average underestimation in this subgroup. High-day RMSE is 173.583; the signed error, rather than RMSE alone, supplies the direction.

The overall signed error is 15.283 µg/m³ (positive means average overestimation), so the aggregate bias can have a different direction from the high-day bias. There are **3 negative test estimates**, a physical limitation of this unrestricted linear model; they remain in the reported errors.

These are conditional associations and same-day estimates using observed weather. They do not establish causal effects or advance-forecasting skill.

## Sample and fixed specifications

All candidates use the same **725 eligible training dates**, from the Stage 1 calendar 2013-03-01 to 2015-03-01 exclusive. There are 359 eligible validation dates and 357 eligible test dates. The original 18-hour mean/joint-completeness and complete-24-hour rainfall rules are unchanged; excluded dates are not silently joined for time diagnostics.

The response remains µg/m³. Training marginal skewness supported considering log1p, but a nonnormal marginal response is not itself a violation of the normal conditional-error assumption. The protocol fixes the original scale to preserve direct interpretation; no log model was fit or chosen based on these results.

Training-only centering constants are: temperature = 13.5128, wind_speed = 1.5212, rainfall = 1.4185, pressure = 1010.6528. Units remain °C, m/s, mm/day and hPa. Centering changes coefficient interpretation and numerical scaling, not fitted values or the model family. Winter is the reference season.

- **M1:** intercept + centered temperature, wind speed, rainfall and pressure.
- **M2:** M1 + three seasonal indicators.
- **M3:** M2 + three season × centered-wind interactions.

All matrices are checked for full rank. Numerical conditioning is reported separately from coefficient uncertainty; full rank is not evidence that statistical estimates are precise.

## Fitted comparison and planned joint hypotheses

| Model | n | Parameters | R² | Adjusted R² | Residual SD | AIC* | BIC* |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M1 | 725 | 5 | 0.198 | 0.194 | 61.592 | 8037.2 | 8060.1 |
| M2 | 725 | 8 | 0.213 | 0.206 | 61.132 | 8029.3 | 8066.0 |
| M3 | 725 | 11 | 0.221 | 0.211 | 60.950 | 8027.9 | 8078.4 |

R² and adjusted R² describe fit to training observations. They do not estimate future accuracy. *AIC/BIC are working Gaussian/iid likelihood criteria on the same response/sample; remaining dependence limits their usual interpretation.*

| Question | Comparison | SSE reduction | Added df | F | Classical p* |
| --- | --- | --- | --- | --- | --- |
| H1_season | M1 → M2 | 51786.8 | 3 | 4.619 | 0.00329 |
| H2_wind_by_season | M2 → M3 | 27151.2 | 3 | 2.436 | 0.0636 |

The ordinary partial F-test uses the SSE decrease per added parameter relative to the full model's residual mean square. Its exact reference distribution assumes a correctly specified linear conditional mean with independent, homoscedastic Gaussian errors; large-sample approximations have their own conditions. Serial dependence, unequal variance or nonnormal errors can make nominal p-values misleading; they are not the sole inferential conclusion. [Statsmodels F-test documentation](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.compare_f_test.html).

| Question | HAC days | Wald χ² | df | HAC p | Primary Holm p |
| --- | --- | --- | --- | --- | --- |
| H1_season | 7 | 8.548 | 3 | 0.0359 | 0.0618 |
| H1_season | 14 | 8.704 | 3 | 0.0335 | NA |
| H1_season | 30 | 7.897 | 3 | 0.0482 | NA |
| H2_wind_by_season | 7 | 8.881 | 3 | 0.0309 | 0.0618 |
| H2_wind_by_season | 14 | 9.692 | 3 | 0.0214 | NA |
| H2_wind_by_season | 30 | 9.549 | 3 | 0.0228 | NA |

HAC uses Bartlett weights, a primary 7-calendar-day bandwidth, prespecified 7, 14, 30-day sensitivities, and n/(n−p) correction. Omitted dates contribute zero scores, preserving calendar-day separations without inventing responses. The reported Wald reference is asymptotic χ², not the classical nested F distribution. The two primary joint p-values receive Holm adjustment; the bandwidth sensitivities are descriptive checks. HAC cannot repair a misspecified mean, informative missingness, endogeneity or instability. [HAC reference](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html).

## Coefficients and interpretation

| M2 term | Estimate | HAC SE | HAC interval | Unadjusted HAC p |
| --- | --- | --- | --- | --- |
| Intercept | 104.942 | 10.924 | [83.532, 126.352] | 7.48e-22 |
| temperature_c | -2.483 | 0.766 | [-3.985, -0.982] | 0.00119 |
| wind_speed_c | -49.030 | 4.376 | [-57.608, -40.453] | 3.92e-29 |
| rainfall_c | -0.203 | 0.429 | [-1.043, 0.637] | 0.636 |
| pressure_c | -2.246 | 0.623 | [-3.467, -1.026] | 0.00031 |
| season_spring | -3.451 | 11.446 | [-25.885, 18.984] | 0.763 |
| season_summer | -33.747 | 17.362 | [-67.776, 0.282] | 0.0519 |
| season_autumn | -19.041 | 13.289 | [-45.086, 7.004] | 0.152 |

These M2 intervals use the primary HAC covariance and a normal approximation at 95% individual coverage; coefficient p-values are unadjusted. Full ordinary t-based and HAC tables for **all three models** are in `results/stage2/tables/coefficients.csv`. Statistical evidence for a joint seasonal term does not establish every individual seasonal contrast.

For M2, a weather coefficient is an estimated µg/m³ difference associated with one unit higher weather value, conditional on the other listed predictors and season. A seasonal coefficient compares that season with winter under the common wind slope. With interactions in M3, seasonal offsets are evaluated at the training mean wind speed, and its base wind coefficient is the winter slope.

For example, M2's wind coefficient is -49.030: a 1 m/s higher daily wind speed is associated with that many µg/m³ difference in fitted PM2.5, holding the other listed predictors and season fixed. Its individual primary HAC interval is [-57.608, -40.453]. This conditional association is not a causal claim about an intervention.

| Season | M3 wind slope | HAC interval |
| --- | --- | --- |
| winter | -52.119 | [-66.716, -37.522] |
| spring | -47.098 | [-60.869, -33.326] |
| summer | -17.138 | [-38.795, 4.519] |
| autumn | -57.921 | [-78.256, -37.586] |

M3 slopes are changes in fitted µg/m³ per 1 m/s higher wind speed, conditional on the other predictors. Each interval uses the full linear-contrast covariance, including covariance between the baseline wind slope and interaction. These are individual uncertainty intervals, not simultaneous intervals or causal intervention effects.

## Residual adequacy and influence

| Model | Lag-1 residual r | BG-style LM p* | Aux n | Koenker BP p* | Residual skew | Cook flags |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | 0.527 | 3.66e-45 | 683 | 2.16e-07 | 1.297 | 30 |
| M2 | 0.517 | 1.64e-43 | 683 | 3.48e-06 | 1.310 | 40 |
| M3 | 0.512 | 5.72e-43 | 683 | 7.84e-05 | 1.317 | 40 |

The calendar ACF retains missing daily positions. The BG-style check regresses the fitted residual on the original regressors and the preceding 7 calendar-day residuals, dropping only auxiliary rows missing one of those lags; the smaller auxiliary n is explicit. Its LM statistic is n_aux × R² with an approximate χ² reference. This complete-case variant is documented in the protocol, rather than applying row-based lags across missing dates. [BG auxiliary-regression reference](https://www.statsmodels.org/stable/generated/statsmodels.stats.diagnostic.acorr_breusch_godfrey.html).

*The serial auxiliary F, Koenker/Breusch–Pagan and Jarque–Bera reference p-values also have assumptions; temporal dependence and missingness can affect their calibration. Koenker's variant relaxes normality, not independence. Interpret them alongside the scatter, Q–Q and ACF patterns and the magnitude of residuals.* Full statistics, residual skewness/kurtosis, screening counts and auxiliary sample sizes are saved in `residual_diagnostics.csv`. [Breusch–Pagan assumptions](https://www.statsmodels.org/stable/generated/statsmodels.stats.diagnostic.het_breuschpagan.html).

The five largest Cook's distances for M3 are:

| Date | Observed | Fitted | Residual | Leverage | Cook's distance |
| --- | --- | --- | --- | --- | --- |
| 2013-08-11 | 128.625 | 69.609 | 59.016 | 0.313 | 0.056 |
| 2013-11-27 | 9.250 | -66.997 | 76.247 | 0.170 | 0.035 |
| 2013-07-01 | 225.542 | 89.262 | 136.280 | 0.062 | 0.032 |
| 2014-11-30 | 96.167 | -13.507 | 109.674 | 0.078 | 0.027 |
| 2014-10-09 | 354.217 | 137.546 | 216.672 | 0.018 | 0.021 |

No flagged day was removed. Cook > 4/n, leverage > 2p/n and |internally studentized residual| > 3 are screening guides. They identify observations to inspect, not proven errors or emissions events. A Q–Q plot assesses error-distribution shape; it does not check temporal independence.

## Chronological selection and held-out estimates

| Model | Parameters | Validation n | MAE | RMSE | Within tolerance | Chosen |
| --- | --- | --- | --- | --- | --- | --- |
| M1 | 5 | 359 | 52.025 | 65.519 | False | False |
| M2 | 8 | 359 | 50.660 | 64.579 | False | False |
| M3 | 11 | 359 | 50.104 | 64.171 | True | True |

The selection rule uses only overall validation MAE. Models within 1% of its minimum are compared by parameter count, then MAE, then name. Inferential p-values, AIC/BIC and final-test scores do not select the model. Validation is therefore a development interval, not a second untouched performance claim.

The two smallest candidate validation MAEs differ by only 0.556 µg/m³ (1.11% of the minimum). This modest difference should not be portrayed as decisive model superiority; selection can be sensitive to the prespecified simplicity tolerance and this particular validation year. The rule is kept unchanged after seeing the test results.

The chosen coefficients, training means, baseline and daily threshold were written to `results/stage2/frozen_model.json` **before** evaluation of the final test response. No validation/test refit, imputation, response-scale change, weather scaling or negative-prediction clipping was performed.

The daily high-pollution threshold is **234.655 µg/m³**, the 95th percentile of eligible training daily PM2.5 (days at or above it are high). This is distinct from an hourly threshold in a related paper.

| Model | Group | n | MAE | RMSE | Mean prediction − observation | Negative estimates |
| --- | --- | --- | --- | --- | --- | --- |
| M3 | all | 357 | 46.785 | 60.935 | 15.283 | 3 |
| M3 | high | 17 | 160.945 | 173.583 | -160.945 | 0 |
| M3 | below_cutoff | 340 | 41.077 | 48.910 | 24.095 | 3 |
| training_mean | all | 357 | 55.297 | 73.006 | 12.897 | 0 |
| training_mean | high | 17 | 215.812 | 225.886 | -215.812 | 0 |
| training_mean | below_cutoff | 340 | 47.272 | 55.183 | 24.333 | 0 |

All error quantities above are in µg/m³. Signed error is prediction − observation: negative means underestimation. High/below-cutoff subgroups partition the same test dates for both models, and small subgroup sizes limit precision. The training-mean baseline is fixed at 90.774 µg/m³. Only M3 and that baseline are evaluated on the final test; the other candidate test scores are not computed.

All predictions use actual same-day aggregated weather, so this is a held-out **contemporaneous estimation** exercise. Real advance forecasts would require different information and evaluation rules. Temporal errors also make independent-observation confidence intervals for performance differences inappropriate; none are claimed.

## Figures, reproducibility and limits

`results/stage2/figures/` contains PNG and SVG exports: training correlations; an individual four-panel diagnostic for M1, M2 and M3; full-calendar residual series; residual ACFs; M3 seasonal wind slopes and HAC intervals; validation MAE comparison; and final-test estimates. Final-test plots are descriptive after the model is frozen, not inputs to tuning.

Exact invocation:

```bash
.venv/bin/python -W error -m beijing_pm25 stage2
```

Reproduce from the project directory with `.venv/bin/python -m beijing_pm25 stage1`, then `.venv/bin/python -m beijing_pm25 stage2`; check both stages using `.venv/bin/python -m beijing_pm25 verify`. The Stage 1 refresh updates provenance/code/environment references after installing the Stage 2 modules and leaves the source archive unchanged. The Stage 2 manifest records the protocol, configuration, source/Stage 1 hashes, dependency versions, the frozen-model file and every generated artifact. Tests and independent checks are documented separately in `reports/stage2_checks.md` when run.

This study uses one station and a historical time range. Completeness filtering may be selective, weather is spatially matched, pollution history/emissions and nonlinear relationships are omitted, and coefficient relations can change over years. Neither rank/conditioning, a significant p-value, nor a high R² establishes adequate errors or generalization. The test interval is now used for evaluation; future adaptations need to be labeled exploratory rather than reusing it as fresh confirmation. No published paper's model scores are reported as ours.

Stage 2's core analysis is complete. The next practical deliverable is a concise submission report and presentation explaining this evidence and its limits. Optional EWMA/ridge/second-station work has not been started.
