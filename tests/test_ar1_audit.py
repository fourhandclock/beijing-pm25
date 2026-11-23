"""Calendar-gap sensitivity is checked against a dense conditional covariance."""

import numpy as np
import pandas as pd
import pytest
from scipy import linalg

from beijing_pm25.ar1_audit import conditional_fit_at_rho, profile_ar1


@pytest.mark.parametrize("rho", [0.0, 0.6, -0.4])
def test_transition_whitening_matches_dense_conditional_gls(rho):
    days = np.array([0, 1, 3, 4, 7, 8])
    x = np.column_stack([np.ones(6), [2, -1, 4, 0, 3, 5]])
    y = np.array([5, 3, 8, 2, 1, 6], dtype=float)
    beta, covariance, objective = conditional_fit_at_rho(x, y, np.diff(days), rho)
    t = days[1:]
    conditional = (rho ** np.abs(t[:, None]-t[None, :]) - rho ** (t[:, None]+t[None, :])) / (1-rho*rho)
    z = x[1:] - (rho ** t)[:, None] * x[0]
    response = y[1:] - rho ** t * y[0]
    precision_z = linalg.solve(conditional, z, assume_a="pos")
    bread = linalg.inv(z.T @ precision_z)
    expected_beta = bread @ (z.T @ linalg.solve(conditional, response, assume_a="pos"))
    error = response - z @ expected_beta
    sse = float(error @ linalg.solve(conditional, error, assume_a="pos"))
    expected_covariance = sse / (len(t)-x.shape[1]) * bread
    expected_objective = len(t)*np.log(sse/len(t)) + np.linalg.slogdet(conditional)[1]
    np.testing.assert_allclose(beta, expected_beta, rtol=1e-10, atol=1e-10)
    np.testing.assert_allclose(covariance, expected_covariance, rtol=1e-10, atol=1e-10)
    assert objective == pytest.approx(expected_objective)


def test_row_and_calendar_modes_are_identical_without_missing_dates():
    random = np.random.default_rng(18)
    index = pd.date_range("2013-03-01", periods=80, freq="D")
    design = pd.DataFrame({"constant": 1.0, "x": random.normal(size=80)}, index=index)
    response = pd.Series(2 + 3*design["x"] + random.normal(size=80), index=index)
    rows = profile_ar1(design, response, "rows")
    calendar = profile_ar1(design, response, "calendar")
    assert rows.rho == pytest.approx(calendar.rho, abs=1e-12)
    np.testing.assert_allclose(rows.parameters, calendar.parameters, rtol=1e-12)
    assert calendar.calendar_gaps == 0


def test_calendar_gaps_are_recorded_and_alignment_is_required():
    random = np.random.default_rng(21)
    index = pd.date_range("2013-03-01", periods=50, freq="D").delete([8, 9, 30])
    design = pd.DataFrame({"constant": 1.0, "x": random.normal(size=len(index))}, index=index)
    response = pd.Series(5 + 2*design["x"] + random.normal(size=len(index)), index=index)
    fit = profile_ar1(design, response, "calendar")
    assert fit.calendar_gaps == 2 and fit.max_calendar_gap_days == 3
    assert fit.n_transitions == len(index)-1 and not fit.at_search_bound
    with pytest.raises(ValueError, match="aligned"):
        profile_ar1(design, response.iloc[::-1], "calendar")
    with pytest.raises(ValueError, match="spacing"):
        profile_ar1(design, response, "other")


@pytest.mark.parametrize("gaps,rho", [([1, 0, 1], 0.5), ([1, 1.5, 1], 0.5), ([1, 1, 1], 1.0)])
def test_invalid_transition_assumptions_are_rejected(gaps, rho):
    with pytest.raises(ValueError):
        conditional_fit_at_rho(np.column_stack([np.ones(4), [1, 3, 2, 4]]),
                               np.array([3, 1, 5, 2]), gaps, rho)
