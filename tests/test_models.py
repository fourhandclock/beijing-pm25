"""Synthetic numerical and leakage checks; never used as empirical results."""

from dataclasses import replace
from datetime import timedelta
import copy

import numpy as np
import pandas as pd
import pytest
from scipy import stats
import statsmodels.api as sm
from statsmodels.stats.sandwich_covariance import cov_hac

from beijing_pm25.config import SEASONS
from beijing_pm25.model_config import Stage2Config
from beijing_pm25.model_diagnostics import calendar_bg, calendar_hac, joint_wald, model_tables, seasonal_wind_slopes
from beijing_pm25.models import (choose_validation_model, design_matrix, develop_models,
                                evaluate_frozen, fit_candidates, frozen_specification,
                                prediction_rows, score_predictions)


def synthetic_daily():
    random = np.random.default_rng(8042)
    index = pd.date_range("2013-03-01", periods=565, freq="D", name="date")
    season = index.month.map(SEASONS)
    temperature = 15 + 13 * np.sin(np.arange(565) * 2 * np.pi / 365) + random.normal(0, 3, 565)
    wind = random.uniform(0.5, 6, 565)
    pressure = 1010 + random.normal(0, 6, 565)
    rainfall = random.exponential(2, 565) * (random.random(565) > 0.7)
    errors = random.normal(0, 8, 565)
    for i in range(1, len(errors)):
        errors[i] += 0.35 * errors[i - 1]
    response = (100 + 0.8 * temperature - 7 * wind + 0.3 * (pressure - 1010) - rainfall + errors
                + 12 * (season == "spring") - 15 * (season == "summer")
                + 3 * wind * (season == "autumn"))
    result = pd.DataFrame({
        "station": "Synthetic", "season": season, "temperature": temperature,
        "wind_speed": wind, "rainfall": rainfall, "pressure": pressure,
        "pm25": response, "analysis_eligible": True,
        "split": ["train"] * 365 + ["validation"] * 100 + ["test"] * 100,
    }, index=index)
    result.loc[index[[50, 150, 250]], "analysis_eligible"] = False
    result.loc[index[[50, 150, 250]], "pm25"] = np.nan
    return result


def partitions():
    daily = synthetic_daily()
    eligible = daily.loc[daily["analysis_eligible"]]
    return tuple(eligible.loc[eligible["split"].eq(split)] for split in ("train", "validation", "test"))


def test_ols_and_nested_f_against_independent_least_squares():
    training, _, _ = partitions()
    fitted, centers = fit_candidates(training)
    oracle_sse = {}
    for name, result in fitted.items():
        design = design_matrix(training, centers, name).to_numpy()
        coefficient, _, _, _ = np.linalg.lstsq(design, training["pm25"].to_numpy(), rcond=None)
        np.testing.assert_allclose(result.params, coefficient, rtol=1e-10, atol=1e-10)
        error = training["pm25"].to_numpy() - design @ coefficient
        oracle_sse[name] = float(error @ error)
    for smaller, larger in (("M1", "M2"), ("M2", "M3")):
        q = len(fitted[larger].params) - len(fitted[smaller].params)
        df = len(training) - len(fitted[larger].params)
        expected_f = ((oracle_sse[smaller] - oracle_sse[larger]) / q) / (oracle_sse[larger] / df)
        actual_f, actual_p, actual_q = fitted[larger].compare_f_test(fitted[smaller])
        assert actual_f == pytest.approx(expected_f)
        assert actual_p == pytest.approx(stats.f.sf(expected_f, q, df))
        assert actual_q == q == 3


def test_centering_preserves_nested_fitted_values():
    training, _, _ = partitions()
    fitted, _ = fit_candidates(training)
    zero_centers = {name: 0.0 for name in ("temperature", "wind_speed", "rainfall", "pressure")}
    for name, result in fitted.items():
        uncentered = design_matrix(training, zero_centers, name).to_numpy()
        beta = np.linalg.lstsq(uncentered, training["pm25"].to_numpy(), rcond=None)[0]
        np.testing.assert_allclose(uncentered @ beta, result.fittedvalues, rtol=1e-10, atol=1e-9)
    assert [len(result.params) for result in fitted.values()] == [5, 8, 11]


@pytest.mark.parametrize("lag", [0, 3, 7])
def test_calendar_hac_matches_statsmodels_on_uninterrupted_calendar(lag):
    daily = synthetic_daily().iloc[:365].drop(columns="analysis_eligible").copy()
    # Fill the three intentionally missing synthetic responses for this specific
    # uninterrupted-calendar identity check; never do this in the real pipeline.
    daily["pm25"] = daily["pm25"].interpolate()
    fitted, centers = fit_candidates(daily)
    result = fitted["M3"]
    actual = calendar_hac(design_matrix(daily, centers, "M3"), result.resid, lag)
    expected = cov_hac(result, nlags=lag, use_correction=True)
    np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-10)


def test_gapped_hac_against_hand_calculated_intercept_example():
    index = pd.DatetimeIndex(["2013-01-01", "2013-01-02", "2013-01-04", "2013-01-05"])
    design = pd.DataFrame({"Intercept": 1.0}, index=index)
    residuals = pd.Series([1.0, 2.0, -4.0, 1.0], index=index)
    covariance = calendar_hac(design, residuals, 1)
    # Sum of squares 22; only day-distance-one products 2 and -4 enter.
    # Bartlett lag-one weight = 1/2, bread = 1/4, correction = 4/3.
    assert covariance[0, 0] == pytest.approx((22 + 2 * 0.5 * (2 - 4)) / 16 * 4 / 3)
    assert covariance[0, 0] != pytest.approx(1.0)  # The compressed-row calculation.
    with pytest.raises(ValueError, match="align exactly"):
        calendar_hac(design, residuals.iloc[::-1], 1)


