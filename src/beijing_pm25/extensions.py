"""Stage 3 exploratory extensions.

Everything here is exploratory: the Stage 2 test year was already scored before
these ideas were tried, so test-year numbers are descriptive, not confirmatory.
All fitting, centring, thresholds and cutoffs still use training (or, for the
logistic cutoff, validation) data only.
"""

import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster.hierarchy import fcluster, linkage
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests

from .data import aggregate_daily
from .model_diagnostics import calendar_hac, joint_wald
from .models import SEASONS, WEATHER, design_matrix, fit_candidates, prediction_rows, score_predictions


COMPASS_DEGREES = {name: 22.5 * step for step, name in enumerate(
    "N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW".split())}
EXTRA_WEATHER = ("dew_point", "southerly", "westerly")
POLLUTANT_NAMES = {"PM2.5": "pm25", "PM10": "pm10", "SO2": "so2", "NO2": "no2", "CO": "co", "O3": "o3"}
SEASON_TERMS = tuple("season_" + season for season in SEASONS[1:])
INTERACTION_TERMS = tuple("wind_x_" + season for season in SEASONS[1:])

# Candidate models, all built on the Stage 2 M3 design.
EXTENSION_MODELS = {
    "M3": {"log": False, "lag": False, "met": False},
    "M3_log": {"log": True, "lag": False, "met": False},
    "M3_lag": {"log": False, "lag": True, "met": False},
    "M3_met": {"log": False, "lag": False, "met": True},
    "M3_log_lag_met": {"log": True, "lag": True, "met": True},
}
MODEL_LABELS = {
    "M3": "M3 refit on common sample",
    "M3_log": "M3 on log(1 + PM2.5)",
    "M3_lag": "M3 + previous day's PM2.5",
    "M3_met": "M3 + dew point + wind direction",
    "M3_log_lag_met": "Log scale + previous day + dew point + wind direction",
    "training_mean": "Training mean (baseline)",
}


# ---------------------------------------------------------------- daily data

def wind_components(direction: pd.Series, speed: pd.Series):
    """Hourly wind-vector components from the compass point the wind blows FROM.

    southerly > 0 means air arriving from the south; westerly > 0 from the west.
    Missing or unknown directions, or missing speeds, give NaN (never imputed).
    """
    angle = np.deg2rad(direction.map(COMPASS_DEGREES).astype(float))
    speed = speed.astype(float)
    return -speed * np.cos(angle), -speed * np.sin(angle)


def extra_daily(hourly: pd.DataFrame, min_valid_hours: int, pollutants=tuple(POLLUTANT_NAMES)):
    """Daily dew point, mean wind vector and pollutant means, using Stage 1's completeness rule."""
    out = {}
    groups = hourly["DEWP"].resample("D")
    out["n_dew_point"] = groups.count()
    out["dew_point"] = groups.mean().where(out["n_dew_point"] >= min_valid_hours)
    southerly, westerly = wind_components(hourly["wd"], hourly["WSPM"])
    valid = southerly.notna() & westerly.notna()
    out["n_wind_vector"] = valid.resample("D").sum().astype(int)
    enough = out["n_wind_vector"] >= min_valid_hours
    out["southerly"] = southerly.resample("D").mean().where(enough)
    out["westerly"] = westerly.resample("D").mean().where(enough)
    for column in pollutants:
        name = POLLUTANT_NAMES[column]
        if name == "pm25":
            continue  # Stage 1 already provides the daily PM2.5 mean.
        groups = hourly[column].resample("D")
        counts = groups.count()
        out[name] = groups.mean().where(counts >= min_valid_hours)
    frame = pd.DataFrame(out)
    frame.index.name = "date"
    return frame


def build_station_daily(data, stage1_config, min_valid_hours):
    """Stage 1 daily calendar plus Stage 3 variables; lag uses the previous CALENDAR day."""
    daily = aggregate_daily(data, stage1_config)
    extra = extra_daily(data.hourly, min_valid_hours)
    if not extra.index.equals(daily.index):
        raise ValueError("Stage 3 daily variables must share the Stage 1 calendar.")
    daily = daily.join(extra)
    # shift() on the complete calendar: a gap gives NaN, never the last observed row.
    daily["pm25_lag1"] = daily["pm25"].shift(1)
    return daily


