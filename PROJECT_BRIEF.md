# Project brief — Beyond R²: Beijing PM2.5

The statistical investigation and verification are complete. Current work refines its research presentation and documentation without changing the analysis. The first-task instructions below are retained as the original handoff; no new EWMA, ridge or forecasting extension is planned.

## Purpose and constraints
This is an undergraduate statistics project worth **30%** of the course grade. The project should resemble a clear, reproducible statistical investigation, **not** a claim of publication-grade novelty. Core syllabus methods: **multiple linear regression, ANOVA / nested-model tests, hypothesis testing, residual diagnostics**. Optional extension: an **adaptive residual-bias correction** using EWMA. Optional mathematical add-on: collinearity, design-matrix conditioning, and ridge regression if justified by evidence.

Assessment criteria (out of 30): dataset quality 5, analytical work 10, presentation 5, interpretation 5, quality of results 5.

## Working title
**Beyond R²: Seasonal Effects, Residual Dependence, and Model Adequacy in Beijing PM2.5 Regression**

## Main research question
How adequately do meteorological and seasonal variables explain daily PM2.5 variation, and what do nested-model tests and residual diagnostics reveal about model adequacy?

The original handoff also proposed past-only adaptive bias correction as an optional question. It is not part of the final submission implementation; existing Stage 3 extensions are exploratory supporting analyses.

**Do not presuppose any hypotheses are true.** Report null/negative findings and uncertainty explicitly.

## Data
- Primary: **UCI Beijing Multi-Site Air Quality Dataset**, https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data . Hourly measurements at 12 monitoring stations from March 2013–February 2017; fields include PM2.5, PM10, SO2, NO2, CO, O3, temperature, pressure, dew point, rain, wind speed, wind direction, and timestamps.
- Initial scope: use **daily aggregates from one station**, and, if time permits, repeat key tests at one additional station. For daily PM2.5 means require an explicitly documented minimum count of valid hourly observations; use comparable completeness rules for meteorological variables. Keep a record of missingness and date coverage. Choose stations based on completeness and documented criteria, not on whichever produces an attractive result.
- Daily aggregation reduces implementation complexity but **does not make observations independent**. Plot ACF and check time dependence. For extreme-event analysis, distinguish daily high-pollution days from the paper's hourly 95th-percentile threshold; do not reuse the latter without considering aggregation.
- Prefer obtaining data from its original UCI source and record provenance/version/date of access. Preserve raw files unchanged.

## Related papers and what we use
1. Y. Wang and R. Du, **Same-Hour Estimation and Multi-Horizon Forecasting of PM2.5 in Beijing: Model Comparison and Feature-Group Contributions**, arXiv:2607.07279v3 (Aug 2026), https://arxiv.org/abs/2607.07279 . Uses this UCI dataset; useful for feature-group contributions, extreme-event model failure, station heterogeneity, and chronological evaluation. Its principal task is multi-horizon forecasting, **not** our explanatory regression/ANOVA study. Do not copy its results as ours.
2. **Interpretable PM2.5 Forecasting for Urban Air Quality: A Comparative Study of Adaptive Time-Series Models**, arXiv:2603.25495 (consult the **revised version** and verify exact method and results), https://arxiv.org/abs/2603.25495 . Its EWMA correction using prior residuals motivates an *optional* small extension. It uses different underlying data; **do not compare its published numerical errors directly to UCI benchmark scores**.

## Statistical investigation
Use PM2.5 concentration as response. Examine the skewness, decide in advance whether a log1p transformation is justified, and clearly describe the interpretability implications. Use consistent response definitions across models being compared.

Candidate nested OLS specifications (exact covariates to be finalized after EDA, ensuring numerical stability and avoiding redundant indicators):

- **M1 (weather):** `response ~ temperature + wind_speed + rainfall + pressure`.
- **M2 (weather + season):** `M1 + C(season)`.
- **M3 (weather + season-specific wind effect):** `M2 + C(season):wind_speed`.

Primary inferential questions:
- **H1:** After adjustment for meteorological variables, are seasonal coefficients jointly zero? M1 vs M2.
- **H2:** Does the wind-speed association differ by season? M2 vs M3.
- **H3:** Do model residuals show significant serial dependence and/or heteroscedasticity? Examine diagnostic evidence and inferential consequences; don't use a significant p-value alone to characterize practical importance.
- **Exploratory H4:** Does strictly historical EWMA residual correction improve out-of-sample MAE/RMSE relative to the frozen OLS model? This is an optional predictive test, not an ANOVA question.

