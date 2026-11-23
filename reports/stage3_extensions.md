# Stage 3 — exploratory extensions

> **Status: exploratory.** These analyses were added after the Stage 2 test year had been scored.
> Fitting and preprocessing use training observations; the logistic probability cutoff uses validation.
> Because the test year had already been examined, these results provide no new confirmatory test.
> The prespecified Stage 2 analysis and its frozen test evaluation remain separate.

Command: `python -m beijing_pm25 stage3`

## 1. Exploratory model comparisons at Wanliu

Common sample: Stage 2's eligible days that also have dew point, wind direction and the previous calendar day's PM2.5 (721 training, 354 validation, 355 test days; 11 fewer than Stage 2 in total).

| Model | Validation MAE | Test MAE | Test RMSE | Test smog-day mean error | Test predictions < 0 |
|---|---|---|---|---|---|
| M3 refit on common sample | 50.4 | 46.7 | 60.9 | -161.7 | 3 |
| M3 on log(1 + PM2.5) | 50.0 | 45.1 | 58.3 | -132.1 | 0 |
| M3 + previous day's PM2.5 | 37.7 | 35.5 | 47.8 | -103.1 | 11 |
| M3 + dew point + wind direction | 46.9 | 40.7 | 55.4 | -143.2 | 25 |
| Log scale + previous day + dew point + wind direction | 32.7 | 29.0 | 40.8 | -39.2 | 0 |
| Training mean (baseline) | 57.0 | 55.3 | 73.1 | -215.9 | 0 |

Smog day = PM2.5 ≥ 233.8 µg/m³ (training 95th percentile of this sample).
Negative mean error = underestimate. Lowest validation MAE: **Log scale + previous day + dew point + wind direction** (32.7 vs 50.4 for M3).

| Model | Scale | Parameters | Training R² (own scale) | Smearing factor | Training predictions < 0 |
|---|---|---|---|---|---|
| M3 refit on common sample | original | 11 | 0.220 | – | 10 |
| M3 on log(1 + PM2.5) | log1p | 11 | 0.315 | 1.239 | 0 |
| M3 + previous day's PM2.5 | original | 12 | 0.506 | – | 14 |
| M3 + dew point + wind direction | original | 14 | 0.417 | – | 18 |
| Log scale + previous day + dew point + wind direction | log1p | 15 | 0.626 | 1.117 | 0 |

The M3 row is refitted on this smaller common sample; it is not the original frozen Stage 2 evaluation.
R² on the log scale is not comparable with R² on the original scale. For a log1p model, estimates are
back-transformed as exp(fitted log1p response) × mean(exp(training residual)) − 1. This global Duan
smearing factor uses training residuals only and need not remove conditional bias under heteroscedasticity.
The transformation permits estimates above −1; nonnegative estimates in these runs are an empirical result,
not a mathematical guarantee. No estimate is silently clipped.

### Do the added variables help beyond M3? (training data)

| Comparison | Added | df | Partial F | Classical p | HAC(7-day) p | ΔR² |
|---|---|---|---|---|---|---|
| M3 -> M3_met | dew point + wind direction | 3 | 79.38 | 2.9e-44 | 2.1e-27 | 0.197 |
| M3 -> M3_lag | previous day's PM2.5 | 1 | 409.76 | 3.0e-72 | 1.9e-68 | 0.286 |

### Coefficients of the added variables (HAC 7-day standard errors)

| Model | Response scale | Term | Estimate | 95% CI low | 95% CI high | HAC p |
|---|---|---|---|---|---|---|
| M3_met | original | dew_point_c | 8.48 | 6.94 | 10.01 | 2.1e-27 |
| M3_met | original | southerly_c | -2.81 | -9.04 | 3.43 | 0.378 |
| M3_met | original | westerly_c | -9.11 | -16.37 | -1.85 | 0.014 |
| M3_lag | original | pm25_lag1_c | 0.54 | 0.48 | 0.60 | 1.9e-68 |
| M3_log_lag_met | log1p | dew_point_c | 0.07 | 0.06 | 0.08 | 6.2e-31 |
| M3_log_lag_met | log1p | southerly_c | 0.12 | 0.06 | 0.18 | 1.6e-04 |
| M3_log_lag_met | log1p | westerly_c | -2.9e-03 | -0.09 | 0.08 | 0.947 |
| M3_log_lag_met | log1p | log_pm25_lag1_c | 0.36 | 0.31 | 0.40 | 3.6e-52 |

