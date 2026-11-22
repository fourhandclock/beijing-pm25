"""Correctness checks for Stage 3 helpers on small synthetic inputs (never empirical results)."""

import numpy as np
import pandas as pd
import pytest

from beijing_pm25.data import read_station
from beijing_pm25.extension_config import Stage3Config
from beijing_pm25.extensions import (EXTENSION_MODELS, FittedExtension, build_station_daily, choose_cutoff,
                                     cluster_stations, common_sample, confusion, extra_daily,
                                     rank_auc, training_centres, wind_components)
from conftest import csv_bytes, hourly_rows


def test_wind_components_follow_meteorological_from_convention():
    direction = pd.Series(["N", "S", "W", "E", "XYZ", None])
    speed = pd.Series([2.0, 2.0, 3.0, 3.0, 1.0, 1.0])
    southerly, westerly = wind_components(direction, speed)
    assert southerly.iloc[0] == pytest.approx(-2.0)   # from the north: air moves south
    assert southerly.iloc[1] == pytest.approx(2.0)    # from the south
    assert westerly.iloc[2] == pytest.approx(3.0)     # from the west
    assert westerly.iloc[3] == pytest.approx(-3.0)
    assert southerly.iloc[4:].isna().all() and westerly.iloc[4:].isna().all()


def _hourly(hours=48):
    index = pd.date_range("2013-03-01", periods=hours, freq="h", name="timestamp")
    frame = pd.DataFrame({column: 1.0 for column in ("PM10", "SO2", "NO2", "CO", "O3")}, index=index)
    frame["DEWP"] = 5.0
    frame["WSPM"] = 2.0
    frame["wd"] = "S"
    return frame


def test_extra_daily_applies_completeness_rule_to_each_variable():
    hourly = _hourly()
    hourly.iloc[:7, hourly.columns.get_loc("DEWP")] = np.nan      # day 1: 17 valid dew-point hours
    hourly.iloc[24:31, hourly.columns.get_loc("wd")] = None       # day 2: 17 valid wind vectors
    daily = extra_daily(hourly, 18)
    assert np.isnan(daily["dew_point"].iloc[0]) and daily["dew_point"].iloc[1] == pytest.approx(5.0)
    assert daily["southerly"].iloc[0] == pytest.approx(2.0) and np.isnan(daily["southerly"].iloc[1])
    assert daily["n_wind_vector"].tolist() == [24, 17]


def test_previous_day_pm25_uses_calendar_day_not_previous_row(small_config):
    rows = hourly_rows(days=8)
    for row in rows:
        if row["day"] == 3:
            row["PM2.5"] = "NA"   # day 3 has no PM2.5 at all
    data = read_station("Alpha", "Alpha.csv", csv_bytes(rows), small_config)
    daily = build_station_daily(data, small_config, small_config.min_valid_hours)
    assert np.isnan(daily.loc["2013-03-03", "pm25"])
    assert np.isnan(daily.loc["2013-03-04", "pm25_lag1"])          # not day 2's value
    assert daily.loc["2013-03-05", "pm25_lag1"] == daily.loc["2013-03-04", "pm25"]
    sample = common_sample(daily)
    assert pd.Timestamp("2013-03-04") not in sample.index


def _synthetic_sample(n=120, seed=0):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2013-03-01", periods=n, freq="D", name="date")
    frame = pd.DataFrame({
        "temperature": rng.normal(10, 8, n), "wind_speed": rng.gamma(2, 1, n),
        "rainfall": rng.exponential(0.5, n), "pressure": rng.normal(1010, 8, n),
        "dew_point": rng.normal(0, 8, n), "southerly": rng.normal(0, 1, n), "westerly": rng.normal(0, 1, n),
        "season": np.resize(["winter", "spring", "summer", "autumn"], n), "split": "train",
        "analysis_eligible": True,
    }, index=index)
    frame["pm25"] = np.exp(4 - 0.3 * frame["wind_speed"] + rng.normal(0, 0.4, n))
    frame["pm25_lag1"] = frame["pm25"].shift(1).fillna(frame["pm25"].mean())
    return frame


@pytest.mark.parametrize("name", list(EXTENSION_MODELS))
def test_extension_models_centre_on_training_and_back_transform(name):
    training = _synthetic_sample()
    centres = training_centres(training)
    model = FittedExtension(name, training, centres)
    predictions = model.predict(training)
    assert predictions.shape == (len(training),) and np.isfinite(predictions).all()
    if EXTENSION_MODELS[name]["log"]:
        assert model.smearing == pytest.approx(np.mean(np.exp(model.result.resid)))
        assert (predictions > -1).all()
    other = _synthetic_sample(seed=1)
    assert np.allclose(FittedExtension(name, training, centres).predict(other), model.predict(other))


def test_rank_auc_and_confusion_counts():
    probabilities = np.array([0.1, 0.4, 0.35, 0.8])
    outcomes = np.array([False, False, True, True])
    assert rank_auc(probabilities, outcomes) == pytest.approx(0.75)
    counts = confusion(probabilities, outcomes, 0.35)
    assert (counts["true_positive"], counts["false_positive"], counts["false_negative"]) == (2, 1, 0)


def test_cutoff_maximises_f1_on_the_given_sample_only():
    probabilities = np.array([0.05, 0.1, 0.2, 0.3, 0.6])
    outcomes = np.array([False, False, True, True, False])
    assert choose_cutoff(probabilities, outcomes) == pytest.approx(0.2)
    with pytest.raises(ValueError, match="no smog days"):
        choose_cutoff(probabilities, np.zeros(5, bool))


def test_cluster_numbering_and_largest_gap_rule():
    profiles = pd.DataFrame({
        "pm25": [50, 52, 51, 90, 92, 91], "pm10": [70, 71, 72, 120, 121, 119],
        "so2": [10, 11, 10, 20, 21, 20], "no2": [30, 31, 29, 60, 61, 59],
        "co": [900, 910, 905, 1400, 1410, 1395], "o3": [65, 64, 66, 50, 49, 51],
    }, index=pd.Index(list("abcdef"), name="station"))
    result = cluster_stations(profiles, ("PM2.5", "PM10", "SO2", "NO2", "CO", "O3"), (2, 4))
    clusters = result["assignments"].set_index("station")["cluster"]
    assert result["k"] == 2
    assert set(clusters[list("abc")]) == {1} and set(clusters[list("def")]) == {2}


def test_stage3_config_rejects_bad_settings():
    with pytest.raises(ValueError):
        Stage3Config(cluster_variables=("TEMP_X",))
    with pytest.raises(ValueError):
        Stage3Config(cluster_k_range=(1, 3))
    assert Stage3Config().as_dict()["cluster_k_range"] == [2, 5]
