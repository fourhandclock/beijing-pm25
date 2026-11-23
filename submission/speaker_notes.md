# Presentation speaker notes

Beyond R²: Seasonal Effects, Residual Dependence, and Model Adequacy in Beijing PM2.5 Regression

Slides use generated analysis tables. Stage 2 is the prespecified core; Stage 3 and the AR(1) sensitivity are exploratory.

## 1. Beyond R²

Introduce a statistical adequacy investigation using UCI observations. Weather is measured on the same day as the response: this is contemporaneous estimation, not an advance-forecast benchmark. The original confirmatory regressions are distinguished from exploratory work developed after the test year was viewed.

## 2. Does season add information beyond weather?

H1 compares M1 with M2; H2 compares M2 with M3. The third question concerns the errors, not another search for favorable p-values. Season can represent omitted processes, so seasonal coefficients describe conditional association rather than a causal mechanism.

## 3. Daily data, chronological evaluation

The source contains 420,768 hourly station records. Wanliu retains 1,441 of 1,461 calendar dates. Each mean uses its own valid hours; there is no target imputation or outcome-based trimming. Centers and quantile thresholds use training data only. Local time and rainfall-amount assumptions are documented in the report.

## 4. Three nested multiple regressions

Each added block has three parameters. In M3, seasonal offsets apply at the training mean wind speed and the base wind coefficient is the winter slope. Every design is full rank; conditioning is separate from statistical uncertainty. The wind coefficient is an observational association, not an intervention effect.

## 5. Classical ANOVA and robust inference

Classical F uses an iid, constant-variance Gaussian reference for exact calibration. HAC retains actual calendar separations and uses n/(n−p). Its Wald reference is asymptotic. The 14/30-day bandwidth checks are descriptive sensitivities. Failure to reject is not proof that seasonal structure is absent.

## 6. Residual dependence remains

The first-lag correlation is substantial after weather and season adjustment. Missing calendar positions are retained and pair counts vary by lag. Daily aggregation has not made the errors independent. Read the magnitude and pattern rather than treating an auxiliary p-value as an independence certificate.

## 7. Residual spread and distributional shape

The scatter and Q–Q plot address different aspects of adequacy. The Q–Q plot does not test independence. Serial, Koenker/Breusch–Pagan and influence diagnostics have calibration assumptions under dependence. Forty M3 observations exceed the Cook's-distance screening guide, which does not establish that they are errors.

## 8. Average gain, high-day failure

The fixed validation rule chooses M3, with M2 only 1.11% above the minimum. Overall signed error is positive, but high-day error is strongly negative. The high-day cutoff is 234.655 µg/m³, learned from training. There is no clipping or test-year refit; dependent errors preclude a naive independent-day interval for performance differences.

## 9. Exploratory temporal and weather extensions

The five candidates share dates. Extra weather is dew point and two wind-vector components; the lag is the previous calendar day's observed PM2.5. Log estimates use a training-only smearing factor times exp(linear predictor), minus one. This does not guarantee nonnegativity. The viewed test year supplies descriptive comparisons, not independent confirmation.

## 10. AR(1) sensitivity to five short gaps

Original GLSAR compresses rows across five two-day training gaps. The paired check holds estimation and first-observation treatment fixed. A separate dense covariance verifies wind coefficients and profile objectives. Nominal H1/H2 conclusions remain unchanged, including within-method Holm adjustment. This does not validate stationary Gaussian AR(1) or override the primary HAC/Holm result.

## 11. Cross-station consistency

Each station has its own eligible dates, centers and cutoff. All M2 wind intervals lie below zero. Seasonal findings vary; M3 beats the training-mean baseline at 11/12 sites, except Gucheng. Shared pollution and weather make these dependent sites, not independent replications.

## 12. High recall brings many false alarms

The concentration threshold is the training daily 95th percentile. Validation F1 selects the probability cutoff, breaking ties toward a higher value; test labels do not select it. A 0.5 cutoff detects none. AUC describes ranking, while this table shows the selected cutoff's burden. Rare, dependent events limit precision; odds-ratio intervals assume independence.

## 13. Two groups of training pollutant profiles

The existing verified heatmap displays the standardized training profiles and cluster labels. The largest merge-height gap for k=2…5 chooses two groups. The lower mean-PM2.5 group contains Changping, Dingling, Huairou, Shunyi. Group labels describe this period; they do not identify validated geographic or risk classes.

## 14. Limits of the evidence

Mention spatially matched weather, emissions/transport and boundary-layer information. HAC cannot repair an inadequate conditional mean. A common smearing factor can miss varying conditional error distributions. Cross-station consistency and separate implementation checks do not establish causal effects or independent scientific replication.

## 15. Model adequacy requires more than explained variance

Return to the question: fit reduction, inference and error behavior must be considered together. Smaller errors for exploratory temporal/weather models motivate further study without confirming them. A new evaluation should define the information available when an estimate is issued and avoid retuning on the current test year.

## 16. References and assistance

Full references and attribution appear in the report, including UCI's CC BY 4.0 license and Duan's retransformation method. Empirical numbers are this project's generated results. AI assistance is disclosed; the submitter remains responsible for interpretation and course-policy compliance. Numerical verification is not independent scientific replication.
