"""Validate one station at a time and aggregate on a complete daily calendar."""

from dataclasses import dataclass
from datetime import timedelta
import hashlib
import io

import numpy as np
import pandas as pd

from .config import CORE_VARIABLES, MEAN_VARIABLES, NUMERIC_VARIABLES, SEASONS, Stage1Config


WIND_DIRECTIONS = set("N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW".split())
NONNEGATIVE = {"PM2.5", "PM10", "SO2", "NO2", "CO", "O3", "RAIN", "WSPM"}
CALENDAR_COLUMNS = ("year", "month", "day", "hour")


@dataclass
class StationData:
    station: str
    hourly: pd.DataFrame
    audit: dict
    missingness: list[dict]
    gaps: list[dict]


def split_labels(index: pd.DatetimeIndex, config: Stage1Config):
    if (index < pd.Timestamp(config.calendar_start)).any() or (
        index >= pd.Timestamp(config.calendar_end_exclusive)
    ).any():
        raise ValueError("Timestamp outside the declared analysis calendar.")
    return pd.Series(np.select(
        [index < pd.Timestamp(config.train_end_exclusive),
         index < pd.Timestamp(config.validation_end_exclusive)],
        ["train", "validation"], default="test",
    ), index=index, name="split")


def _gap_ranges(index: pd.DatetimeIndex, station: str):
    if index.empty:
        return []
    ranges = []
    start = previous = index[0]
    count = 1
    for timestamp in index[1:]:
        if timestamp - previous != timedelta(hours=1):
            ranges.append({"station": station, "start_hour": start.isoformat(),
                           "end_hour_inclusive": previous.isoformat(), "missing_hours": count})
            start, count = timestamp, 0
        previous = timestamp
        count += 1
    ranges.append({"station": station, "start_hour": start.isoformat(),
                   "end_hour_inclusive": previous.isoformat(), "missing_hours": count})
    return ranges


def read_station(station: str, member: str, content: bytes, config: Stage1Config):
    frame = pd.read_csv(io.BytesIO(content), na_values=["NA"], keep_default_na=True)
    required = {*CALENDAR_COLUMNS, *NUMERIC_VARIABLES, "station", "wd"}
    absent_columns = sorted(required - set(frame.columns))
    if absent_columns:
        raise ValueError(f"{member}: missing required columns: {absent_columns}")
    if frame.empty:
        raise ValueError(f"{member}: station file is empty.")
    if not frame["station"].eq(station).all():
        raise ValueError(f"{member}: station column disagrees with filename or mixes stations.")

    for column in CALENDAR_COLUMNS:
        values = pd.to_numeric(frame[column], errors="raise")
        if not np.isfinite(values).all() or not values.mod(1).eq(0).all():
            raise ValueError(f"{member}: {column} must contain finite integers.")
        frame[column] = values.astype("int64")
    if not frame["hour"].between(0, 23).all():
        raise ValueError(f"{member}: hour must be between 0 and 23.")
    timestamps = pd.DatetimeIndex(pd.to_datetime(frame[list(CALENDAR_COLUMNS)], errors="raise"))
    if timestamps.has_duplicates:
        raise ValueError(f"{member}: duplicate station/timestamp rows; no automatic averaging or deduplication.")
    split_labels(timestamps, config)  # Also checks calendar bounds.
    unsorted_steps = sum(current < previous for previous, current in zip(timestamps, timestamps[1:]))
    frame.index = timestamps

    raw_missing = pd.DataFrame(index=timestamps)
    invalid = pd.DataFrame(index=timestamps)
    for column in NUMERIC_VARIABLES:
        series = pd.to_numeric(frame[column], errors="raise").astype(float)
        raw_missing[column] = series.isna()
        bad = series.notna() & ~np.isfinite(series)
        if column in NONNEGATIVE:
            bad |= series.lt(0)
        if column == "PRES":
            bad |= series.le(0)
        invalid[column] = bad
        frame[column] = series.mask(bad)
    raw_missing["wd"] = frame["wd"].isna()
    invalid["wd"] = frame["wd"].notna() & ~frame["wd"].isin(WIND_DIRECTIONS)
    frame["wd"] = frame["wd"].mask(invalid["wd"])
    frame["observed_hour"] = True

    grid = pd.date_range(config.calendar_start, config.calendar_end_exclusive,
                         inclusive="left", freq="h", name="timestamp")
    hourly = frame.reindex(grid)
    hourly["observed_hour"] = hourly["observed_hour"].eq(True)
    # The station label identifies a calendar slot, not an invented observation.
    hourly["station"] = station
    hourly["split"] = split_labels(grid, config)
    raw_missing = raw_missing.reindex(grid, fill_value=False)
    invalid = invalid.reindex(grid, fill_value=False)
    gaps = _gap_ranges(grid[~hourly["observed_hour"]], station)

    missingness = []
    for scope in ("all", "train", "validation", "test"):
        scope_mask = pd.Series(True, index=grid) if scope == "all" else hourly["split"].eq(scope)
        expected_hours = int(scope_mask.sum())
        observed_hours = int(hourly.loc[scope_mask, "observed_hour"].sum())
        for column in (*NUMERIC_VARIABLES, "wd"):
            valid_hours = int(hourly.loc[scope_mask, column].notna().sum())
            missingness.append({
                "station": station, "scope": scope, "variable": column,
                "expected_hours": expected_hours, "observed_rows": observed_hours,
                "absent_hour_rows": expected_hours - observed_hours,
                "source_missing_values": int(raw_missing.loc[scope_mask, column].sum()),
                "invalid_values_masked": int(invalid.loc[scope_mask, column].sum()),
                "valid_hours": valid_hours,
                "unusable_hours": expected_hours - valid_hours,
                "unusable_fraction": (expected_hours - valid_hours) / expected_hours,
            })

    audit = {
        "station": station, "archive_member": member,
        "member_sha256": hashlib.sha256(content).hexdigest(),
        "source_hourly_rows": len(frame), "expected_hourly_rows": len(grid),
        "missing_hour_rows": int((~hourly["observed_hour"]).sum()),
        "duplicate_timestamps": 0, "out_of_order_steps_sorted": unsorted_steps,
        "longest_absent_hour_run": max((gap["missing_hours"] for gap in gaps), default=0),
        "first_observed_hour": timestamps.min().isoformat(),
        "last_observed_hour": timestamps.max().isoformat(),
        "source_missing_values": int(raw_missing.to_numpy().sum()),
        "invalid_values_masked": int(invalid.to_numpy().sum()),
        "training_pm25_valid_hours": int(hourly.loc[hourly["split"].eq("train"), "PM2.5"].notna().sum()),
    }
    return StationData(station, hourly, audit, missingness, gaps)


