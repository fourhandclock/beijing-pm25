"""Classical comparisons, calendar-day HAC sensitivity, and residual diagnostics."""

import numpy as np
import pandas as pd
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.multitest import multipletests

from .describe import calendar_acf
from .models import SEASONS


def calendar_hac(design: pd.DataFrame, residuals: pd.Series, max_lag: int):
    """Bartlett/Newey–West sandwich, preserving calendar-day distances at gaps.

    Missing daily score contributions are zero; no missing target is imputed.
    Finite-sample correction is n_observed/(n_observed - p), not n_calendar/(...).
    """
    index = design.index
    if not isinstance(index, pd.DatetimeIndex) or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("HAC needs unique, increasing calendar dates.")
    if not index.equals(index.normalize()) or not residuals.index.equals(index):
        raise ValueError("HAC residuals and daily design dates must align exactly.")
    x, errors = design.to_numpy(dtype=float), residuals.to_numpy(dtype=float)
    n, p = x.shape
    if n <= p or np.linalg.matrix_rank(x) != p or not np.isfinite(x).all() or not np.isfinite(errors).all():
        raise ValueError("HAC needs finite data and a full-rank design with positive residual degrees of freedom.")
    grid = pd.date_range(index.min(), index.max(), freq="D")
    if type(max_lag) is not int or not 0 <= max_lag < len(grid):
        raise ValueError("HAC lag must be a nonnegative integer shorter than the calendar.")
    scores = pd.DataFrame(x * errors[:, None], index=index).reindex(grid, fill_value=0).to_numpy()
    meat = scores.T @ scores
    for lag in range(1, max_lag + 1):
        cross = scores[lag:].T @ scores[:-lag]
        meat += (1 - lag / (max_lag + 1)) * (cross + cross.T)
    inverse_x = np.linalg.pinv(x)
    bread = inverse_x @ inverse_x.T
    covariance = (n / (n - p)) * (bread @ meat @ bread)
    return (covariance + covariance.T) / 2


def joint_wald(parameters, covariance, positions):
    beta = np.asarray(parameters)[positions]
    restricted_covariance = np.asarray(covariance)[np.ix_(positions, positions)]
    if np.linalg.matrix_rank(restricted_covariance) != len(positions):
        raise ValueError("Joint covariance is singular; cannot report a valid joint Wald statistic.")
    statistic = float(beta @ np.linalg.solve(restricted_covariance, beta))
    if statistic < -1e-8:
        raise ValueError("Negative Wald statistic indicates an invalid covariance.")
    statistic = max(0.0, statistic)
    return statistic, float(stats.chi2.sf(statistic, len(positions)))