def common_sample(daily: pd.DataFrame):
    """Stage 2 eligibility plus every Stage 3 predictor, so all candidates share one sample."""
    keep = daily["analysis_eligible"] & daily[[*EXTRA_WEATHER, "pm25_lag1"]].notna().all(axis=1)
    return daily.loc[keep]


def partitions(frame):
    parts = {split: frame.loc[frame["split"].eq(split)] for split in ("train", "validation", "test")}
    if any(part.empty for part in parts.values()):
        raise ValueError("Every chronological partition needs observations.")
    if not parts["train"].index.max() < parts["validation"].index.min() <= parts["validation"].index.max() < parts["test"].index.min():
        raise ValueError("Partitions must be chronological and non-overlapping.")
    return parts


# ------------------------------------------------------ alternative models

def training_centres(training):
    names = (*WEATHER, *EXTRA_WEATHER)
    centres = {name: float(training[name].mean()) for name in names}
    centres["pm25_lag1"] = float(training["pm25_lag1"].mean())
    centres["log_pm25_lag1"] = float(np.log1p(training["pm25_lag1"]).mean())
    return centres


def extension_design(frame, centres, spec):
    design = design_matrix(frame, centres, "M3")
    if spec["met"]:
        for name in EXTRA_WEATHER:
            design[name + "_c"] = frame[name].astype(float) - centres[name]
    if spec["lag"]:
        if spec["log"]:
            design["log_pm25_lag1_c"] = np.log1p(frame["pm25_lag1"].astype(float)) - centres["log_pm25_lag1"]
        else:
            design["pm25_lag1_c"] = frame["pm25_lag1"].astype(float) - centres["pm25_lag1"]
    if not np.isfinite(design.to_numpy()).all():
        raise ValueError("Extension designs need finite inputs.")
    return design


class FittedExtension:
    """OLS on the stated scale; log-scale predictions use Duan's smearing back-transform."""

    def __init__(self, name, training, centres):
        self.name, self.spec, self.centres = name, EXTENSION_MODELS[name], centres
        design = extension_design(training, centres, self.spec)
        n, p = design.shape
        if n <= p or np.linalg.matrix_rank(design.to_numpy()) != p:
            raise ValueError(f"{name}: insufficient or rank-deficient training design.")
        response = training["pm25"].astype(float)
        if self.spec["log"]:
            response = np.log1p(response)
        self.result = sm.OLS(response, design, missing="raise").fit()
        self.smearing = float(np.mean(np.exp(self.result.resid))) if self.spec["log"] else None

    def predict(self, frame):
        linear = self.result.predict(extension_design(frame, self.centres, self.spec)).to_numpy()
        if self.spec["log"]:
            return np.exp(linear) * self.smearing - 1
        return linear


def compare_models(sample, quantile):
    """Fit every candidate on training rows of one common sample; pick by validation MAE."""
    parts = partitions(sample)
    training = parts["train"]
    centres = training_centres(training)
    threshold = float(training["pm25"].quantile(quantile))
    baseline = float(training["pm25"].mean())
    fitted = {name: FittedExtension(name, training, centres) for name in EXTENSION_MODELS}
    rows = []
    for split, frame in parts.items():
        for name, model in fitted.items():
            rows.append(prediction_rows(frame, name, model.predict(frame), threshold))
        rows.append(prediction_rows(frame, "training_mean", np.full(len(frame), baseline), threshold))
    predictions = pd.concat(rows, ignore_index=True)
    scores = score_predictions(predictions)
    validation = scores.loc[scores["split"].eq("validation") & scores["subgroup"].eq("all")
                            & scores["model"].isin(EXTENSION_MODELS)]
    chosen = str(validation.sort_values(["mae", "model"]).iloc[0]["model"])
    summary = pd.DataFrame([{
        "model": name, "label": MODEL_LABELS[name],
        "response_scale": "log1p" if model.spec["log"] else "original",
        "parameters": len(model.result.params), "n_train": int(model.result.nobs),
        "r2_fitted_scale": model.result.rsquared, "adj_r2_fitted_scale": model.result.rsquared_adj,
        "smearing_factor": model.smearing,
        "training_negative_predictions": int((model.predict(training) < 0).sum()),
        "selected_by_validation_mae": name == chosen,
    } for name, model in fitted.items()])
    return {"fitted": fitted, "centres": centres, "threshold": threshold, "baseline": baseline,
            "predictions": predictions, "scores": scores, "summary": summary, "chosen": chosen}


