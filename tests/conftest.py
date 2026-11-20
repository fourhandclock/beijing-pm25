"""Explicit synthetic fixtures for correctness tests, never empirical results."""

import csv
from datetime import datetime, timedelta
import io
import zipfile

import pytest

from beijing_pm25.config import Stage1Config


@pytest.fixture
def small_config():
    return Stage1Config(
        calendar_start="2013-03-01", train_end_exclusive="2013-03-05",
        validation_end_exclusive="2013-03-07", calendar_end_exclusive="2013-03-09",
        max_acf_lag=3,
    )


def hourly_rows(station="Alpha", days=8, offset=0):
    rows = []
    start = datetime(2013, 3, 1)
    for step in range(days * 24):
        stamp = start + timedelta(hours=step)
        rows.append({
            "No": step + 1, "year": stamp.year, "month": stamp.month,
            "day": stamp.day, "hour": stamp.hour,
            "PM2.5": 10 + offset + (step // 24) * 5 + stamp.hour,
            "PM10": 40, "SO2": 5, "NO2": 20, "CO": 600, "O3": 30,
            "TEMP": -3 + stamp.hour / 2, "PRES": 1010, "DEWP": -10,
            "RAIN": 0, "wd": "N", "WSPM": 2, "station": station,
        })
    return rows


def csv_bytes(rows):
    handle = io.StringIO(newline="")
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return handle.getvalue().encode("utf-8")


def write_archive(path, station_rows, *, nested=True, auxiliary=True):
    target = io.BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for station, rows in station_rows.items():
            archive.writestr(f"PRSA_Data_20130301-20170228/PRSA_Data_{station}_20130301-20170228.csv", csv_bytes(rows))
    if nested:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("PRSA2017_Data_20130301-20170228.zip", target.getvalue())
            if auxiliary:
                archive.writestr("data.csv", "unrelated,example\n1,2\n")
                archive.writestr("test.csv", "unrelated,example\n3,4\n")
    else:
        path.write_bytes(target.getvalue())
    return path
