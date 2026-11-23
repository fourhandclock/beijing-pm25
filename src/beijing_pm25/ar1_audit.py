"""Exploratory sensitivity audit for the existing AR(1) calendar-gap limitation.

The original GLSAR estimates are retained. Paired conditional-likelihood fits
use identical estimation and first-observation treatment, changing only whether
successive retained dates are assumed one day apart or use their actual gaps.
No test responses, new predictors, or forecasting model are introduced.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import optimize, stats
from statsmodels.stats.multitest import multipletests

from .models import WEATHER, design_matrix


@dataclass
class ProfileAR1:
    rho: float
    parameters: pd.Series
    covariance: np.ndarray
    objective: float
    df_resid: int
    n_transitions: int
    calendar_gaps: int
    max_calendar_gap_days: int
    at_search_bound: bool


def conditional_fit_at_rho(x, y, gaps, rho):
    """Conditional AR(1) Gaussian profile at fixed rho, innovation variance 1.

    For a d-day gap, the transition coefficient is rho**d and its innovation
    variance is q_d = (1-rho**(2*d))/(1-rho**2). The first retained response is
    conditioned on in both sensitivity fits. Coefficient covariance uses the
    residual df correction and treats rho as fixed (plug-in approximation).
    """
    x, y = np.asarray(x, float), np.asarray(y, float)
    gaps = np.asarray(gaps)
    if (x.ndim != 2 or y.shape != (len(x),) or gaps.shape != (len(x)-1,)
            or not np.isfinite(x).all() or not np.isfinite(y).all()
            or not np.isfinite(gaps).all() or (gaps < 1).any()
            or not np.equal(gaps, np.floor(gaps)).all()):
        raise ValueError("AR audit needs finite aligned data and positive integer day gaps.")
    if not np.isfinite(rho) or abs(rho) >= 1:
        raise ValueError("Stationary AR(1) sensitivity requires abs(rho) < 1.")
    gaps = gaps.astype(int)
    transition = rho ** gaps
    q = (np.ones(len(gaps)) if abs(rho) < 1e-12 else
         -np.expm1(2 * gaps * np.log(abs(rho))) / (1 - rho * rho))
    wx = (x[1:] - transition[:, None] * x[:-1]) / np.sqrt(q)[:, None]
    wy = (y[1:] - transition * y[:-1]) / np.sqrt(q)
    m, p = wx.shape
    beta, _, rank, _ = np.linalg.lstsq(wx, wy, rcond=None)
    if m <= p or rank != p:
        raise ValueError("AR audit requires full rank and positive residual degrees of freedom.")
    error = wy - wx @ beta
    sse = float(error @ error)
    if not np.isfinite(sse) or sse <= 1e-24:
        raise ValueError("AR audit requires nonzero residual variation.")
    inverse = np.linalg.pinv(wx)
    covariance = (sse / (m - p)) * (inverse @ inverse.T)
    objective = float(m * np.log(sse / m) + np.log(q).sum())
    return beta, covariance, objective


def profile_ar1(design, response, spacing):
    if spacing not in ("rows", "calendar"):
        raise ValueError("AR audit spacing must be 'rows' or 'calendar'.")
    index = design.index
    if (not isinstance(index, pd.DatetimeIndex) or index.has_duplicates
            or not index.is_monotonic_increasing or not index.equals(index.normalize())
            or not response.index.equals(index)):
        raise ValueError("AR audit needs unique increasing daily dates and aligned responses.")
    actual = index.to_series().diff().dt.days.iloc[1:].to_numpy(dtype=int)
    gaps = actual if spacing == "calendar" else np.ones_like(actual)
    x, y = design.to_numpy(dtype=float), response.to_numpy(dtype=float)

    def objective(rho):
        return conditional_fit_at_rho(x, y, gaps, float(rho))[2]

    search = optimize.minimize_scalar(objective, bounds=(-0.98, 0.98), method="bounded",
                                      options={"xatol": 1e-9, "maxiter": 200})
    if not search.success or not np.isfinite(search.fun):
        raise ValueError("AR(1) conditional-likelihood sensitivity did not converge.")
    rho = float(search.x)
    beta, covariance, value = conditional_fit_at_rho(x, y, gaps, rho)
    return ProfileAR1(rho, pd.Series(beta, index=design.columns), covariance, value,
                      len(y)-1-x.shape[1], len(y)-1, int((actual > 1).sum()),
                      int(actual.max()), bool(abs(rho) > 0.97999))


def calendar_sensitivity(training, alpha, legacy):
    """Keep the original estimates and add paired row/calendar likelihood checks."""
    centres = {name: float(training[name].mean()) for name in WEATHER}
    rows = []
    for original in legacy.to_dict(orient="records"):
        rows.append({
            "method": "original_glsar_rows", "hypothesis": original["hypothesis"],
            "model": original["model"], "rho": original["ar1_rho"],
            "f_statistic_approx": original["f_statistic"], "df_num": original["df_num"],
            "df_resid": original["df_denom"], "p_value_approx": original["p_value"],
            "wind_coefficient": original["wind_coefficient"],
            "wind_ci_lower": original["wind_ci_lower"], "wind_ci_upper": original["wind_ci_upper"],
            "n_transitions": original["n_used"], "calendar_gaps": original["calendar_gaps_bridged"],
            "max_calendar_gap_days": int(training.index.to_series().diff().dt.days.max()),
            "conditional_profile_objective": np.nan, "rho_at_search_bound": False,
        })
    z = float(stats.norm.ppf(1 - alpha / 2))
    for spacing in ("rows", "calendar"):
        for hypothesis, model, prefix in (("H1: seasons (M1 -> M2)", "M2", "season_"),
                                          ("H2: wind x season (M2 -> M3)", "M3", "wind_x_")):
            design = design_matrix(training, centres, model)
            fit = profile_ar1(design, training["pm25"].astype(float), spacing)
            positions = [i for i, name in enumerate(design.columns) if name.startswith(prefix)]
            beta = fit.parameters.iloc[positions].to_numpy()
            covariance = fit.covariance[np.ix_(positions, positions)]
            statistic = float(beta @ np.linalg.solve(covariance, beta) / len(positions))
            wind = list(design.columns).index("wind_speed_c")
            se = float(np.sqrt(fit.covariance[wind, wind]))
            rows.append({
                "method": "conditional_ml_" + spacing, "hypothesis": hypothesis, "model": model,
                "rho": fit.rho, "f_statistic_approx": statistic, "df_num": len(positions),
                "df_resid": fit.df_resid,
                "p_value_approx": float(stats.f.sf(statistic, len(positions), fit.df_resid)),
                "wind_coefficient": float(fit.parameters.iloc[wind]),
                "wind_ci_lower": float(fit.parameters.iloc[wind]-z*se),
                "wind_ci_upper": float(fit.parameters.iloc[wind]+z*se),
                "n_transitions": fit.n_transitions, "calendar_gaps": fit.calendar_gaps,
                "max_calendar_gap_days": fit.max_calendar_gap_days,
                "conditional_profile_objective": fit.objective,
                "rho_at_search_bound": fit.at_search_bound,
            })
    table = pd.DataFrame(rows)
    table["p_holm_within_method"] = np.nan
    for method in table["method"].unique():
        mask = table["method"].eq(method)
        table.loc[mask, "p_holm_within_method"] = multipletests(
            table.loc[mask, "p_value_approx"], alpha=alpha, method="holm",
        )[1]
    return table