def model_tables(models, config):
    coefficients, summaries = [], []
    covariances = {}
    for name, result in models.items():
        design = pd.DataFrame(result.model.exog, index=result.model.data.row_labels,
                              columns=result.model.exog_names)
        covariances[name] = {lag: calendar_hac(design, result.resid, lag) for lag in config.hac_lag_days}
        hac = covariances[name][config.primary_hac_lag_days]
        classical_ci = result.conf_int(alpha=config.alpha)
        z_critical = float(stats.norm.ppf(1 - config.alpha / 2))
        for index, (term, value) in enumerate(result.params.items()):
            standard_error = float(np.sqrt(max(0.0, hac[index, index])))
            z = float(value / standard_error) if standard_error else np.nan
            coefficients.append({
                "model": name, "term": term, "estimate": float(value),
                "classical_se": float(result.bse.iloc[index]),
                "classical_t": float(result.tvalues.iloc[index]),
                "classical_p": float(result.pvalues.iloc[index]),
                "classical_ci_lower": float(classical_ci.iloc[index, 0]),
                "classical_ci_upper": float(classical_ci.iloc[index, 1]),
                "hac_lag_days": config.primary_hac_lag_days,
                "hac_se": standard_error, "hac_z": z,
                "hac_p": float(2 * stats.norm.sf(abs(z))),
                "hac_ci_lower": float(value - z_critical * standard_error),
                "hac_ci_upper": float(value + z_critical * standard_error),
            })
        summaries.append({
            "model": name, "n": int(result.nobs), "parameters": len(result.params),
            "df_resid": int(result.df_resid), "design_rank": int(np.linalg.matrix_rank(design)),
            "condition_number_centered": float(np.linalg.cond(design)),
            "r_squared": float(result.rsquared), "adjusted_r_squared": float(result.rsquared_adj),
            "sse": float(result.ssr), "residual_standard_error": float(np.sqrt(result.mse_resid)),
            "aic_working_iid": float(result.aic), "bic_working_iid": float(result.bic),
        })

    classical, robust = [], []
    for hypothesis, restricted_name, full_name in (("H1_season", "M1", "M2"), ("H2_wind_by_season", "M2", "M3")):
        restricted, full = models[restricted_name], models[full_name]
        if not restricted.model.data.row_labels.equals(full.model.data.row_labels):
            raise ValueError("Nested comparisons require identical fitted dates.")
        old_columns, new_columns = restricted.model.exog_names, full.model.exog_names
        if new_columns[:len(old_columns)] != old_columns or not np.array_equal(
            restricted.model.exog, full.model.exog[:, :len(old_columns)]
        ):
            raise ValueError("The proposed models are not nested in the declared design.")
        f_value, p_value, df_difference = full.compare_f_test(restricted)
        classical.append({
            "hypothesis": hypothesis, "restricted": restricted_name, "full": full_name,
            "n": int(full.nobs), "sse_restricted": float(restricted.ssr), "sse_full": float(full.ssr),
            "sse_reduction": float(restricted.ssr - full.ssr),
            "df_added": int(df_difference), "df_resid_full": int(full.df_resid),
            "f_statistic": float(f_value), "p_value_iid": float(p_value),
        })
        positions = list(range(len(old_columns), len(new_columns)))
        for lag in config.hac_lag_days:
            statistic, p_value = joint_wald(full.params, covariances[full_name][lag], positions)
            robust.append({
                "hypothesis": hypothesis, "restricted": restricted_name, "full": full_name,
                "hac_lag_calendar_days": lag, "primary_bandwidth": lag == config.primary_hac_lag_days,
                "n": int(full.nobs), "wald_chi2": statistic, "df": len(positions),
                "p_value_hac": p_value,
            })
    robust = pd.DataFrame(robust)
    primary = robust["primary_bandwidth"]
    robust["p_holm_primary"] = np.nan
    robust.loc[primary, "p_holm_primary"] = multipletests(
        robust.loc[primary, "p_value_hac"], alpha=config.alpha, method="holm",
    )[1]
    return pd.DataFrame(summaries), pd.DataFrame(coefficients), pd.DataFrame(classical), robust, covariances


def calendar_bg(result, lag_days):
    """Complete-calendar-lag BG-style auxiliary regression; reference p is approximate."""
    index = result.model.data.row_labels
    grid = pd.date_range(index.min(), index.max(), freq="D")
    residuals = result.resid.reindex(grid)
    design = pd.DataFrame(result.model.exog, index=index, columns=result.model.exog_names)
    auxiliary = design.copy()
    auxiliary["response_residual"] = result.resid
    for lag in range(1, lag_days + 1):
        auxiliary[f"residual_lag_{lag}"] = residuals.shift(lag).reindex(index)
    auxiliary = auxiliary.dropna()
    extra = [f"residual_lag_{lag}" for lag in range(1, lag_days + 1)]
    x = auxiliary[[*design.columns, *extra]]
    n, p = x.shape
    if n <= p or np.linalg.matrix_rank(x) != p:
        raise ValueError("Insufficient complete calendar-lag observations for the serial diagnostic.")
    full = sm.OLS(auxiliary["response_residual"], x).fit()
    restricted = sm.OLS(auxiliary["response_residual"], auxiliary[list(design.columns)]).fit()
    f_statistic, f_p_value, _ = full.compare_f_test(restricted)
    lm = float(n * full.rsquared)
    return {"serial_lag_calendar_days": lag_days, "serial_auxiliary_n": n,
            "serial_auxiliary_r_squared": float(full.rsquared),
            "serial_lm_approx": lm, "serial_lm_p_approx": float(stats.chi2.sf(lm, lag_days)),
            "serial_auxiliary_f": float(f_statistic), "serial_auxiliary_f_p_iid": float(f_p_value)}