def _hac_frame(result):
    design = pd.DataFrame(result.model.exog, index=result.model.data.row_labels,
                          columns=result.model.exog_names)
    return design


def added_block_tests(fitted, hac_lag):
    """Classical partial F and calendar-HAC Wald tests for each block added to M3."""
    base = fitted["M3"].result
    rows = []
    for name, block in (("M3_met", "dew point + wind direction"), ("M3_lag", "previous day's PM2.5")):
        full = fitted[name].result
        f_value, f_p, df_diff = full.compare_f_test(base)
        added = [term for term in full.params.index if term not in base.params.index]
        positions = [list(full.params.index).index(term) for term in added]
        covariance = calendar_hac(_hac_frame(full), full.resid, hac_lag)
        wald, wald_p = joint_wald(full.params.to_numpy(), covariance, positions)
        rows.append({"comparison": f"M3 -> {name}", "added_block": block, "terms": ";".join(added),
                     "df": int(df_diff), "classical_f": f_value, "classical_p": f_p,
                     "hac_lag_days": hac_lag, "hac_wald_chi2": wald, "hac_p": wald_p,
                     "delta_r2": full.rsquared - base.rsquared})
    return pd.DataFrame(rows)


def coefficient_table(fitted, names, hac_lag, alpha):
    z = float(stats.norm.ppf(1 - alpha / 2))
    rows = []
    for name in names:
        result = fitted[name].result
        covariance = calendar_hac(_hac_frame(result), result.resid, hac_lag)
        for index, (term, value) in enumerate(result.params.items()):
            se = float(np.sqrt(max(0.0, covariance[index, index])))
            rows.append({"model": name, "term": term, "estimate": float(value),
                         "hac_se": se, "hac_p": float(2 * stats.norm.sf(abs(value / se))) if se else np.nan,
                         "hac_ci_lower": float(value - z * se), "hac_ci_upper": float(value + z * se),
                         "classical_p": float(result.pvalues.iloc[index])})
    return pd.DataFrame(rows)


# ---------------------------------------------- regression with AR(1) errors