def aggregate_daily(data: StationData, config: Stage1Config):
    hourly = data.hourly
    grid = pd.date_range(config.calendar_start, config.calendar_end_exclusive,
                         inclusive="left", freq="D", name="date")
    daily = pd.DataFrame(index=grid)
    daily["station"] = data.station
    daily["split"] = split_labels(grid, config)
    daily["season"] = grid.month.map(SEASONS)
    daily["year"] = grid.year
    daily["month"] = grid.month
    daily["hours_observed"] = hourly["observed_hour"].resample("D").sum().astype(int)

    for column, name in MEAN_VARIABLES.items():
        groups = hourly[column].resample("D")
        counts = groups.count()
        daily[f"n_{name}"] = counts
        daily[name] = groups.mean().where(counts >= config.min_valid_hours)
    rain_groups = hourly["RAIN"].resample("D")
    daily["n_rainfall"] = rain_groups.count()
    daily["rainfall"] = rain_groups.sum(min_count=24)
    daily["n_joint_core_hours"] = hourly[list(CORE_VARIABLES)].notna().all(axis=1).resample("D").sum().astype(int)
    daily["pm25_complete"] = daily["pm25"].notna()
    daily["weather_complete"] = daily[["temperature", "pressure", "wind_speed", "rainfall"]].notna().all(axis=1)
    daily["joint_complete"] = daily["n_joint_core_hours"].ge(config.min_valid_hours)
    daily["analysis_eligible"] = daily[["pm25_complete", "weather_complete", "joint_complete"]].all(axis=1)

    reasons = pd.Series("", index=grid)
    for name in MEAN_VARIABLES.values():
        bad = daily[f"n_{name}"].lt(config.min_valid_hours)
        reasons.loc[bad] += f"insufficient_{name}_hours;"
    reasons.loc[daily["n_rainfall"].lt(24)] += "incomplete_rainfall_total;"
    reasons.loc[~daily["joint_complete"]] += "insufficient_joint_hours;"
    daily["exclusion_reason"] = reasons.str.rstrip(";")
    return daily


def coverage_rows(daily: pd.DataFrame, station: str):
    rows = []
    for scope in ("all", "train", "validation", "test"):
        part = daily if scope == "all" else daily.loc[daily["split"].eq(scope)]
        rows.append({
            "station": station, "scope": scope, "calendar_days": len(part),
            "observed_hourly_rows": int(part["hours_observed"].sum()),
            "pm25_qualified_days": int(part["pm25_complete"].sum()),
            "analysis_eligible_days": int(part["analysis_eligible"].sum()),
            "excluded_days": int((~part["analysis_eligible"]).sum()),
            "days_with_no_source_rows": int(part["hours_observed"].eq(0).sum()),
            "days_insufficient_pm25": int((~part["pm25_complete"]).sum()),
            "days_insufficient_weather": int((~part["weather_complete"]).sum()),
            "days_incomplete_rainfall": int(part["n_rainfall"].lt(24).sum()),
            "days_insufficient_joint_hours": int((~part["joint_complete"]).sum()),
        })
    return rows


def station_audit(data: StationData, daily: pd.DataFrame):
    return {
        **data.audit, "calendar_days": len(daily),
        "pm25_qualified_days": int(daily["pm25_complete"].sum()),
        "analysis_eligible_days": int(daily["analysis_eligible"].sum()),
        "training_analysis_days": int((daily["split"].eq("train") & daily["analysis_eligible"]).sum()),
    }


def rank_stations(audits: list[dict]):
    # Only completeness in the training interval enters selection. Neither
    # pollution levels nor validation/test coverage can change the ordering.
    ranked = pd.DataFrame(audits).sort_values(
        ["training_analysis_days", "training_pm25_valid_hours", "station"],
        ascending=[False, False, True], kind="stable",
    ).reset_index(drop=True)
    ranked.insert(0, "training_completeness_rank", np.arange(1, len(ranked) + 1))
    return ranked
