"""Independent real-data oracle using csv/datetime/statistics, without pandas.

Checks all station selection counts, then every selected daily mean, rainfall
total, hourly count, split and eligibility flag against original archive bytes.
This is verification, not a second set of empirical claims or a model fit.
"""

import csv
from datetime import date, timedelta
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VARIABLES = {"PM2.5": "pm25", "TEMP": "temperature", "PRES": "pressure", "WSPM": "wind_speed", "RAIN": "rainfall"}
PATTERN = re.compile(r"PRSA_Data_([A-Za-z0-9]+)_\d{8}-\d{8}\.csv$")


def clean(text, column):
    if text.strip() in {"", "NA", "NaN", "nan"}:
        return None
    value = float(text)
    if not math.isfinite(value):
        return None
    if column in {"PM2.5", "RAIN", "WSPM"} and value < 0:
        return None
    if column == "PRES" and value <= 0:
        return None
    return value


def source_members(archive):
    for member in archive.namelist():
        if member.endswith("/"):
            continue
        if member.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(archive.read(member))) as nested:
                yield from source_members(nested)
        else:
            match = PATTERN.fullmatch(Path(member).name)
            if match:
                yield match.group(1), archive.read(member)


def verify():
    config = json.loads((ROOT / "config" / "stage1.json").read_text())
    manifest = json.loads((ROOT / "results" / "stage1_run.json").read_text())
    if manifest.get("status") != "complete":
        raise ValueError("A complete default Stage 1 run is required.")
    if config != manifest["configuration"]:
        raise ValueError("This oracle checks the default config; configuration does not match the run.")
    original = ROOT / "data" / "raw" / "uci_beijing_multi_site.zip"
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    assert digest == manifest["raw_provenance"]["sha256"], "Raw checksum mismatch"
    minimum = config["min_valid_hours"]
    start, end = date.fromisoformat(config["calendar_start"]), date.fromisoformat(config["calendar_end_exclusive"])
    train_end = date.fromisoformat(config["train_end_exclusive"])
    validation_end = date.fromisoformat(config["validation_end_exclusive"])
    selected = manifest["selected_station"]
    expected_selected, ranks = {}, []

    with zipfile.ZipFile(original) as archive:
        for station, content in source_members(archive):
            days = {}
            seen = set()
            for row in csv.DictReader(io.StringIO(content.decode("utf-8-sig"))):
                assert row["station"] == station, "Mixed station labels"
                stamp = (int(row["year"]), int(row["month"]), int(row["day"]), int(row["hour"]))
                assert stamp not in seen, "Duplicate source timestamp"
                seen.add(stamp)
                day = date(*stamp[:3])
                values = {key: clean(row[key], key) for key in VARIABLES}
                days.setdefault(day, []).append(values)
            train_days = train_pm_hours = 0
            for step in range((end - start).days):
                day = start + timedelta(days=step)
                records = days.get(day, [])
                valid = {key: [row[key] for row in records if row[key] is not None] for key in VARIABLES}
                joint = sum(all(row[key] is not None for key in VARIABLES) for row in records)
                eligible = (all(len(valid[key]) >= minimum for key in VARIABLES if key != "RAIN")
                            and len(valid["RAIN"]) == 24 and joint >= minimum)
                split = "train" if day < train_end else "validation" if day < validation_end else "test"
                if split == "train":
                    train_days += int(eligible)
                    train_pm_hours += len(valid["PM2.5"])
                if station == selected:
                    result = {"hours_observed": len(records), "n_joint_core_hours": joint,
                              "analysis_eligible": eligible, "split": split}
                    for key, name in VARIABLES.items():
                        result[f"n_{name}"] = len(valid[key])
                        threshold = 24 if key == "RAIN" else minimum
                        result[name] = (
                            None if len(valid[key]) < threshold else
                            sum(valid[key]) if key == "RAIN" else statistics.mean(valid[key])
                        )
                    expected_selected[day.isoformat()] = result
            ranks.append((station, train_days, train_pm_hours))
    ranks.sort(key=lambda row: (-row[1], -row[2], row[0]))
    with (ROOT / "results" / "tables" / "station_audit.csv").open(newline="") as handle:
        reported = [(row["station"], int(row["training_analysis_days"]), int(row["training_pm25_valid_hours"]))
                    for row in csv.DictReader(handle)]
    assert ranks == reported, "Station ranking or training counts differ"
    if config["station"] == "auto":
        assert ranks[0][0] == selected, "Wrong automatic station choice"
    checked = 0
    with (ROOT / "data" / "processed" / f"{selected}_daily.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            expected = expected_selected.pop(row["date"])
            assert row["station"] == selected
            for field, value in expected.items():
                actual = row[field]
                if value is None:
                    assert actual == "", (row["date"], field, "missing value expected")
                elif isinstance(value, bool):
                    assert actual == str(value), (row["date"], field)
                elif isinstance(value, str):
                    assert actual == value, (row["date"], field)
                else:
                    assert math.isclose(float(actual), value, rel_tol=1e-10, abs_tol=1e-10), (row["date"], field)
            checked += 1
    assert not expected_selected, "Daily dates missing from processed output"
    result = {"status": "passed", "method": "Independent Python standard-library oracle",
              "raw_sha256": digest, "stations_checked": len(ranks), "selected_station": selected,
              "daily_rows_checked": checked, "station_rank_and_counts_match": True,
              "daily_means_totals_counts_splits_and_eligibility_match": True}
    destination = ROOT / "reports" / "independent_aggregation_check.json"
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    verify()
