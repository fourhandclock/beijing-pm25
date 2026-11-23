# Statistical audit for final submission

Baseline: merged PR #1, commit
`87152460db5eb73c58c11df66d0964e0fd9e8467`. This audit checks numerical correctness
and interpretation. It supplies no new confirmatory test period.

## Confirmatory Stage 2

The original aggregation, model, configuration, diagnostics and evaluation methods
are retained. `check_frozen_stage2.py` compares their source hashes, training-only
centering, all three fits, model choice, cutoff, predictions' summary scores,
ANOVA and HAC tests with a snapshot of the merged main branch. The original
prefit protocol is preserved byte for byte in
[`../archive/stage2_protocol_original_20261119.md`](../archive/stage2_protocol_original_20261119.md).
Administrative edits to the active protocol leave its methodological rules unchanged.

`verify_models.py` uses a separate QR least-squares implementation, SSE-based
partial F calculations, explicit calendar-pair HAC score products, linear
contrasts and direct error summaries. It imports neither the analysis package
nor statsmodels. All 3 fits, 9 HAC covariance matrices and 5,050 dated predictions
are checked. The 7-day primary Wald statistics are 8.548354 and 8.880500;
unadjusted p-values are 0.035939 and 0.030923. Holm adjustment across the two
prespecified hypotheses gives **0.061845 for both**. Neither rejects at 5%.
The classical F p-values (0.003290 and 0.063581) must be distinguished from this
primary conclusion; ordinary F calibration assumes appropriate independent,
constant-variance errors.

The fixed validation rule selects M3. M2 is only 1.11% above the minimum MAE,
just outside the unchanged 1% simplicity tolerance. M3's frozen test MAE is
46.784656 and RMSE 60.934771 µg/m³ on 357 days. The original test results are
regenerated for reproducibility, without retuning or treating the test year as
unseen again. Residual lag-one correlation is 0.511654 over 719 calendar pairs;
high-day signed error is −160.944617 µg/m³ on only 17 days. Three negative test
estimates remain in every score. Individual coefficient intervals are not
simultaneous intervals; the summer wind interval includes zero.

## Exploratory Stage 3

`verify_extensions.py` starts from the raw archive and separately aggregates all
12 stations. Its QR/optimization/direct Ward implementations do not import the
analysis package or statsmodels. Agreement checks numerical implementation; it
is **not independent scientific replication** of the observational evidence.

- **Common samples:** 721/354/355 training/validation/test days are required by
  all five candidates. Stage 3's M3 is a refit on that sample, not the frozen
  Stage 2 test evaluation (725/359/357). Their different rows and training
  means explain the small differences in their M3 scores. No frozen score is
  replaced. The common-sample 95th-percentile threshold is also recalculated
  using only its own training data, so it differs from Stage 2's 234.655.
- **Log response:** the response is `log(1 + PM2.5)`. Training residuals determine
  the Duan smearing factor `s = mean(exp(residual))`; estimates on the original
  scale are `exp(linear estimate) * s - 1`. All coefficients, factors, predictions
  and original-unit error summaries are independently checked. The factors are
  approximately 1.239 (log M3) and 1.117 (combined model). A common smearing
  factor is an approximation if the conditional error distribution varies with
  predictors. The formula ensures an estimate above −1, **not nonnegativity**;
  zero negative estimates is an empirical result in this run. Cross-scale R²
  values must not be ranked as if they described the same response.
- **Lags and unavailable days:** PM2.5 is shifted on the complete daily calendar
  before filtering. A missing prior calendar day yields a missing lag; it never
  uses the last available row. A lag needs the prior day's eligible PM2.5 mean,
  not every prior weather field. The first validation/test day can use the
  preceding period's already observed PM2.5. Later test days use actual past
  PM2.5 in a rolling same-day estimation exercise, not recursively generated
  future values. Changing synthetic test outcomes/predictors cannot alter fitted
  parameters, smearing, validation model selection or the logistic cutoff.
- **Classification:** the logistic outcome is daily PM2.5 at or above the
  training 95th percentile, not a regulatory or health category. The M2 logistic
  fit uses 725 training days (37 positives). Validation F1 selects the probability
  cutoff **0.13229904066**, with higher-cutoff tie breaking; test labels do not
  select it. An independent analytic-gradient/Hessian optimization and direct
  rank-pair AUC check reproduce the result. On 357 test days: TP 15, FP 44,
  FN 2, TN 296, AUC 0.927336, recall 0.882353, precision 0.254237. A 0.5 cutoff
  detects none. AUC does not describe the false-alarm burden at the selected
  cutoff. Odds-ratio intervals assume independent observations and are exploratory.
- **Station comparison:** each station has its own eligible dates, train-only
  centers and quantile. All 12 M2 wind HAC intervals lie below zero. H1 passes
  within-station Holm adjustment at 6 stations, H2 at 2. The two-test correction
  within each station does **not** correct the full 24-test family. Stations
  share pollution and weather, so they are dependent. M3 beats its training-mean
  test MAE at 11 stations; Gucheng is the exception.