For M1–M3, compare nested-model partial F-tests **only with appropriate caveats**: standard OLS p-values can be misleading when residuals are serially correlated or heteroscedastic. Use HAC/Newey–West covariance and robust *joint Wald tests* as an additional sensitivity check. Don't claim HAC corrections automatically make every issue disappear. Make inferential vs predictive comparisons explicit.

Descriptive and diagnostic output:
- Sample sizes, missingness, seasonal distributions, correlation plots, potentially extreme periods.
- Coefficient estimates, uncertainty intervals, p-values, adjusted R², AIC/BIC where meaningful, in-sample model comparisons.
- Residual-versus-fitted, QQ, ACF, time-series residual plot, influence/outliers and heteroscedasticity diagnostics; discuss limitations.
- Chronological holdout performance with MAE and RMSE, both overall and for high-PM2.5 days (threshold defined using training data). Extreme-subgroup RMSE is not itself proof of systematic underprediction; check signed errors.

## Optional adaptive extension
- Fit a selected OLS model on the training interval. **Freeze** its coefficients for the held-out evaluation.
- At time t, issue an estimate from covariates available for that task. An EWMA bias estimate uses **only residuals already observed before t**. For daily data, update with completed past days, not the current day's observed target.
- Compare frozen OLS predictions to `OLS prediction + available past EWMA bias`.
- Tune EWMA smoothing constant only within training/validation periods; never select based on final held-out errors.
- Distinguish **same-day explanatory estimates with observed weather** from a deployable forward forecast. If the user wants true forecasting, use only features observable at the forecast origin or weather forecasts and modify the task definition.
- Test whether gains persist across dates and, if feasible, a second station. Report failures honestly. Do not suggest causal effects.

## Scope and execution priorities
**Core deliverable:** defensible descriptive analysis + M1/M2/M3 + ANOVA/robust testing + residual diagnostics + interpretable conclusions.
**Stretch only if core is sound:** past-only EWMA residual correction; then perhaps matrix condition numbers, VIF, SVD or ridge. Avoid implementing XGBoost, Prophet, NeuralProphet, SARIMAX, conformal inference or a large multi-horizon benchmark unless explicitly authorized.

Suggested structure:
```
beijing-pm25/
  AGENTS.md
  PROJECT_BRIEF.md
  README.md
  data/raw/               # gitignored as needed
  data/processed/         # generated, not source of truth
  src/                    # reproducible loading, cleaning, analysis
  notebooks/              # concise EDA and illustrative figures
  results/figures/
  results/tables/
  reports/                # hypotheses, interpretation, limitations
  tests/                  # leakage, aggregation, correctness checks
```
Preferred implementation: Python (pandas, numpy, scipy, statsmodels, matplotlib/seaborn or plotly if clearly justified; scikit-learn only if needed). Use small modules/scripts over one huge notebook; reproducible environment and documented execution commands. Data acquisition must respect network availability and site policies.

## Evidence and limitations to preserve
- Chronological train/validation/test splitting, not random train/test for time-dependent prediction questions.
- Prevent train/test leakage in imputation, scaling, transformations, threshold selection and adaptive correction.
- Observational association **is not causation**.
- Don't equate near-zero raw temperature correlation with no seasonal or conditional temperature relationship.
- Station, time, and missingness may confound simple analyses; discuss scope of any generalization.
- Be careful with ANOVA assumptions and effective sample size; robust inference if serial dependence warrants it.
- No fabricated statistics or claimed model performance before runs are complete.

## Handoff: first Codex task
**Do only Stage 1; stop and report before implementing later stages:**
1. Read `PROJECT_BRIEF.md` and `AGENTS.md`.
2. Inspect the local environment and decide on a lightweight reproducible Python project structure.
3. Locate/fetch the original UCI Beijing Multi-Site dataset if network is available; otherwise create a documented download step and stop short of invented data.
4. Inspect station availability, missingness, timestamp regularity and the response distribution; propose the first station using transparent criteria.
5. Implement a data-cleaning + daily-aggregation pipeline and sanity tests (e.g., no accidental combining across stations, no missing-day misalignment, completeness thresholds).
6. Produce a short Stage 1 summary listing: chosen station and rationale, observations retained/excluded, plots, issues requiring decisions, exact commands run.
7. **Do not start Stage 2/model fitting until approved.**

## Operating rules
- Local-first. Do not commit, push, open PRs, or make remote changes without explicit permission. Do not modify unrelated repositories.
- Tests and data-quality checks before substantive model claims.
- If expensive/hanging operations occur, support interruption and reasonable timeouts; keep memory usage modest.
- Clearly separate the published papers' findings from results actually reproduced in this project.
