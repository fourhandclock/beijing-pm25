"""Separate raw-data and numerical implementations for the submission audit.

No imports from beijing_pm25 or statsmodels. Hourly aggregation uses csv and
calendar dictionaries; regression uses pivoted QR; clustering uses direct Ward
merge costs rather than scipy.cluster.hierarchy.
"""

import csv
from datetime import date, timedelta
import io
import math
from pathlib import PurePosixPath
import re
import zipfile

import numpy as np
from scipy import linalg, optimize, special, stats

from verify_models import design, pairwise_hac


WEATHER = ("temperature", "wind_speed", "rainfall", "pressure")
EXTRA = ("dew_point", "southerly", "westerly")
POLLUTANTS = {"PM2.5": "pm25", "PM10": "pm10", "SO2": "so2", "NO2": "no2", "CO": "co", "O3": "o3"}
SPECIFICATIONS = {"M3": (False, False, False), "M3_log": (True, False, False),
                  "M3_lag": (False, True, False), "M3_met": (False, False, True),
                  "M3_log_lag_met": (True, True, True)}
COMPASS = {name: 2*math.pi*i/16 for i, name in enumerate("N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW".split())}
SEASON = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
          6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}


def clean(value, column):
    if value.strip() in ("NA", "", "NaN", "nan"):
        return None
    number = float(value)
    if not math.isfinite(number) or (column in {*POLLUTANTS, "RAIN", "WSPM"} and number < 0):
        return None
    return None if column == "PRES" and number <= 0 else number


def members(archive):
    pattern = re.compile(r"PRSA_Data_([A-Za-z0-9]+)_\d{8}-\d{8}\.csv$")
    for name in sorted(archive.namelist()):
        if name.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(archive.read(name))) as nested:
                yield from members(nested)
        else:
            match = pattern.fullmatch(PurePosixPath(name).name)
            if match:
                yield match.group(1), archive.read(name)


def daily_data(archive_path, config):
    variables = (*POLLUTANTS, "TEMP", "PRES", "RAIN", "WSPM", "DEWP")
    names = {**POLLUTANTS, "TEMP": "temperature", "PRES": "pressure", "RAIN": "rainfall",
             "WSPM": "wind_speed", "DEWP": "dew_point"}
    start, end = date.fromisoformat(config["calendar_start"]), date.fromisoformat(config["calendar_end_exclusive"])
    train_end = date.fromisoformat(config["train_end_exclusive"])
    validation_end = date.fromisoformat(config["validation_end_exclusive"])
    minimum = config["min_valid_hours"]
    stations = {}
    with zipfile.ZipFile(archive_path) as archive:
        for station, content in members(archive):
            grouped, seen = {}, set()
            for row in csv.DictReader(io.StringIO(content.decode("utf-8-sig"))):
                if row["station"] != station:
                    raise ValueError("Mixed station in independent raw-data reader")
                stamp = tuple(int(row[name]) for name in ("year", "month", "day", "hour"))
                if stamp in seen:
                    raise ValueError("Duplicate timestamp in original data")
                seen.add(stamp)
                day = date(*stamp[:3])
                values = {column: clean(row[column], column) for column in variables}
                group = grouped.setdefault(day, {**{column: [] for column in variables},
                                                  "southerly": [], "westerly": [], "joint": 0, "rows": 0})
                group["rows"] += 1
                for column, value in values.items():
                    if value is not None:
                        group[column].append(value)
                group["joint"] += int(all(values[column] is not None for column in ("PM2.5", "TEMP", "PRES", "WSPM", "RAIN")))
                direction, speed = row["wd"], values["WSPM"]
                if direction in COMPASS and speed is not None:
                    group["southerly"].append(-speed*math.cos(COMPASS[direction]))
                    group["westerly"].append(-speed*math.sin(COMPASS[direction]))
            days = []
            previous = None
            for step in range((end-start).days):
                day = start + timedelta(days=step)
                group = grouped.get(day, {**{column: [] for column in variables},
                                           "southerly": [], "westerly": [], "joint": 0, "rows": 0})
                result = {"date": day.isoformat(), "station": station, "season": SEASON[day.month],
                          "split": "train" if day < train_end else "validation" if day < validation_end else "test"}
                for column, name in names.items():
                    values = group[column]
                    required = 24 if column == "RAIN" else minimum
                    result[name] = (None if len(values) < required else
                                    math.fsum(values) if column == "RAIN" else math.fsum(values)/len(values))
                    result["n_"+name] = len(values)
                for name in ("southerly", "westerly"):
                    values = group[name]
                    result[name] = math.fsum(values)/len(values) if len(values) >= minimum else None
                result["analysis_eligible"] = (all(result[name] is not None for name in ("pm25", *WEATHER))
                                                 and group["joint"] >= minimum)
                result["pm25_lag1"] = previous
                previous = result["pm25"]
                days.append(result)
            stations[station] = days
    return stations


def centres(training):
    result = {name: float(np.mean([row[name] for row in training])) for name in (*WEATHER, *EXTRA, "pm25_lag1")}
    result["log_pm25_lag1"] = float(np.mean(np.log1p([row["pm25_lag1"] for row in training])))
    return result


