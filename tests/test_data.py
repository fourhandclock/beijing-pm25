from dataclasses import replace
from datetime import date, timedelta
import statistics

import numpy as np
import pandas as pd
import pytest

from beijing_pm25.data import aggregate_daily, rank_stations, read_station, split_labels, station_audit
from beijing_pm25.config import Stage1Config
from beijing_pm25.describe import calendar_acf, response_summary
from conftest import csv_bytes, hourly_rows


def load(rows, config, station="Alpha"):
    return read_station(station, f"PRSA_Data_{station}_20130301-20170228.csv", csv_bytes(rows), config)


def test_aggregation_matches_independent_arithmetic(small_config):
    rows = hourly_rows()
    # Known hourly rainfall amounts: a daily total, not an hourly mean.
    for row in rows[:24]:
        row["RAIN"] = 0.5
    daily = aggregate_daily(load(rows, small_config), small_config)
    assert daily.iloc[0]["pm25"] == statistics.mean(row["PM2.5"] for row in rows[:24])
    assert daily.iloc[0]["temperature"] == statistics.mean(row["TEMP"] for row in rows[:24])
    assert daily.iloc[0]["rainfall"] == 12
    assert daily["analysis_eligible"].all()


@pytest.mark.parametrize("valid_hours,qualified", [(17, False), (18, True), (24, True)])
def test_pm25_completeness_boundary(small_config, valid_hours, qualified):
    rows = hourly_rows()
    for row in rows[:24 - valid_hours]:
        row["PM2.5"] = "NA"
    daily = aggregate_daily(load(rows, small_config), small_config)
    first = daily.iloc[0]
    assert first["n_pm25"] == valid_hours
    assert bool(first["pm25_complete"]) is qualified
    assert bool(first["analysis_eligible"]) is qualified
    if qualified:
        expected = statistics.mean(float(row["PM2.5"]) for row in rows[:24] if row["PM2.5"] != "NA")
        assert first["pm25"] == expected
    else:
        assert pd.isna(first["pm25"])


@pytest.mark.parametrize("missing_hours", [1, 24])
def test_incomplete_rainfall_is_not_zero_or_partial_total(small_config, missing_hours):
    rows = hourly_rows()
    for row in rows[:24]:
        row["RAIN"] = 1
    for row in rows[:missing_hours]:
        row["RAIN"] = "NA"
    daily = aggregate_daily(load(rows, small_config), small_config)
    assert daily.iloc[0]["n_rainfall"] == 24 - missing_hours
    assert pd.isna(daily.iloc[0]["rainfall"])
    assert not daily.iloc[0]["analysis_eligible"]
    assert daily.iloc[1]["rainfall"] == 0


def test_missing_whole_day_preserves_alignment_and_gap(small_config):
    rows = [row for row in hourly_rows() if row["day"] != 2]
    data = load(rows, small_config)
    daily = aggregate_daily(data, small_config)
    assert len(daily) == 8
    assert list(daily.index.date) == [date(2013, 3, 1) + timedelta(days=i) for i in range(8)]
    assert daily.loc["2013-03-02", "hours_observed"] == 0
    assert pd.isna(daily.loc["2013-03-02", "pm25"])
    assert daily.loc["2013-03-03", "pm25"] == 31.5
    assert data.audit["missing_hour_rows"] == 24
    assert data.gaps == [{"station": "Alpha", "start_hour": "2013-03-02T00:00:00",
                          "end_hour_inclusive": "2013-03-02T23:00:00", "missing_hours": 24}]
    missing = next(row for row in data.missingness if row["scope"] == "all" and row["variable"] == "PM2.5")
    assert missing["absent_hour_rows"] == 24
    assert missing["source_missing_values"] == 0
    assert missing["unusable_hours"] == 24


def test_disjoint_hour_subsets_need_minimum_overlap(small_config):
    rows = hourly_rows()
    for row in rows[:6]:
        row["PM2.5"] = "NA"
    for row in rows[6:12]:
        row["TEMP"] = "NA"
    daily = aggregate_daily(load(rows, small_config), small_config)
    first = daily.iloc[0]
    assert first["pm25_complete"] and first["weather_complete"]
    assert first["n_joint_core_hours"] == 12
    assert not first["analysis_eligible"]
    assert first["exclusion_reason"] == "insufficient_joint_hours"


def test_mixed_stations_rejected(small_config):
    rows = hourly_rows()
    rows[2]["station"] = "Beta"
    with pytest.raises(ValueError, match="mixes stations"):
        load(rows, small_config)


def test_duplicate_hours_rejected(small_config):
    rows = hourly_rows()
    rows.append(rows[0].copy())
    with pytest.raises(ValueError, match="duplicate station/timestamp"):
        load(rows, small_config)


@pytest.mark.parametrize("column,value", [("hour", 24), ("day", 32), ("hour", 1.5), ("year", "NA"), ("PM2.5", "broken")])
def test_malformed_calendar_and_numeric_values_rejected(small_config, column, value):
    rows = hourly_rows()
    rows[0][column] = value
    with pytest.raises(ValueError):
        load(rows, small_config)


