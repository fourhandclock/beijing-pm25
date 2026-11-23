# Stage 2 analysis protocol

Recorded before the first empirical model fit, following the user's approval to proceed from Stage 1. The original dated protocol is preserved byte for byte in `archive/stage2_protocol_original_20261119.md`; the methodological rules below remain unchanged. Stage 2 covers the core regression investigation; EWMA, ridge, other response models and a second station remain outside this stage.

## Response, sample and models

Use Wanliu and the unchanged Stage 1 daily-completeness rules. Fit all three models on exactly the same eligible **training** dates, 2013-03-01 through 2015-02-28. Retain the 2015-03-01–2016-02-29 validation and 2016-03-01–2017-02-28 test intervals.

The primary response is daily PM2.5 in **µg/m³**, without transformation. Training daily skewness was 1.441; log1p skewness was -0.450. These marginal distributions do not determine the distribution of conditional errors. Keeping the original scale supports direct course-level coefficient and prediction-error interpretation. This choice is fixed before fitting; an attractive p-value or test score will not trigger a response-scale switch. Negative OLS predictions will be counted and retained, rather than clipped silently.

Center temperature, wind speed, rainfall and pressure using **eligible training means only**. Retain their original measurement units. Centering improves intercept interpretation and pressure-related numerical scaling without changing the model family. Winter (DJF) is the reference season; spring is MAM, summer JJA and autumn SON.

- **M1:** intercept + centered temperature + centered wind speed + centered rainfall + centered pressure (5 parameters).
- **M2:** M1 + spring/summer/autumn indicators (8 parameters).
- **M3:** M2 + each non-reference season indicator × centered wind speed (11 parameters).

Check full rank and common observations before comparison. No iterative feature selection, outlier deletion, imputation, fitted scaling or unapproved model extension is planned.

## Inference and diagnostics

H1 compares M1 with M2: are the three seasonal offsets jointly zero? H2 compares M2 with M3: are the three changes in wind-speed association jointly zero?

Report ordinary nested-model partial F-tests alongside their independent/homoscedastic-error assumptions. Report additional joint **chi-square Wald tests** using calendar-aware Newey–West covariance: Bartlett weights, primary maximum lag **7 calendar days**, sensitivity lags **14 and 30 days**, and finite-sample multiplier n/(n−p). Report unadjusted primary robust p-values and Holm-adjusted p-values for the two planned robust hypotheses at alpha 0.05; the bandwidth sensitivities are not additional confirmatory tests.

Incomplete dates must not collapse the time scale. For the HAC covariance, insert zero **score contributions** (x × residual), not invented measurements, at omitted calendar slots, and form lagged cross-products on the full training calendar. The bread matrix and finite-sample correction use only actual fitted observations. This preserves calendar-day distances. It does not cure informative missingness, a misspecified conditional mean, endogeneity or unstable long-term dynamics. On an uninterrupted calendar the calculation must agree with statsmodels' standard HAC covariance.

Show ordinary t-based and primary HAC normal-approximation coefficient intervals separately. Estimate M3 wind-speed slopes in all four seasons using linear contrasts and the full covariance matrix; these are adjusted associations, not causal effects. Report adjusted R², residual standard error, AIC/BIC and matrix rank/conditioning; AIC/BIC are working Gaussian/iid criteria on a common response/sample.

Diagnostics use training residuals: residual-versus-fitted and scale-location plots, a normal Q–Q plot, full-calendar residual time series/ACF, and leverage/Cook's distance. Retain flagged observations; thresholds 4/n for Cook's distance, 2p/n for leverage and |internally studentized residual| > 3 are screening guides. A high score does not establish measurement error.

For a serial-dependence sensitivity check, regress the fitted residual on the original regressors plus residuals at lags 1–7 **calendar days**, keeping only rows with all required historical residuals. Report the Breusch–Godfrey-style n_aux × R² statistic, approximate chi-square p-value, auxiliary partial F statistic and auxiliary sample size. This is an explicitly complete-case variant, not an off-the-shelf test on compressed rows. Its calibration remains approximate and can be affected by heteroscedasticity/missingness. Use the residual ACF and effect sizes alongside its p-value.

Report Koenker's studentized Breusch–Pagan heteroscedasticity check and descriptive Jarque–Bera/skewness/kurtosis. These reference p-values also have assumptions, including temporal independence for their usual calibration. A significant p-value alone will not establish practical model inadequacy or causation. HAC is an uncertainty sensitivity check, not a repair of the fitted mean.

## Selection and chronological evaluation

Fit every candidate using training data only. Rank candidates by **overall validation MAE**; among models within **1%** of the minimum validation MAE, choose the fewest parameters, then lowest MAE, then model name. This fixed rule avoids keeping complexity for negligible validation gains. Hypothesis-test significance is not the predictive selection rule.

Before evaluating the test response, write `results/stage2/frozen_model.json`: the chosen model, fixed coefficients, training means, model columns, training PM2.5 mean baseline, training 95th-percentile daily response cutoff, selection rule and configuration. Do not refit on validation or test observations.

Evaluate only the chosen frozen model and the training-mean baseline on final test dates. Report MAE, RMSE, and **prediction − observation** mean signed error overall, on days at/above the training 95th-percentile daily cutoff, and below that cutoff. Counts and mean observed/predicted values accompany subgroup errors. The cutoff is a daily statistic of this training sample, not an imported hourly paper threshold. Extreme-subgroup RMSE alone does not establish underprediction; signed errors supply the direction. Report validation scores for all candidates and label fitted training scores separately.

All estimates use same-day observed weather. They evaluate contemporaneous estimation, **not advance forecasting**. Test outcomes cannot choose the response, regressors, covariance bandwidth, centering, cutoff or model. Any future adaptation after inspecting these results must be labeled exploratory and cannot reuse this test as fresh validation.

## Reproducibility and references

Keep raw data unchanged, preserve Stage 1 outputs, and write Stage 2 tables/figures into their own directory. A run manifest must record source and protocol/configuration hashes, dependencies, frozen-model hash, selected model and generated outputs. Synthetic tests must verify nesting, OLS/F calculations, gap-aware HAC, training-only preprocessing/selection/thresholds and evaluation signs. An independent NumPy/SciPy calculation will verify the real-data results. No paper's numerical results are substituted for this project's runs.

Primary method documentation consulted:

- [Statsmodels nested-model F comparison](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.compare_f_test.html): nested restrictions and the error-covariance caveat.
- [Statsmodels HAC covariance](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html): equal-spacing assumption and Bartlett covariance. Our missing-date adaptation is stated above and tested separately.
- [Statsmodels Breusch–Godfrey diagnostic](https://www.statsmodels.org/stable/generated/statsmodels.stats.diagnostic.acorr_breusch_godfrey.html): residual-lag auxiliary regression; our calendar complete-case variant is explicit.
- [Statsmodels Breusch–Pagan diagnostic](https://www.statsmodels.org/stable/generated/statsmodels.stats.diagnostic.het_breuschpagan.html): studentized variant and reference-test assumptions.
