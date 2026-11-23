"""Render empirical results from completed computations, without invented claims."""

import shlex

import pandas as pd


def number(value, digits=3):
    return "NA" if pd.isna(value) else f"{value:.{digits}f}"


def probability(value):
    if pd.isna(value):
        return "NA"
    if value == 0:
        return "<1e-300"
    return f"{value:.3g}"


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |",
                      *("| " + " | ".join(map(str, row)) + " |" for row in rows)])


def render_report(station, stage1, config, development, summaries, coefficients, classical,
                  robust, diagnostics, influences, slopes, metrics, frozen, invocation):
    selected = development.selected_model
    primary = robust.loc[robust["primary_bandwidth"]]
    test = metrics.loc[metrics["split"].eq("test")]
    overall = test.loc[test["model"].eq(selected) & test["subgroup"].eq("all")].iloc[0]
    baseline = test.loc[test["model"].eq("training_mean") & test["subgroup"].eq("all")].iloc[0]
    high = test.loc[test["model"].eq(selected) & test["subgroup"].eq("high")].iloc[0]
    chosen_diagnostics = diagnostics.loc[diagnostics["model"].eq(selected)].iloc[0]
    best_two = development.selection.sort_values("mae").head(2)
    validation_gap = float(best_two.iloc[1]["mae"] - best_two.iloc[0]["mae"])
    validation_gap_percent = 100 * validation_gap / float(best_two.iloc[0]["mae"])
    wind = coefficients.loc[coefficients["model"].eq("M2") & coefficients["term"].eq("wind_speed_c")].iloc[0]
    improvement = 100 * (1 - overall["mae"] / baseline["mae"]) if baseline["mae"] else float("nan")
    error_direction = "underestimation" if high["mean_signed_error"] < 0 else "overestimation"
    inference_rows = []
    for _, row in primary.iterrows():
        decision = "evidence against this joint null" if row["p_holm_primary"] < config.alpha else "insufficient evidence against this joint null"
        inference_rows.append(
            f"- **{row['hypothesis']}**: primary calendar-HAC Wald χ²({int(row['df'])}) = "
            f"{number(row['wald_chi2'])}, p = {probability(row['p_value_hac'])}; "
            f"Holm-adjusted p = {probability(row['p_holm_primary'])}. At alpha {config.alpha:g}, this is {decision}."
        )
    fit_table = table(["Model", "n", "Parameters", "R²", "Adjusted R²", "Residual SD", "AIC*", "BIC*"], [
        (row.model, row.n, row.parameters, number(row.r_squared), number(row.adjusted_r_squared),
         number(row.residual_standard_error), number(row.aic_working_iid, 1), number(row.bic_working_iid, 1))
        for row in summaries.itertuples()
    ])
    f_table = table(["Question", "Comparison", "SSE reduction", "Added df", "F", "Classical p*"], [
        (row.hypothesis, f"{row.restricted} → {row.full}", number(row.sse_reduction, 1), row.df_added,
         number(row.f_statistic), probability(row.p_value_iid)) for row in classical.itertuples()
    ])
    robust_table = table(["Question", "HAC days", "Wald χ²", "df", "HAC p", "Primary Holm p"], [
        (row.hypothesis, row.hac_lag_calendar_days, number(row.wald_chi2), row.df,
         probability(row.p_value_hac), probability(row.p_holm_primary)) for row in robust.itertuples()
    ])
    coefficient_table = table(["M2 term", "Estimate", "HAC SE", "HAC interval", "Unadjusted HAC p"], [
        (row.term, number(row.estimate), number(row.hac_se),
         f"[{number(row.hac_ci_lower)}, {number(row.hac_ci_upper)}]", probability(row.hac_p))
        for row in coefficients.loc[coefficients["model"].eq("M2")].itertuples()
    ])
    slope_table = table(["Season", "M3 wind slope", "HAC interval"], [
        (row.season, number(row.pm25_change_per_1_mps_wind),
         f"[{number(row.hac_ci_lower)}, {number(row.hac_ci_upper)}]") for row in slopes.itertuples()
    ])
    diagnostic_table = table(["Model", "Lag-1 residual r", "BG-style LM p*", "Aux n", "Koenker BP p*", "Residual skew", "Cook flags"], [
        (row.model, number(row.calendar_lag1_residual_correlation), probability(row.serial_lm_p_approx),
         row.serial_auxiliary_n, probability(row.koenker_bp_p_iid), number(row.residual_skewness), row.cook_screen_count)
        for row in diagnostics.itertuples()
    ])
    selection_table = table(["Model", "Parameters", "Validation n", "MAE", "RMSE", "Within tolerance", "Chosen"], [
        (row.model, row.parameters, row.n, number(row.mae), number(row.rmse),
         str(row.within_simplicity_band), str(row.selected)) for row in development.selection.itertuples()
    ])
    test_table = table(["Model", "Group", "n", "MAE", "RMSE", "Mean prediction − observation", "Negative estimates"], [
        (row.model, row.subgroup, row.n, number(row.mae), number(row.rmse),
         number(row.mean_signed_error), row.negative_predictions) for row in test.itertuples()
    ])
    important = influences.loc[influences["model"].eq(selected)].nlargest(5, "cooks_distance")
    influential_table = table(["Date", "Observed", "Fitted", "Residual", "Leverage", "Cook's distance"], [
        (row.date.date().isoformat(), number(row.observed), number(row.fitted), number(row.residual),
         number(row.leverage), number(row.cooks_distance)) for row in important.itertuples()
    ])
    centers = ", ".join(f"{name} = {value:.4f}" for name, value in development.centers.items())
    counts = stage1["retention"]
    return f"""# Stage 2 — regression, seasonal tests and model adequacy

**{station}; original-scale daily PM2.5; completed on the original UCI dataset.** Model decisions follow the [protocol](stage2_protocol.md), written before the first empirical fit. The submission deadline is 25 November 2026.

## Main findings

The validation rule selected **{selected}**. Its frozen final-test MAE is **{number(overall['mae'])} µg/m³** and RMSE is **{number(overall['rmse'])} µg/m³**, across {int(overall['n'])} eligible days. The training-mean baseline has MAE {number(baseline['mae'])} and RMSE {number(baseline['rmse'])}; the selected model's relative MAE reduction is {number(improvement, 1)}% (negative would indicate worse performance).

{chr(10).join(inference_rows)}
- The selected model's lag-one training residual correlation is {number(chosen_diagnostics['calendar_lag1_residual_correlation'])}. This quantifies remaining temporal structure; the diagnostic p-values below have assumptions and are not an independence certificate.
- On the {int(high['n'])} final-test high-pollution days, mean prediction minus observation is {number(high['mean_signed_error'])} µg/m³, indicating average {error_direction} in this subgroup. High-day RMSE is {number(high['rmse'])}; the signed error, rather than RMSE alone, supplies the direction.

The overall signed error is {number(overall['mean_signed_error'])} µg/m³ (positive means average overestimation), so the aggregate bias can have a different direction from the high-day bias. There are **{int(overall['negative_predictions'])} negative test estimates**, a physical limitation of this unrestricted linear model; they remain in the reported errors.

These are conditional associations and same-day estimates using observed weather. They do not establish causal effects or advance-forecasting skill.

## Sample and fixed specifications

All candidates use the same **{counts['train']['analysis_eligible_days']} eligible training dates**, from the Stage 1 calendar {stage1['configuration']['calendar_start']} to {stage1['configuration']['train_end_exclusive']} exclusive. There are {counts['validation']['analysis_eligible_days']} eligible validation dates and {counts['test']['analysis_eligible_days']} eligible test dates. The original 18-hour mean/joint-completeness and complete-24-hour rainfall rules are unchanged; excluded dates are not silently joined for time diagnostics.

The response remains µg/m³. Training marginal skewness supported considering log1p, but a nonnormal marginal response is not itself a violation of the normal conditional-error assumption. The protocol fixes the original scale to preserve direct interpretation; no log model was fit or chosen based on these results.

Training-only centering constants are: {centers}. Units remain °C, m/s, mm/day and hPa. Centering changes coefficient interpretation and numerical scaling, not fitted values or the model family. Winter is the reference season.

- **M1:** intercept + centered temperature, wind speed, rainfall and pressure.
- **M2:** M1 + three seasonal indicators.
- **M3:** M2 + three season × centered-wind interactions.

All matrices are checked for full rank. Numerical conditioning is reported separately from coefficient uncertainty; full rank is not evidence that statistical estimates are precise.

## Fitted comparison and planned joint hypotheses

{fit_table}

R² and adjusted R² describe fit to training observations. They do not estimate future accuracy. *AIC/BIC are working Gaussian/iid likelihood criteria on the same response/sample; remaining dependence limits their usual interpretation.*

{f_table}

The ordinary partial F-test uses the SSE decrease per added parameter relative to the full model's residual mean square. Its exact reference distribution assumes a correctly specified linear conditional mean with independent, homoscedastic Gaussian errors; large-sample approximations have their own conditions. Serial dependence, unequal variance or nonnormal errors can make nominal p-values misleading; they are not the sole inferential conclusion. [Statsmodels F-test documentation](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.compare_f_test.html).

{robust_table}

HAC uses Bartlett weights, a primary {config.primary_hac_lag_days}-calendar-day bandwidth, prespecified {', '.join(map(str, config.hac_lag_days))}-day sensitivities, and n/(n−p) correction. Omitted dates contribute zero scores, preserving calendar-day separations without inventing responses. The reported Wald reference is asymptotic χ², not the classical nested F distribution. The two primary joint p-values receive Holm adjustment; the bandwidth sensitivities are descriptive checks. HAC cannot repair a misspecified mean, informative missingness, endogeneity or instability. [HAC reference](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html).

## Coefficients and interpretation

{coefficient_table}

These M2 intervals use the primary HAC covariance and a normal approximation at {100 * (1 - config.alpha):g}% individual coverage; coefficient p-values are unadjusted. Full ordinary t-based and HAC tables for **all three models** are in `results/stage2/tables/coefficients.csv`. Statistical evidence for a joint seasonal term does not establish every individual seasonal contrast.

For M2, a weather coefficient is an estimated µg/m³ difference associated with one unit higher weather value, conditional on the other listed predictors and season. A seasonal coefficient compares that season with winter under the common wind slope. With interactions in M3, seasonal offsets are evaluated at the training mean wind speed, and its base wind coefficient is the winter slope.

For example, M2's wind coefficient is {number(wind['estimate'])}: a 1 m/s higher daily wind speed is associated with that many µg/m³ difference in fitted PM2.5, holding the other listed predictors and season fixed. Its individual primary HAC interval is [{number(wind['hac_ci_lower'])}, {number(wind['hac_ci_upper'])}]. This conditional association is not a causal claim about an intervention.

{slope_table}

M3 slopes are changes in fitted µg/m³ per 1 m/s higher wind speed, conditional on the other predictors. Each interval uses the full linear-contrast covariance, including covariance between the baseline wind slope and interaction. These are individual uncertainty intervals, not simultaneous intervals or causal intervention effects.

## Residual adequacy and influence

{diagnostic_table}

The calendar ACF retains missing daily positions. The BG-style check regresses the fitted residual on the original regressors and the preceding {config.serial_test_lag_days} calendar-day residuals, dropping only auxiliary rows missing one of those lags; the smaller auxiliary n is explicit. Its LM statistic is n_aux × R² with an approximate χ² reference. This complete-case variant is documented in the protocol, rather than applying row-based lags across missing dates. [BG auxiliary-regression reference](https://www.statsmodels.org/stable/generated/statsmodels.stats.diagnostic.acorr_breusch_godfrey.html).

*The serial auxiliary F, Koenker/Breusch–Pagan and Jarque–Bera reference p-values also have assumptions; temporal dependence and missingness can affect their calibration. Koenker's variant relaxes normality, not independence. Interpret them alongside the scatter, Q–Q and ACF patterns and the magnitude of residuals.* Full statistics, residual skewness/kurtosis, screening counts and auxiliary sample sizes are saved in `residual_diagnostics.csv`. [Breusch–Pagan assumptions](https://www.statsmodels.org/stable/generated/statsmodels.stats.diagnostic.het_breuschpagan.html).

The five largest Cook's distances for {selected} are:

{influential_table}

No flagged day was removed. Cook > 4/n, leverage > 2p/n and |internally studentized residual| > 3 are screening guides. They identify observations to inspect, not proven errors or emissions events. A Q–Q plot assesses error-distribution shape; it does not check temporal independence.

## Chronological selection and held-out estimates

{selection_table}

The selection rule uses only overall validation MAE. Models within {100 * config.simplicity_tolerance_fraction:g}% of its minimum are compared by parameter count, then MAE, then name. Inferential p-values, AIC/BIC and final-test scores do not select the model. Validation is therefore a development interval, not a second untouched performance claim.

The two smallest candidate validation MAEs differ by only {number(validation_gap)} µg/m³ ({number(validation_gap_percent, 2)}% of the minimum). This modest difference should not be portrayed as decisive model superiority; selection can be sensitive to the prespecified simplicity tolerance and this particular validation year. The rule is kept unchanged after seeing the test results.

The chosen coefficients, training means, baseline and daily threshold were written to `results/stage2/frozen_model.json` **before** evaluation of the final test response. No validation/test refit, imputation, response-scale change, weather scaling or negative-prediction clipping was performed.

The daily high-pollution threshold is **{number(development.threshold)} µg/m³**, the {100 * config.extreme_training_quantile:g}th percentile of eligible training daily PM2.5 (days at or above it are high). This is distinct from an hourly threshold in a related paper.

{test_table}

All error quantities above are in µg/m³. Signed error is prediction − observation: negative means underestimation. High/below-cutoff subgroups partition the same test dates for both models, and small subgroup sizes limit precision. The training-mean baseline is fixed at {number(development.training_mean)} µg/m³. Only {selected} and that baseline are evaluated on the final test; the other candidate test scores are not computed.

All predictions use actual same-day aggregated weather, so this is a held-out **contemporaneous estimation** exercise. Real advance forecasts would require different information and evaluation rules. Temporal errors also make independent-observation confidence intervals for performance differences inappropriate; none are claimed.

## Figures, reproducibility and limits

`results/stage2/figures/` contains PNG and SVG exports: training correlations; an individual four-panel diagnostic for M1, M2 and M3; full-calendar residual series; residual ACFs; M3 seasonal wind slopes and HAC intervals; validation MAE comparison; and final-test estimates. Final-test plots are descriptive after the model is frozen, not inputs to tuning.

Exact invocation:

```bash
{shlex.join(invocation)}
```

Reproduce from the project directory with `.venv/bin/python -m beijing_pm25 stage1`, then `.venv/bin/python -m beijing_pm25 stage2`; check both stages using `.venv/bin/python -m beijing_pm25 verify`. The Stage 1 refresh updates provenance/code/environment references after installing the Stage 2 modules and leaves the source archive unchanged. The Stage 2 manifest records the protocol, configuration, source/Stage 1 hashes, dependency versions, the frozen-model file and every generated artifact. Tests and independent checks are documented separately in `reports/stage2_checks.md` when run.

This study uses one station and a historical time range. Completeness filtering may be selective, weather is spatially matched, pollution history/emissions and nonlinear relationships are omitted, and coefficient relations can change over years. Neither rank/conditioning, a significant p-value, nor a high R² establishes adequate errors or generalization. The test interval is now used for evaluation; future adaptations need to be labeled exploratory rather than reusing it as fresh confirmation. No published paper's model scores are reported as ours.

Stage 2's core analysis is complete. The next practical deliverable is a concise submission report and presentation explaining this evidence and its limits. Optional EWMA/ridge/second-station work has not been started.
"""