def test_quality_masks_count_errors_and_preserve_valid_values(small_config):
    rows = hourly_rows()
    rows[0]["PM2.5"] = -1
    rows[1]["PM2.5"] = 0
    rows[2]["PM2.5"] = 2000  # A large value alone is not evidence of measurement error.
    rows[3]["PM2.5"] = "inf"
    rows[4]["PRES"] = 0
    rows[5]["wd"] = "UNKNOWN"
    data = load(rows, small_config)
    assert pd.isna(data.hourly.iloc[0]["PM2.5"])
    assert data.hourly.iloc[1]["PM2.5"] == 0
    assert data.hourly.iloc[2]["PM2.5"] == 2000
    assert pd.isna(data.hourly.iloc[3]["PM2.5"])
    assert pd.isna(data.hourly.iloc[4]["PRES"])
    assert pd.isna(data.hourly.iloc[5]["wd"])
    assert data.hourly.iloc[0]["TEMP"] == -3
    assert data.audit["invalid_values_masked"] == 4
    assert data.audit["source_missing_values"] == 0


def test_out_of_order_rows_are_counted_and_calendar_sorted(small_config):
    rows = hourly_rows()
    data = load(list(reversed(rows)), small_config)
    assert data.audit["out_of_order_steps_sorted"] == len(rows) - 1
    assert data.hourly.index.is_monotonic_increasing
    assert aggregate_daily(data, small_config).iloc[0]["pm25"] == 21.5


def test_split_boundaries_and_season_are_calendar_based(small_config):
    daily = aggregate_daily(load(hourly_rows(), small_config), small_config)
    assert list(daily["split"]) == ["train"] * 4 + ["validation"] * 2 + ["test"] * 2
    assert daily["season"].eq("spring").all()
    with pytest.raises(ValueError, match="outside"):
        split_labels(pd.DatetimeIndex(["2013-03-09"]), small_config)


def test_leap_day_kept_and_not_moved_across_split():
    config = Stage1Config()
    rows = hourly_rows(days=3)
    stamps = pd.date_range("2016-02-28", periods=72, freq="h")
    for row, stamp in zip(rows, stamps):
        row.update(year=stamp.year, month=stamp.month, day=stamp.day, hour=stamp.hour)
    daily = aggregate_daily(load(rows, config), config)
    assert daily.loc["2016-02-29", "hours_observed"] == 24
    assert daily.loc["2016-02-29", "split"] == "validation"
    assert daily.loc["2016-02-29", "season"] == "winter"
    assert daily.loc["2016-03-01", "split"] == "test"
    assert daily.loc["2016-03-01", "season"] == "spring"


def test_station_selection_ignores_future_values_and_coverage(small_config):
    alpha = hourly_rows("Alpha")
    beta = hourly_rows("Beta", offset=500)
    for row in alpha[:24]:
        row["PM2.5"] = "NA"
    # Beta has better training coverage, despite much worse future coverage.
    for row in beta[4 * 24:]:
        row["PM2.5"] = "NA"
    audits = []
    for name, rows in (("Alpha", alpha), ("Beta", beta)):
        data = load(rows, small_config, name)
        audits.append(station_audit(data, aggregate_daily(data, small_config)))
    assert rank_stations(audits).iloc[0]["station"] == "Beta"
    changed = [{**row, "analysis_eligible_days": 10000 if row["station"] == "Alpha" else 0} for row in audits]
    assert rank_stations(changed).iloc[0]["station"] == "Beta"


def test_selection_ties_are_alphabetical(small_config):
    audits = []
    for name in ("Beta", "Alpha"):
        data = load(hourly_rows(name), small_config, name)
        audits.append(station_audit(data, aggregate_daily(data, small_config)))
    assert list(rank_stations(audits)["station"]) == ["Alpha", "Beta"]


def test_acf_preserves_gaps_against_independent_correlation():
    values = pd.Series([1, np.nan, 4, 2, 7, np.nan, 3, 6],
                       index=pd.date_range("2013-03-01", periods=8, freq="D"))
    acf = calendar_acf(values, max_lag=1).iloc[0]
    assert acf["paired_days"] == 3
    assert acf["correlation"] == pytest.approx(statistics.correlation([2, 7, 6], [4, 2, 3]))
    with pytest.raises(ValueError, match="every calendar day"):
        calendar_acf(values.dropna(), max_lag=1)


def test_response_descriptions_exclude_held_out_values(small_config):
    data = load(hourly_rows(), small_config)
    daily = aggregate_daily(data, small_config)
    train = daily.loc[daily["split"].eq("train")]
    summary = response_summary(data.hourly.loc[data.hourly["split"].eq("train"), "PM2.5"], train)
    row = summary.loc[summary["subset"].eq("daily_analysis_eligible_training") & summary["scale"].eq("original")].iloc[0]
    assert row["n"] == 4
    assert row["mean"] == statistics.mean([21.5, 26.5, 31.5, 36.5])


@pytest.mark.parametrize("updates", [
    {"min_valid_hours": 0}, {"min_valid_hours": 25}, {"min_valid_hours": True},
    {"max_acf_lag": 0}, {"station": "../bad"},
    {"train_end_exclusive": "2013-03-01"},
])
def test_invalid_configuration_rejected(small_config, updates):
    with pytest.raises(ValueError):
        replace(small_config, **updates)
