# Reference and attribution check

Checked 23 November 2026 against primary sources. The final submission reports
this project's generated results; no published paper's error scores are used
as this project's results.

- **Dataset:** Chen, S. (2017), *Beijing Multi-Site Air Quality*, UCI Machine
  Learning Repository, DOI `10.24432/C5RK5G`, CC BY 4.0. The 12-site,
  March 2013–February 2017 scope and nearest-weather-station matching agree
  with [UCI documentation](https://archive.ics.uci.edu/dataset/501/beijing+multi+site+air+quality+data).
- **Retransformation:** Duan, N. (1983), *Smearing Estimate: A Nonparametric
  Retransformation Method*, JASA 78(383), 605–610, DOI
  [`10.1080/01621459.1983.10478017`](https://www.tandfonline.com/doi/abs/10.1080/01621459.1983.10478017).
- **Methods:** the final references link official statsmodels documentation for
  [nested F comparisons](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.RegressionResults.compare_f_test.html),
  [HAC covariance](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html)
  and [iterative GLSAR](https://www.statsmodels.org/stable/generated/statsmodels.regression.linear_model.GLSAR.html).
  Calendar-aware handling in this project is explicitly documented rather
  than assumed to be the library's default row-spacing behavior.
- **Original handoff background:** Wang, Yusheng and Du, Ruiyan,
  *Same-Hour Estimation and Multi-Horizon Forecasting of PM2.5 in Beijing:
  Model Comparison and Feature-Group Contributions*, arXiv:2607.07279v3,
  revised 25 August 2026. The title, authors and version match the
  [official arXiv record](https://arxiv.org/abs/2607.07279).
- **Original handoff background:** Gondal, Moazzam Umer; ul Qudous, Hamad;
  Farhan, Asma Ahmad; and Alamri, Sultan, *Interpretable PM2.5 Forecasting
  for Urban Air Quality: A Comparative Study of Adaptive Time-Series Models*,
  arXiv:2603.25495v2, revised 19 October 2026. The
  [official record](https://arxiv.org/abs/2603.25495) verifies the metadata;
  the [revised full text](https://arxiv.org/html/2603.25495v2) describes
  API-derived estimates and EWMA residual correction under Perfect Prognosis.
  It is not a directly comparable UCI daily-regression benchmark. This
  optional correction was not implemented in the submission.

The forecasting papers are retained as handoff background rather than invoked
to validate this investigation. The final report's method references are the
dataset record, Duan and official method documentation. No causal claim,
operational forecast claim or independently replicated observational evidence
is attributed to these computational checks.