def ar1_error_tests(training, alpha):
    """Feasible GLS with AR(1) errors (statsmodels GLSAR, iterated Cochrane–Orcutt).

    GLSAR treats consecutive rows as consecutive days; the number of calendar
    gaps it bridges is reported rather than hidden.
    """
    centres = {name: float(training[name].mean()) for name in WEATHER}
    gaps = int((training.index.to_series().diff().dt.days.dropna() > 1).sum())
    z = float(stats.norm.ppf(1 - alpha / 2))
    rows = []
    for hypothesis, model, terms in (("H1: seasons (M1 -> M2)", "M2", SEASON_TERMS),
                                     ("H2: wind x season (M2 -> M3)", "M3", INTERACTION_TERMS)):
        design = design_matrix(training, centres, model)
        result = sm.GLSAR(training["pm25"].astype(float), design, rho=1).iterative_fit(maxiter=100)
        names = list(result.params.index)
        restriction = np.zeros((len(terms), len(names)))
        for row, term in enumerate(terms):
            restriction[row, names.index(term)] = 1.0
        test = result.f_test(restriction)
        wind = names.index("wind_speed_c")
        rows.append({
            "hypothesis": hypothesis, "model": model, "ar1_rho": float(result.model.rho[0]),
            "f_statistic": float(np.squeeze(test.fvalue)), "df_num": int(test.df_num),
            "df_denom": float(test.df_denom), "p_value": float(test.pvalue),
            "wind_coefficient": float(result.params.iloc[wind]),
            "wind_ci_lower": float(result.params.iloc[wind] - z * result.bse.iloc[wind]),
            "wind_ci_upper": float(result.params.iloc[wind] + z * result.bse.iloc[wind]),
            "n_used": int(result.nobs), "calendar_gaps_bridged": gaps,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------- logistic smog-day model

def rank_auc(probabilities, outcomes):
    probabilities, outcomes = np.asarray(probabilities, float), np.asarray(outcomes, bool)
    positives, negatives = int(outcomes.sum()), int((~outcomes).sum())
    if not positives or not negatives:
        return float("nan")
    ranks = stats.rankdata(probabilities)  # ties get average ranks
    return float((ranks[outcomes].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def confusion(probabilities, outcomes, cutoff):
    flagged, outcomes = np.asarray(probabilities) >= cutoff, np.asarray(outcomes, bool)
    tp, fp = int((flagged & outcomes).sum()), int((flagged & ~outcomes).sum())
    fn, tn = int((~flagged & outcomes).sum()), int((~flagged & ~outcomes).sum())
    recall = tp / (tp + fn) if tp + fn else float("nan")
    precision = tp / (tp + fp) if tp + fp else float("nan")
    f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
    return {"cutoff": float(cutoff), "true_positive": tp, "false_positive": fp, "false_negative": fn,
            "true_negative": tn, "recall": recall, "precision": precision, "f1": f1}


def choose_cutoff(probabilities, outcomes):
    """Cutoff with the highest F1 among the observed probabilities (ties: higher cutoff)."""
    outcomes = np.asarray(outcomes, bool)
    if not outcomes.any():
        raise ValueError("The cutoff sample contains no smog days.")
    best = None
    for cutoff in np.unique(np.asarray(probabilities, float)):
        f1 = confusion(probabilities, outcomes, cutoff)["f1"]
        if best is None or f1 >= best[0]:
            best = (f1, float(cutoff))
    return best[1]


def smog_logistic(parts, quantile, alpha):
    """Logit for 'daily PM2.5 >= training quantile' on weather + season (M2 terms).

    Fitted on training, cutoff chosen on validation, then applied unchanged to test.
    Standard errors assume independent days, which Stage 2 showed is false: read
    them as rough guides only.
    """
    training = parts["train"]
    centres = {name: float(training[name].mean()) for name in WEATHER}
    threshold = float(training["pm25"].quantile(quantile))
    designs = {split: design_matrix(frame, centres, "M2") for split, frame in parts.items()}
    outcomes = {split: frame["pm25"].ge(threshold).to_numpy() for split, frame in parts.items()}
    result = sm.Logit(outcomes["train"].astype(float), designs["train"]).fit(disp=0, maxiter=200)
    if not result.mle_retvals.get("converged", False):
        raise ValueError("The smog-day logistic regression did not converge.")
    probabilities = {split: result.predict(design).to_numpy() for split, design in designs.items()}
    cutoff = choose_cutoff(probabilities["validation"], outcomes["validation"])
    performance = []
    for split in parts:
        for rule, value in (("validation_max_f1", cutoff), ("fixed_0.5", 0.5)):
            row = {"split": split, "cutoff_rule": rule, "n": len(outcomes[split]),
                   "smog_days": int(outcomes[split].sum()),
                   "auc": rank_auc(probabilities[split], outcomes[split])}
            row.update(confusion(probabilities[split], outcomes[split], value))
            performance.append(row)
    interval = result.conf_int(alpha=alpha)
    odds = pd.DataFrame({
        "term": result.params.index, "coefficient": result.params.to_numpy(),
        "odds_ratio": np.exp(result.params.to_numpy()),
        "odds_ratio_ci_lower": np.exp(interval.iloc[:, 0].to_numpy()),
        "odds_ratio_ci_upper": np.exp(interval.iloc[:, 1].to_numpy()),
        "p_value_assuming_independence": result.pvalues.to_numpy(),
    })
    daily = pd.concat([pd.DataFrame({"date": frame.index, "split": split, "observed_pm25": frame["pm25"].to_numpy(),
                                     "smog_day": outcomes[split], "probability": probabilities[split]})
                       for split, frame in parts.items()], ignore_index=True)
    return {"threshold": threshold, "cutoff": cutoff, "training_smog_days": int(outcomes["train"].sum()),
            "pseudo_r2": float(result.prsquared), "performance": pd.DataFrame(performance),
            "odds": odds, "daily": daily}


# ------------------------------------------------------- other stations

def station_replication(station, daily, quantile, hac_lag, alpha):
    """Stage 2's M1–M3 on another station's Stage 1-eligible days."""
    eligible = daily.loc[daily["analysis_eligible"]]
    parts = partitions(eligible)
    fitted, centres = fit_candidates(parts["train"])
    covariances = {name: calendar_hac(_hac_frame(result), result.resid, hac_lag)
                   for name, result in fitted.items() if name in ("M2", "M3")}
    m2, m3 = fitted["M2"], fitted["M3"]
    m2_terms, m3_terms = list(m2.params.index), list(m3.params.index)
    _, h1_p = joint_wald(m2.params.to_numpy(), covariances["M2"], [m2_terms.index(t) for t in SEASON_TERMS])
    _, h2_p = joint_wald(m3.params.to_numpy(), covariances["M3"], [m3_terms.index(t) for t in INTERACTION_TERMS])
    holm = multipletests([h1_p, h2_p], alpha=alpha, method="holm")[1]
    wind = m2_terms.index("wind_speed_c")
    se = float(np.sqrt(covariances["M2"][wind, wind]))
    z = float(stats.norm.ppf(1 - alpha / 2))
    test = parts["test"]
    threshold = float(parts["train"]["pm25"].quantile(quantile))
    m3_test = m3.predict(design_matrix(test, centres, "M3")).to_numpy()
    baseline = float(parts["train"]["pm25"].mean())
    high = test["pm25"].to_numpy() >= threshold
    return {
        "station": station, "n_train": len(parts["train"]), "n_validation": len(parts["validation"]),
        "n_test": len(test), "training_mean_pm25": baseline,
        "m3_r2": m3.rsquared, "m2_wind_coefficient": float(m2.params.iloc[wind]),
        "m2_wind_hac_ci_lower": float(m2.params.iloc[wind] - z * se),
        "m2_wind_hac_ci_upper": float(m2.params.iloc[wind] + z * se),
        "h1_hac_p": h1_p, "h2_hac_p": h2_p, "h1_holm_p": float(holm[0]), "h2_holm_p": float(holm[1]),
        "classical_h1_p": float(m2.compare_f_test(fitted["M1"])[1]),
        "classical_h2_p": float(m3.compare_f_test(m2)[1]),
        "test_m3_mae": float(np.abs(m3_test - test["pm25"]).mean()),
        "test_baseline_mae": float(np.abs(baseline - test["pm25"]).mean()),
        "test_m3_high_day_mean_signed_error": float((m3_test - test["pm25"].to_numpy())[high].mean()) if high.any() else np.nan,
        "test_m3_negative_predictions": int((m3_test < 0).sum()),
    }


# ---------------------------------------------------- station clustering

def pollutant_profiles(dailies, variables):
    """Each station's training-period mean of its own valid daily means."""
    rows = []
    for station, daily in dailies.items():
        training = daily.loc[daily["split"].eq("train")]
        row = {"station": station}
        for column in variables:
            name = POLLUTANT_NAMES[column]
            row[name] = float(training[name].mean())
            row[f"n_{name}_days"] = int(training[name].notna().sum())
        rows.append(row)
    return pd.DataFrame(rows).set_index("station").sort_index()


def cluster_stations(profiles, variables, k_range):
    """Ward clustering of z-scored profiles; k = largest gap in merge heights within k_range."""
    columns = [POLLUTANT_NAMES[column] for column in variables]
    values = profiles[columns]
    spread = values.std(ddof=1)
    if (spread <= 0).any() or not np.isfinite(values.to_numpy()).all():
        raise ValueError("Cluster variables must be finite and vary across stations.")
    scaled = (values - values.mean()) / spread
    tree = linkage(scaled.to_numpy(), method="ward")
    heights, n = tree[:, 2], len(values)
    low, high = k_range[0], min(k_range[1], n - 1)
    gaps = {k: float(heights[n - k] - heights[n - k - 1]) for k in range(low, high + 1)}
    k = max(gaps, key=lambda key: (gaps[key], -key))
    raw = fcluster(tree, k, criterion="maxclust")
    # Number clusters by their training mean PM2.5, lowest first.
    order = pd.Series(values["pm25"].to_numpy()).groupby(raw).mean().sort_values().index
    relabel = {old: new for new, old in enumerate(order, start=1)}
    assignments = profiles.copy()
    assignments.insert(0, "cluster", [relabel[label] for label in raw])
    for column in columns:
        assignments[column + "_z"] = scaled[column]
    gap_table = pd.DataFrame({"k": list(gaps), "merge_height_gap": list(gaps.values())})
    gap_table["chosen"] = gap_table["k"].eq(k)
    return {"k": k, "tree": tree, "labels": list(values.index), "assignments": assignments.reset_index(),
            "gaps": gap_table}