- **Clustering:** six pollutant-specific daily training means are standardized
  across stations with sample SD (`ddof=1`). Different pollutants can have
  different eligible dates. Direct Ward SSE merges reproduce the hierarchy;
  the largest merge-height gap for k=2…5 selects two groups. The group with
  lower mean PM2.5 contains Changping, Dingling, Huairou and Shunyi. Membership
  is descriptive; neither causal grouping, geographic classification nor
  stability on a new period has been established.

## AR(1) errors and missing calendar dates

The original statsmodels iterative GLSAR treats consecutive retained rows as
one step. Five two-day training gaps are therefore bridged as if one day apart
(725 observations, 724 fitted transitions after conditioning on the first).
Its original table remains intact. The limitation warranted a separate,
training-only sensitivity calculation, not replacement of that result.

To isolate spacing from estimation method, `audit_ar1_calendar.py` compares
two conditional Gaussian likelihood fits with identical first-observation
treatment and predictors. The row version uses lag 1 for every transition;
the calendar version uses its actual gap d, transition ρ^d and innovation
variance `(1 − ρ^(2d)) / (1 − ρ²)`. An independently constructed dense conditional
covariance verifies the wind coefficient and profile objective at each fitted ρ. Synthetic
tests also check negative ρ, zero ρ and equality on complete calendars.

| Method | M2 ρ | H1 nominal p | M3 ρ | H2 nominal p |
| --- | ---: | ---: | ---: | ---: |
| Original iterative GLSAR, row spacing | 0.572133 | 0.003317 | 0.569018 | 0.461571 |
| Conditional likelihood, row spacing | 0.571500 | 0.003330 | 0.568407 | 0.460974 |
| Conditional likelihood, calendar spacing | 0.583015 | 0.002613 | 0.580155 | 0.447549 |

The paired calendar treatment changes M2's wind coefficient from −34.002 to
−34.051 and M3's winter wind coefficient from −36.644 to −37.180. The signs
and nominal joint-test decisions are unchanged, including within-method Holm
adjustment. This result addresses these five short gaps; it does not show that
gaps are always harmless. No missing outcome is imputed, and neither sensitivity
uses test responses.

The F references and coefficient intervals treat the estimated ρ as fixed;
uncertainty in it is not fully accounted for. Gaussian AR(1), stationarity and
the conditional mean specification are working assumptions. Agreement with
this sensitivity cannot validate those assumptions or override the primary
Stage 2 HAC/Holm conclusion. See the
[sensitivity table](../../results/stage4/tables/ar1_calendar_sensitivity.csv)
and [dense-covariance check](ar1_calendar_check.json).

## Corrections to presentation, rather than calculations

The original label “Stage 2 M3” in a common-sample comparison is now “M3 refit
on common sample.” Log-scale back-transformation is described accurately;
log-response and original-unit coefficients are explicitly distinguished.
The log-lag coefficient, previously absent from a selected-term display, is
included. Unsupported urban/suburban cluster wording is replaced with the
observed memberships. Administrative submission metadata are omitted from active
documents; the archived prefit protocol retains its original chronology.

No numerical correction to the frozen Stage 2 analysis was needed. Differences
at floating-point precision are checked with explicit tolerances and reported
by the oracle JSON records. Exact bitwise equality across BLAS, Python or OS
versions is not claimed. Raw checksums and output integrity are checked exactly.

All 18 original PR #1 Stage 3 artifacts are additionally preserved byte for byte
in [`../archive/stage3_pr1_original.zip`](../archive/stage3_pr1_original.zip), with
their checksums in `baseline_main.json`. `check_stage3_preservation.py` checks
every regenerated numerical cell in its 12 CSV tables against that archive.
The observed maximum absolute difference in the working rerun was
9.90 × 10⁻¹²; the clarified common-sample M3 label is the only allowed textual
table change. This avoids conflating floating-point serialization with a
change in scientific method.

## Sources and remaining limits

[UCI dataset documentation](https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data)
supports the dataset scope and attribution. Duan (1983),
[Smearing Estimate: A Nonparametric Retransformation Method](https://doi.org/10.1080/01621459.1983.10478017),
JASA 78(383), 605–610, supplies the retransformation reference.
[Statsmodels GLSAR documentation](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.GLSAR.html)
documents the iterative AR-error implementation; the
[GLS example](https://www.statsmodels.org/stable/examples/notebooks/generated/gls.html)
illustrates a lag-distance covariance. These references support methods, not
this project's empirical outcomes.

The study remains observational, geographically limited and historically
bounded. Completeness filtering may be informative; nearest-station weather,
omitted emissions/transport, temporal shifts, heavy tails and residual dependence
limit inference. Observed weather is available only contemporaneously. Stage 3
ideas were developed after the test year was inspected, so a new confirmatory
evaluation needs an unseen period and prespecified rules. No causal effect,
advance forecast or independent scientific replication is claimed.