Units: dew point per °C; southerly/westerly per 1 m/s of mean wind vector from the south/west; previous-day PM2.5 per µg/m³.
Original-response coefficients describe changes in µg/m³. Log1p-response coefficients describe changes
in log(1 + PM2.5); exp(coefficient) scales 1 + PM2.5 for a unit change in the stated predictor.
The combined model uses log(1 + previous-day PM2.5), not the untransformed lag.

## 2. Modelling the autocorrelation directly: regression with AR(1) errors

Feasible GLS (iterated Cochrane–Orcutt, statsmodels GLSAR) on the Stage 2 training sample.

| Test | AR(1) ρ | F | df1 | df2 | p | Wind coef. | CI low | CI high |
|---|---|---|---|---|---|---|---|---|
| H1: seasons (M1 -> M2) | 0.572 | 4.61 | 3 | 716 | 0.003 | -34.0 | -40.7 | -27.3 |
| H2: wind x season (M2 -> M3) | 0.569 | 0.86 | 3 | 713 | 0.462 | -36.6 | -47.0 | -26.2 |

GLSAR treats consecutive eligible rows as consecutive days; it bridges 5 calendar gaps in training.
Its nominal tests are exploratory and conditional on the fitted error model; they do not override the
primary HAC/Holm conclusions. The original values are retained. A paired likelihood sensitivity to
actual calendar gaps is reported separately in [the Stage 4 statistical audit](stage4/statistical_audit.md).

## 3. Logistic regression for smog days

Outcome: daily PM2.5 ≥ 234.7 µg/m³ (training 95th percentile); predictors as M2.
37 training smog days; McFadden pseudo-R² 0.144.
Cutoff chosen to maximise F1 on **validation**: 0.132, then applied unchanged to test.

| Split | Days | Smog days | AUC | Caught | False alarms | Missed | Recall | Precision |
|---|---|---|---|---|---|---|---|---|
| train | 725 | 37 | 0.799 | 14 | 63 | 23 | 0.38 | 0.18 |
| validation | 359 | 16 | 0.858 | 10 | 27 | 6 | 0.62 | 0.27 |
| test | 357 | 17 | 0.927 | 15 | 44 | 2 | 0.88 | 0.25 |

With the default 0.5 cutoff the model flags 0 of 17 test smog days.

| Term | Odds ratio | CI low | CI high | p (assumes independence) |
|---|---|---|---|---|
| temperature_c | 0.959 | 0.881 | 1.043 | 0.329 |
| wind_speed_c | 0.115 | 0.041 | 0.326 | 4.6e-05 |
| rainfall_c | 0.963 | 0.835 | 1.111 | 0.606 |
| pressure_c | 0.970 | 0.902 | 1.043 | 0.414 |
| season_spring | 0.831 | 0.197 | 3.507 | 0.801 |
| season_summer | 0.109 | 0.011 | 1.102 | 0.060 |
| season_autumn | 0.563 | 0.159 | 1.994 | 0.373 |

Odds ratios are per 1 unit of the centred predictor (°C, m/s, mm, hPa) or versus winter. Their usual
intervals and p-values assume independent days; residual dependence in the core models motivates
caution about that assumption here. These are exploratory associations. The high-day definition is
a training-sample quantile, not a health-based regulatory threshold.

## 4. Do the Stage 2 findings hold at the other 11 stations?

Same Stage 1 rules and Stage 2 models, fitted on each station's own training days.

| Station | Train days | M3 R² | M2 wind coef. | CI low | CI high | H1 Holm p | H2 Holm p | Test MAE M3 | Test MAE baseline |
|---|---|---|---|---|---|---|---|---|---|
| Aotizhongxin | 706 | 0.206 | -45.7 | -54.3 | -37.0 | 0.023 | 0.042 | 42.3 | 54.4 |
| Changping | 694 | 0.235 | -38.0 | -44.9 | -31.0 | 0.030 | 0.367 | 38.7 | 47.9 |
| Dingling | 689 | 0.208 | -36.4 | -44.4 | -28.5 | 0.136 | 0.136 | 37.4 | 46.1 |
| Dongsi | 717 | 0.257 | -40.8 | -47.4 | -34.2 | 0.040 | 0.087 | 45.6 | 57.5 |
| Guanyuan | 715 | 0.221 | -46.9 | -55.5 | -38.4 | 0.089 | 0.089 | 42.2 | 53.8 |
| Gucheng | 696 | 0.285 | -65.1 | -77.2 | -52.9 | 0.029 | 0.216 | 55.8 | 54.8 |
| Huairou | 679 | 0.142 | -31.3 | -38.8 | -23.7 | 0.003 | 0.598 | 40.9 | 46.2 |
| Nongzhanguan | 718 | 0.274 | -41.7 | -48.3 | -35.0 | 0.073 | 0.044 | 44.2 | 56.3 |
| Shunyi | 689 | 0.172 | -33.8 | -40.7 | -26.9 | 0.024 | 0.057 | 44.5 | 51.6 |
| Tiantan | 700 | 0.261 | -39.0 | -45.2 | -32.8 | 0.117 | 0.117 | 42.3 | 53.8 |
| Wanliu | 725 | 0.221 | -49.0 | -57.6 | -40.5 | 0.062 | 0.062 | 46.8 | 55.3 |
| Wanshouxigong | 714 | 0.282 | -48.1 | -56.8 | -39.5 | 0.337 | 0.410 | 44.0 | 56.0 |