def test_joint_wald_matches_manual_restriction_calculation():
    covariance = np.array([[4, 1, 0], [1, 3, 1], [0, 1, 2]], dtype=float)
    statistic, p_value = joint_wald(np.array([0, 2, 3]), covariance, [1, 2])
    expected = np.array([2, 3]) @ np.linalg.solve(np.array([[3, 1], [1, 2]]), np.array([2, 3]))
    assert statistic == pytest.approx(expected)
    assert p_value == pytest.approx(stats.chi2.sf(expected, 2))


def test_model_tables_use_same_sample_and_primary_holm_family():
    training, _, _ = partitions()
    fitted, _ = fit_candidates(training)
    config = Stage2Config()
    summaries, coefficients, classical, robust, covariances = model_tables(fitted, config)
    assert summaries["n"].nunique() == 1
    assert list(classical["df_added"]) == [3, 3]
    assert robust["primary_bandwidth"].sum() == 2
    assert robust.loc[~robust["primary_bandwidth"], "p_holm_primary"].isna().all()
    assert (robust.loc[robust["primary_bandwidth"], "p_holm_primary"] >=
            robust.loc[robust["primary_bandwidth"], "p_value_hac"]).all()
    for covariance in covariances["M3"].values():
        assert np.linalg.eigvalsh(covariance).min() > -1e-10
    slopes = seasonal_wind_slopes(fitted["M3"], covariances["M3"][7], 0.05, 7)
    summer = slopes.loc[slopes["season"].eq("summer")].iloc[0]
    assert summer["pm25_change_per_1_mps_wind"] == pytest.approx(
        fitted["M3"].params["wind_speed_c"] + fitted["M3"].params["wind_x_summer"]
    )
    assert (coefficients["hac_ci_lower"] <= coefficients["estimate"]).all()


def test_serial_diagnostic_uses_actual_calendar_lags():
    training, _, _ = partitions()
    fitted, _ = fit_candidates(training)
    diagnostic = calendar_bg(fitted["M1"], 7)
    dates = set(training.index)
    expected_rows = sum(all(day - timedelta(days=lag) in dates for lag in range(1, 8)) for day in dates)
    assert diagnostic["serial_auxiliary_n"] == expected_rows
    assert expected_rows < len(training) - 7  # Missing days interrupt lag availability.


def test_validation_simplicity_rule_and_partition_guard():
    scores = pd.DataFrame({"model": ["M1", "M2", "M3"], "split": "validation",
                           "subgroup": "all", "mae": [10.09, 10.05, 10.0], "n": 100})
    assert choose_validation_model(scores, {"M1": 5, "M2": 8, "M3": 11})[0] == "M1"
    scores.loc[0, "mae"] = 10.2
    assert choose_validation_model(scores, {"M1": 5, "M2": 8, "M3": 11})[0] == "M2"
    with pytest.raises(ValueError, match="validation scores only"):
        choose_validation_model(scores.assign(split="test"), {"M1": 5, "M2": 8, "M3": 11})


def test_frozen_evaluation_does_not_learn_from_test_outcomes_or_weather():
    training, validation, test = partitions()
    config = Stage2Config()
    development = develop_models(training, validation, config)
    frozen = frozen_specification(development, config)
    before = copy.deepcopy(frozen)
    changed_test = test.copy()
    changed_test["pm25"] += 10000
    changed_test["temperature"] += 500
    first = evaluate_frozen(test, frozen)
    second = evaluate_frozen(changed_test, frozen)
    assert frozen == before
    assert frozen["training_centers"]["temperature"] == training["temperature"].mean()
    assert frozen["high_pollution_training_cutoff"] == training["pm25"].quantile(0.95)
    assert len(first) == len(second) == 2 * len(test)
    assert set(first["model"]) == {development.selected_model, "training_mean"}
    with pytest.raises(ValueError, match="train-only"):
        fit_candidates(pd.concat([training, test]))


def test_error_sign_negative_predictions_and_empty_subgroups():
    frame = pd.DataFrame({"pm25": [10.0, 20.0], "season": ["winter", "winter"], "split": "test"},
                         index=pd.date_range("2016-01-01", periods=2))
    predictions = prediction_rows(frame, "M1", [-2, 12], threshold=100)
    assert list(predictions["signed_error"]) == [-12, -8]
    metrics = score_predictions(predictions)
    overall = metrics.loc[metrics["subgroup"].eq("all")].iloc[0]
    assert overall["mae"] == 10
    assert overall["rmse"] == pytest.approx(np.sqrt(104))
    assert overall["mean_signed_error"] == -10
    assert overall["negative_predictions"] == 1
    empty = metrics.loc[metrics["subgroup"].eq("high")].iloc[0]
    assert empty["n"] == 0 and pd.isna(empty["mae"])


@pytest.mark.parametrize("updates", [
    {"response_scale": "log1p"}, {"selection_metric": "rmse"},
    {"hac_lag_days": (14, 30)}, {"primary_hac_lag_days": True},
    {"simplicity_tolerance_fraction": -0.01}, {"extreme_training_quantile": 1},
])
def test_stage2_config_rejects_changes_outside_declared_scope(updates):
    with pytest.raises(ValueError):
        replace(Stage2Config(), **updates)