def residual_tables(models, training_calendar, config):
    diagnostics, influences, correlations, calendars = [], [], [], []
    for name, result in models.items():
        n, p = int(result.nobs), len(result.params)
        influence = result.get_influence()
        cook = influence.cooks_distance[0]
        leverage = influence.hat_matrix_diag
        studentized = influence.resid_studentized_internal
        bp_lm, bp_p, bp_f, bp_f_p = het_breuschpagan(result.resid, result.model.exog, robust=True)
        jb = stats.jarque_bera(result.resid)
        full_calendar = pd.DataFrame(index=training_calendar)
        full_calendar["fitted"] = result.fittedvalues
        full_calendar["residual"] = result.resid
        full_calendar["model"] = name
        full_calendar.index.name = "date"
        calendars.append(full_calendar.reset_index())
        acf = calendar_acf(full_calendar["residual"], config.residual_acf_lag_days)
        acf.insert(0, "model", name)
        correlations.append(acf)
        diagnostics.append({
            "model": name, "n": n, "residual_mean": float(result.resid.mean()),
            "residual_skewness": float(stats.skew(result.resid, bias=False)),
            "residual_pearson_kurtosis": float(stats.kurtosis(result.resid, fisher=False, bias=False)),
            "jarque_bera": float(jb.statistic), "jarque_bera_p_iid": float(jb.pvalue),
            "koenker_bp_lm": float(bp_lm), "koenker_bp_p_iid": float(bp_p),
            "koenker_bp_f": float(bp_f), "koenker_bp_f_p_iid": float(bp_f_p),
            "calendar_lag1_residual_correlation": float(acf.iloc[0]["correlation"]),
            "lag1_paired_days": int(acf.iloc[0]["paired_days"]),
            "cook_screen_count": int((cook > 4 / n).sum()),
            "leverage_screen_count": int((leverage > 2 * p / n).sum()),
            "studentized_screen_count": int((np.abs(studentized) > 3).sum()),
            **calendar_bg(result, config.serial_test_lag_days),
        })
        influences.append(pd.DataFrame({
            "date": result.model.data.row_labels, "model": name,
            "observed": result.model.endog, "fitted": result.fittedvalues.to_numpy(),
            "residual": result.resid.to_numpy(), "leverage": leverage,
            "internally_studentized_residual": studentized, "cooks_distance": cook,
            "cook_screen": cook > 4 / n, "leverage_screen": leverage > 2 * p / n,
            "studentized_screen": np.abs(studentized) > 3,
        }))
    return (pd.DataFrame(diagnostics), pd.concat(influences, ignore_index=True),
            pd.concat(correlations, ignore_index=True), pd.concat(calendars, ignore_index=True))


def seasonal_wind_slopes(model, covariance, alpha, hac_lag):
    rows = []
    names = list(model.params.index)
    z_critical, t_critical = stats.norm.ppf(1 - alpha / 2), stats.t.ppf(1 - alpha / 2, model.df_resid)
    for season in SEASONS:
        contrast = np.zeros(len(names))
        contrast[names.index("wind_speed_c")] = 1
        if season != "winter":
            contrast[names.index("wind_x_" + season)] = 1
        value = float(contrast @ model.params)
        se = float(np.sqrt(contrast @ covariance @ contrast))
        classical_se = float(np.sqrt(contrast @ model.cov_params() @ contrast))
        rows.append({
            "model": "M3", "season": season, "pm25_change_per_1_mps_wind": value,
            "classical_se": classical_se, "classical_ci_lower": value - t_critical * classical_se,
            "classical_ci_upper": value + t_critical * classical_se,
            "hac_lag_days": hac_lag, "hac_se": se,
            "hac_ci_lower": value - z_critical * se, "hac_ci_upper": value + z_critical * se,
        })
    return pd.DataFrame(rows)