def extended_design(rows, center, name):
    log, lag, met = SPECIFICATIONS[name]
    x, terms = design(rows, center, "M3")
    pieces = [x]
    if met:
        pieces.append(np.array([[row[column]-center[column] for column in EXTRA] for row in rows]))
        terms.extend(column+"_c" for column in EXTRA)
    if lag:
        values = np.array([row["pm25_lag1"] for row in rows])
        values = np.log1p(values)-center["log_pm25_lag1"] if log else values-center["pm25_lag1"]
        pieces.append(values[:, None])
        terms.append("log_pm25_lag1_c" if log else "pm25_lag1_c")
    return np.column_stack(pieces), terms


def qr_fit(x, response):
    beta, _, rank, _ = linalg.lstsq(x, response, lapack_driver="gelsy")
    if rank != x.shape[1]:
        raise ValueError("Independent design is rank deficient")
    residual = response-x@beta
    return {"beta": beta, "residual": residual, "sse": float(residual@residual),
            "r2": float(1-(residual@residual)/np.sum((response-response.mean())**2))}


def logistic_fit(x, outcomes):
    def objective(beta):
        eta = x@beta
        return float(np.sum(np.logaddexp(0, eta)-outcomes*eta))
    def gradient(beta):
        return x.T@(special.expit(x@beta)-outcomes)
    def hessian(beta):
        probability = special.expit(x@beta)
        return x.T@((probability*(1-probability))[:, None]*x)
    initial = np.zeros(x.shape[1])
    initial[0] = special.logit(outcomes.mean())
    fit = optimize.minimize(objective, initial, method="trust-exact", jac=gradient, hess=hessian,
                            options={"gtol": 1e-8, "maxiter": 200})
    beta = fit.x.copy()
    for _ in range(6):
        if np.max(np.abs(gradient(beta))) < 1e-9:
            break
        beta -= linalg.solve(hessian(beta), gradient(beta), assume_a="pos")
    if np.max(np.abs(gradient(beta))) > 1e-6:
        raise ValueError("Independent logistic score did not converge")
    return beta, linalg.inv(hessian(beta))


def classification(probability, truth, cutoff):
    flagged = probability >= cutoff
    tp, fp = int(np.sum(flagged & truth)), int(np.sum(flagged & ~truth))
    fn, tn = int(np.sum(~flagged & truth)), int(np.sum(~flagged & ~truth))
    f1 = 2*tp/(2*tp+fp+fn) if tp else 0.0
    return {"true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn, "f1": f1}


def cutoff_from_validation(probability, truth):
    candidates = np.unique(probability)
    return float(max(candidates, key=lambda cutoff: (classification(probability, truth, cutoff)["f1"], cutoff)))


def pair_auc(probability, truth):
    positive, negative = probability[truth], probability[~truth]
    if not len(positive) or not len(negative):
        return np.nan
    return float(np.mean((positive[:, None] > negative[None, :]) + 0.5*(positive[:, None] == negative[None, :])))


def ward_reference(values, pm25, minimum_k, maximum_k):
    scaled = (values-values.mean(axis=0))/values.std(axis=0, ddof=1)
    n = len(values)
    active = {i: {"members": [i], "mean": scaled[i].copy()} for i in range(n)}
    heights, partitions = [], {n: [[i] for i in range(n)]}
    for step in range(n-1):
        keys = sorted(active)
        choices = []
        for i, a in enumerate(keys):
            for b in keys[i+1:]:
                left, right = active[a], active[b]
                na, nb = len(left["members"]), len(right["members"])
                cost = na*nb/(na+nb)*np.sum((left["mean"]-right["mean"])**2)
                choices.append((float(cost), a, b))
        cost, a, b = min(choices)
        left, right = active.pop(a), active.pop(b)
        na, nb = len(left["members"]), len(right["members"])
        active[n+step] = {"members": left["members"]+right["members"],
                          "mean": (na*left["mean"]+nb*right["mean"])/(na+nb)}
        heights.append(math.sqrt(2*cost))
        partitions[len(active)] = [item["members"].copy() for item in active.values()]
    gaps = {k: heights[n-k]-heights[n-k-1] for k in range(minimum_k, min(maximum_k, n-1)+1)}
    selected = max(gaps, key=lambda k: (gaps[k], -k))
    groups = sorted(partitions[selected], key=lambda group: np.mean(pm25[group]))
    labels = np.zeros(n, dtype=int)
    for cluster, group in enumerate(groups, 1):
        labels[group] = cluster
    return selected, labels, gaps, scaled


def glsar_reference(x, y):
    """Reimplement the documented iterated Yule–Walker procedure with QR fits."""
    rho, last = 0.0, None
    for _ in range(99):
        wx, wy = x[1:]-rho*x[:-1], y[1:]-rho*y[:-1]
        fit = qr_fit(wx, wy)
        beta = fit["beta"]
        if last is not None and np.max(np.abs(last-beta)/np.abs(last)) < 1e-4:
            break
        last = beta.copy()
        error = y-x@beta
        error -= error.mean()
        rho = float((error[1:]@error[:-1]/(len(y)-1))/(error@error/len(y)))
    wx, wy = x[1:]-rho*x[:-1], y[1:]-rho*y[:-1]
    fit = qr_fit(wx, wy)
    covariance = fit["sse"]/(len(y)-1-x.shape[1])*linalg.inv(wx.T@wx)
    return fit["beta"], covariance, rho
