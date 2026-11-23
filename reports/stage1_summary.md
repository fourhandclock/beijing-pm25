# Stage 1 — data audit and baseline infrastructure

Run completed at 2026-11-23T16:28:07+00:00. **This stage audits the data and does not fit models.** Regression results are reported separately in [Stage 2](stage2_analysis.md); subsequent extensions are [exploratory](stage3_extensions.md).

## Source and reproducibility

- Source: [UCI Beijing Multi-Site Air Quality](https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data); [dataset DOI](https://doi.org/10.24432/C5RK5G).
- Citation: Chen, S. (2017). Beijing Multi-Site Air Quality [Dataset]. UCI Machine Learning Repository. License: CC BY 4.0.
- Acquisition: `official_uci_download`, 2026-11-19T16:32:10+00:00. Retrieved directly from UCI.
- Preserved archive: `data/raw/uci_beijing_multi_site.zip` (8,192,212 bytes).
- Archive SHA-256: `b04da438b2f331ac0ffd45aebdfec0d20d2367feb5f6948c4b1f7ce1191e33c4`. No provider release-version string is assumed.
- All 12 original station CSVs were checked; the wrapper's auxiliary `data.csv` and `test.csv` were excluded.
- Per-station member hashes, row counts, missingness, calendar gaps, configuration, code hashes, environment versions, and output hashes are saved in the tables and `results/stage1_run.json`.

Exact invocation for this run:

```bash
.venv/bin/python -W error -m beijing_pm25 stage1
```

From the project directory, reproduce with:

```bash
.venv/bin/python -m beijing_pm25 download
.venv/bin/python -m beijing_pm25 stage1
.venv/bin/python -m beijing_pm25 verify
.venv/bin/python -m pytest
```

The download command reuses a preserved archive only after checking its hash. Tests use small explicitly synthetic fixtures, separate from the empirical dataset; test outcomes are recorded in `reports/implementation_checks.md` when that check has been run by the implementer.

## Declared calendar and cleaning decisions

- Complete calendar: `2013-03-01` inclusive to `2017-03-01` exclusive, separately for each station.
- Training: start to `2015-03-01` exclusive. Validation: `2015-03-01` to `2016-03-01` exclusive. Final test: `2016-03-01` to calendar end exclusive. The two full training years and one year each for validation/test in the default configuration cover all seasons.
- Hour fields are interpreted as local civil time, assumed **Asia/Shanghai**; UCI's displayed metadata do not explicitly tag a timezone. No UTC or daylight-saving conversion is imposed.
- A missing calendar hour remains a missing observation; absent dates remain explicit daily rows. Duplicate station/timestamp rows, mixed station labels, invalid calendar fields, and malformed numeric text are errors, not silently repaired. Unordered input is sorted by calendar alignment and counted.
- Original missing values remain missing. Nonfinite measurements, negative pollutant concentrations/rainfall/wind speed, nonpositive pressure, and unrecognized wind directions are masked and counted. Negative temperatures are valid. High positive concentrations are retained. No imputation or clipping is performed.
- PM2.5, temperature, pressure, and wind speed use arithmetic means of their own valid hourly values, with **at least 18/24** valid hours each.
- Rainfall is the sum of **all 24 valid hourly precipitation entries**. A partial total, including an all-missing total, remains missing. This assumes the hourly precipitation entries are interval amounts; sensor semantics are not independently validated.
- An analysis day also needs at least **18 hours with all five core fields observed together**. Variable-specific means can still use different subsets; the overlap count is retained. Every exclusion reason is saved; reason counts overlap and must not be added together.
- Seasons are fixed meteorological seasons: DJF/MAM/JJA/SON. No seasonal boundaries were tuned.

## Station choice and retention

**Selected primary station: Wanliu.** Automatic choice: most analysis-eligible **training** days, then most valid training PM2.5 hours, then alphabetical station name. Validation/test coverage and concentration levels do not enter the choice. The rule was declared in `config/stage1.json` and the implementation before the first empirical run.

| Rank | Station | Eligible training days | Valid training PM2.5 hours |
| --- | --- | --- | --- |
| 1 | Wanliu | 725 | 17399 |
| 2 | Nongzhanguan | 718 | 17281 |
| 3 | Dongsi | 717 | 17260 |
| 4 | Guanyuan | 715 | 17198 |
| 5 | Wanshouxigong | 714 | 17263 |
| 6 | Aotizhongxin | 706 | 16990 |
| 7 | Tiantan | 700 | 17134 |
| 8 | Gucheng | 696 | 17200 |
| 9 | Changping | 694 | 17182 |
| 10 | Dingling | 689 | 17151 |
| 11 | Shunyi | 689 | 17049 |
| 12 | Huairou | 679 | 16882 |

For Wanliu, there are 35,064 source hourly rows of 35,064 expected slots, 0 absent hourly rows, and no duplicate timestamps. 0 invalid measurement cells were masked. See `hourly_missingness.csv` for missing-value counts by variable and interval.

| Interval | Calendar days | PM2.5-qualified days | Analysis-eligible days | Excluded days |
| --- | --- | --- | --- | --- |
| all | 1461 | 1449 | 1441 | 20 |
| train | 730 | 727 | 725 | 5 |
| validation | 366 | 359 | 359 | 7 |
| test | 365 | 363 | 357 | 8 |

`data/processed/Wanliu_daily.csv` retains the entire calendar with counts, split labels, eligibility flags and exclusion reasons. `Wanliu_analysis_ready.csv` contains only the eligible days and carries the same metadata. It supplies a common sample for the nested comparisons; retention alone is not evidence that OLS assumptions hold.

## Training response and time structure

Among 725 eligible training days, daily PM2.5 has mean 90.774, median 72.042, standard deviation 68.598, minimum 4.292, maximum 417.875, and skewness 1.441 on the original µg/m³ scale. Log1p skewness is -0.450; this is a descriptive comparison, **not a finalized model response transformation**.

Lag-one response correlation is 0.536, based on 723 paired calendar days. The ACF uses qualified training daily responses, preserving missing calendar dates. It is descriptive: this stage computes no residuals, independence p-value or white-noise confidence bands. Daily aggregation does not establish independent errors.

All six figures use training observations or training completeness only. Each is saved as PNG and editable/exportable SVG in `results/figures/`:

1. `station_training_completeness`: transparent selection ranking.
2. `hourly_training_missingness`: unusable core-field percentages at each station.
3. `training_daily_series`: qualified daily response and valid-hour counts.
4. `training_response_distribution`: original and log1p daily response distributions.
5. `training_seasonal_distribution`: within-training seasonal response distributions; extremes retained.
6. `training_calendar_acf`: response correlation at calendar-day lags, with gaps retained.

The full-archive missingness audit is descriptive. Validation/test target distributions are not plotted or used for station/response decisions. No imputation, scaling, model selection, extreme-day cutoff, or adaptive smoothing parameter has been learned from those intervals.

## Interpretation limits and implications for regression

- This is one station in a historical observational dataset. Missingness may be informative; completeness filtering can change seasonal composition. Other stations and years need separate assessment.
- Meteorology in UCI is matched from nearby weather stations. These associations cannot establish causal pollution effects or identify an emissions source.
- Same-day observed weather and daily target means support a contemporaneous explanatory study. They do not establish a deployable advance forecast.
- Response-scale decisions must precede fitting on a common sample. Marginal response skewness alone does not require log1p or diagnose conditional regression errors.
- Residual dependence, heteroscedasticity and influence require checks after fitting. Classical partial F-tests and HAC joint Wald tests have different assumptions and reference distributions.
- Reproduction instructions and current document checks are documented in [reproducibility](reproducibility.md) and [editorial verification](stage5_refinement.md).

This report supplies the data-quality evidence for the regression study. It makes no claim of model adequacy or estimation performance.