- Wind interval below zero at every station: **yes**.
- H1 (season) significant after Holm at 6 of 12 stations; H2 (wind × season) at 2 of 12.
- M3 beats the training-mean baseline on test MAE at 11 of 12 stations.

The 12 stations share one city's air, so agreement shows cross-station consistency, not independent
scientific replication. Holm correction covers two hypotheses within each station, not all 24 tests
across stations. These comparisons are exploratory and use station-specific eligible samples.

## 5. Cluster analysis of stations

Ward hierarchical clustering on z-scored training-period means of PM2.5, PM10, SO2, NO2, CO, O3.
k chosen as the largest gap in merge heights for k in 2–5: **k = 2**.
Cluster numbers are ordered by training mean PM2.5 (1 = lower mean PM2.5).

| Station | Cluster | PM2.5 | PM10 | SO2 | NO2 | CO | O3 |
|---|---|---|---|---|---|---|---|
| Changping | 1 | 76.9 | 100.2 | 21.4 | 44.2 | 1,181 | 59.8 |
| Dingling | 1 | 70.6 | 85.9 | 15.2 | 29.4 | 904 | 66.7 |
| Huairou | 1 | 73.8 | 97.7 | 17.4 | 37.8 | 1,067 | 61.7 |
| Shunyi | 1 | 81.9 | 103.7 | 17.3 | 44.2 | 1,220 | 55.5 |
| Aotizhongxin | 2 | 86.4 | 117.5 | 23.4 | 63.7 | 1,240 | 48.2 |
| Dongsi | 2 | 88.0 | 112.2 | 24.6 | 56.7 | 1,390 | 57.5 |
| Guanyuan | 2 | 86.4 | 111.8 | 23.5 | 61.9 | 1,322 | 54.9 |
| Gucheng | 2 | 86.3 | 123.3 | 19.8 | 61.3 | 1,404 | 55.5 |
| Nongzhanguan | 2 | 88.3 | 116.0 | 25.1 | 61.6 | 1,352 | 55.9 |
| Tiantan | 2 | 86.4 | 112.2 | 19.5 | 55.0 | 1,344 | 54.2 |
| Wanliu | 2 | 90.6 | 122.1 | 25.1 | 72.3 | 1,379 | 43.5 |
| Wanshouxigong | 2 | 87.2 | 119.2 | 22.9 | 59.5 | 1,455 | 54.4 |

| k | Merge-height gap | Chosen |
|---|---|---|
| 2 | 5.736 | yes |
| 3 | 0.385 | no |
| 4 | 1.174 | no |
| 5 | 0.209 | no |

Units: µg/m³. Profiles average each pollutant's qualified training daily means; available days can
differ by pollutant. With 12 stations, the groups are descriptive. No geographical or causal separation
is established by clustering pollutant profiles alone.

## What this adds and what it cannot fix

- Adding the previous day's PM2.5 is the largest single improvement: day-to-day persistence is what the
  weather-only model misses most. It turns the model into a same-day explanation that uses yesterday's
  measurement, which is still not a forecast of tomorrow.
- The log models produced no negative estimates in these runs and reduced high-day underestimation;
  their response scale and information set differ from the core regression.
- None of this can make the results causal, recover missing drivers (emissions, regional transport,
  mixing height), or provide a fresh confirmatory test year: that would need data after February 2017.

Figures: `results/stage3/figures/`. Tables: `results/stage3/tables/`. Run record: `results/stage3/run.json`.
