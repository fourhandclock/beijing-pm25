"""Independent QR-based verification of real-data Stage 2 results.

Uses csv/NumPy/SciPy, with no imports from the project analysis package or
statsmodels. The HAC oracle pairs actual dates rather than zero-padding scores.
"""

import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import linalg, stats


ROOT = Path(__file__).resolve().parents[1]
WEATHER = ("temperature", "wind_speed", "rainfall", "pressure")
SEASONS = ("spring", "summer", "autumn")


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def close(actual, expected, message, rtol=1e-8, atol=1e-8):
    np.testing.assert_allclose(actual, expected, rtol=rtol, atol=atol, err_msg=message)


def design(rows, centers, model):
    weather = np.array([[float(row[name]) - centers[name] for name in WEATHER] for row in rows])
    columns = [np.ones(len(rows)), *weather.T]
    names = ["Intercept", *(name + "_c" for name in WEATHER)]
    if model != "M1":
        indicators = [np.array([row["season"] == season for row in rows], dtype=float) for season in SEASONS]
        columns.extend(indicators)
        names.extend("season_" + season for season in SEASONS)
        if model == "M3":
            columns.extend(weather[:, 1] * indicator for indicator in indicators)
            names.extend("wind_x_" + season for season in SEASONS)
    return np.column_stack(columns), names


def pairwise_hac(x, error, dates, lag):
    n, p = x.shape
    bread = linalg.solve(x.T @ x, np.eye(p), assume_a="pos")
    scores = x * error[:, None]
    meat = scores.T @ scores
    lookup = {day: i for i, day in enumerate(dates)}
    for distance in range(1, lag + 1):
        cross = np.zeros((p, p))
        for i, day in enumerate(dates):
            earlier = lookup.get(day - timedelta(days=distance))
            if earlier is not None:
                cross += np.outer(scores[i], scores[earlier])
        meat += (1 - distance / (lag + 1)) * (cross + cross.T)
    return n / (n - p) * bread @ meat @ bread


def verify():
    directory = ROOT / "results" / "stage2"
    manifest = json.loads((directory / "run.json").read_text())
    if manifest.get("status") != "complete":
        raise ValueError("A completed Stage 2 run is required.")
    config = manifest["configuration"]
    parameters = json.loads((directory / "model_parameters.json").read_text())
    frozen = json.loads((directory / "frozen_model.json").read_text())
    daily = read_rows(ROOT / "data" / "processed" / f"{manifest['station']}_daily.csv")
    partitions = {split: [row for row in daily if row["analysis_eligible"] == "True" and row["split"] == split]
                  for split in ("train", "validation", "test")}
    training = partitions["train"]
    y = np.array([float(row["pm25"]) for row in training])
    dates = [date.fromisoformat(row["date"]) for row in training]
    centers = {name: float(np.mean([float(row[name]) for row in training])) for name in WEATHER}
    cutoff = float(np.quantile(y, config["extreme_training_quantile"]))
    close(cutoff, frozen["high_pollution_training_cutoff"], "Training-only cutoff")
    close(y.mean(), frozen["training_mean_baseline"], "Training-only mean baseline")
    for name in WEATHER:
        close(centers[name], frozen["training_centers"][name], "Training-only centering")
    matrices, coefficients, errors, sums, covariance = {}, {}, {}, {}, {}
    covariance_rows = read_rows(directory / "tables" / "hac_covariances.csv")
    influence_rows = read_rows(directory / "tables" / "training_influence.csv")
    diagnostic_rows = {row["model"]: row for row in read_rows(directory / "tables" / "residual_diagnostics.csv")}
    for model in ("M1", "M2", "M3"):
        x, names = design(training, centers, model)
        # Pivoted QR provides an independent solver from statsmodels' SVD fit.
        coefficient, _, rank, _ = linalg.lstsq(x, y, lapack_driver="gelsy")
        assert rank == x.shape[1], "Unexpected rank deficiency"
        assert names == parameters["models"][model]["columns"], "Design names differ"
        saved = np.array([parameters["models"][model]["coefficients"][name] for name in names])
        close(saved, coefficient, f"{model} coefficients")
        error = y - x @ coefficient
        matrices[model], coefficients[model], errors[model] = x, coefficient, error
        sums[model] = float(error @ error)
        covariance[model] = {}
        for lag in config["hac_lag_days"]:
            expected = pairwise_hac(x, error, dates, lag)
            saved = {(row["row_term"], row["column_term"]): float(row["covariance"])
                     for row in covariance_rows if row["model"] == model and int(row["hac_lag_calendar_days"]) == lag}
            reported = np.array([[saved[left, right] for right in names] for left in names])
            close(reported, expected, f"{model} {lag}-day covariance")
            covariance[model][lag] = expected
        n, p = x.shape
        bread = linalg.solve(x.T @ x, np.eye(p), assume_a="pos")
        leverage = np.einsum("ij,jk,ik->i", x, bread, x)
        cook = error ** 2 / (p * (sums[model] / (n - p))) * leverage / (1 - leverage) ** 2
        reported = [row for row in influence_rows if row["model"] == model]
        assert [row["date"] for row in reported] == [row["date"] for row in training]
        close([float(row["leverage"]) for row in reported], leverage, "Leverage")
        close([float(row["cooks_distance"]) for row in reported], cook, "Cook's distance")
        diagnostic = diagnostic_rows[model]
        lag = config["serial_test_lag_days"]
        date_lookup = {day: i for i, day in enumerate(dates)}
        available = [i for i, day in enumerate(dates)
                     if all(day - timedelta(days=distance) in date_lookup for distance in range(1, lag + 1))]
        lagged = np.array([[error[date_lookup[dates[i] - timedelta(days=distance)]]
                            for distance in range(1, lag + 1)] for i in available])
        auxiliary = np.column_stack([x[available], lagged])
        response = error[available]
        auxiliary_beta = linalg.lstsq(auxiliary, response, lapack_driver="gelsy")[0]
        auxiliary_error = response - auxiliary @ auxiliary_beta
        r_squared = 1 - (auxiliary_error @ auxiliary_error) / np.sum((response - response.mean()) ** 2)
        assert len(available) == int(diagnostic["serial_auxiliary_n"]), "Calendar-lag diagnostic count"
        close(float(diagnostic["serial_lm_approx"]), len(available) * r_squared, "Calendar-lag BG-style LM")
        squares = error ** 2
        bp_beta = linalg.lstsq(x, squares, lapack_driver="gelsy")[0]
        bp_error = squares - x @ bp_beta
        bp_lm = n * (1 - (bp_error @ bp_error) / np.sum((squares - squares.mean()) ** 2))
        close(float(diagnostic["koenker_bp_lm"]), bp_lm, "Koenker BP statistic")
        centered = error - error.mean()
        second = np.mean(centered ** 2)
        skewness = np.mean(centered ** 3) / second ** 1.5
        kurtosis = np.mean(centered ** 4) / second ** 2
        close(float(diagnostic["jarque_bera"]), n / 6 * (skewness ** 2 + (kurtosis - 3) ** 2 / 4), "Jarque–Bera statistic")

    for row in read_rows(directory / "tables" / "nested_anova.csv"):
        small, large = row["restricted"], row["full"]
        n, p = matrices[large].shape
        q = p - matrices[small].shape[1]
        f_value = ((sums[small] - sums[large]) / q) / (sums[large] / (n - p))
        close(float(row["f_statistic"]), f_value, "Nested F statistic")
        close(float(row["p_value_iid"]), stats.f.sf(f_value, q, n - p), "Nested F p-value")
    robust_rows = read_rows(directory / "tables" / "hac_joint_tests.csv")
    for row in robust_rows:
        small, large = row["restricted"], row["full"]
        start = matrices[small].shape[1]
        beta = coefficients[large][start:]
        cov = covariance[large][int(row["hac_lag_calendar_days"])][start:, start:]
        wald = float(beta @ linalg.solve(cov, beta, assume_a="pos"))
        close(float(row["wald_chi2"]), wald, "Joint HAC Wald statistic")
        close(float(row["p_value_hac"]), stats.chi2.sf(wald, len(beta)), "Joint HAC p-value", atol=1e-12)
    primary = sorted((row for row in robust_rows if row["primary_bandwidth"] == "True"),
                     key=lambda row: float(row["p_value_hac"]))
    previous = 0.0
    for position, row in enumerate(primary):
        previous = max(previous, min(1.0, (len(primary) - position) * float(row["p_value_hac"])))
        close(float(row["p_holm_primary"]), previous, "Holm adjustment across the two primary hypotheses")

    # Reproduce the validation rule before evaluating only the frozen test model.
    validation_y = np.array([float(row["pm25"]) for row in partitions["validation"]])
    validation_mae = {}
    for model in ("M1", "M2", "M3"):
        x, _ = design(partitions["validation"], centers, model)
        validation_mae[model] = float(np.abs(x @ coefficients[model] - validation_y).mean())
    limit = min(validation_mae.values()) * (1 + config["simplicity_tolerance_fraction"])
    choice = min((model for model in validation_mae if validation_mae[model] <= limit + 1e-12),
                 key=lambda model: (len(coefficients[model]), validation_mae[model], model))
    assert choice == frozen["selected_model"] == manifest["selected_model"], "Validation selection differs"
    close([frozen["coefficients"][name] for name in frozen["columns"]], coefficients[choice], "Frozen coefficients")
    lookup = {(row["split"], row["model"], row["date"]): row
              for row in read_rows(directory / "tables" / "predictions.csv")}
    metric_rows = read_rows(directory / "tables" / "performance.csv")
    predictions_checked = 0
    for split, rows in partitions.items():
        observed = np.array([float(row["pm25"]) for row in rows])
        models = (choice, "training_mean") if split == "test" else ("M1", "M2", "M3", "training_mean")
        for model in models:
            predicted = (np.full(len(rows), y.mean()) if model == "training_mean" else
                         design(rows, centers, model)[0] @ coefficients[model])
            error = predicted - observed
            for i, row in enumerate(rows):
                saved = lookup.pop((split, model, row["date"]))
                close(float(saved["predicted"]), predicted[i], "Predicted value")
                close(float(saved["signed_error"]), error[i], "Prediction-minus-observation sign")
                assert (saved["high_pollution_day"] == "True") == (observed[i] >= cutoff)
                predictions_checked += 1
            for subgroup, mask in (("all", np.ones(len(rows), dtype=bool)),
                                   ("high", observed >= cutoff), ("below_cutoff", observed < cutoff)):
                saved = next(item for item in metric_rows if (item["split"], item["model"], item["subgroup"]) == (split, model, subgroup))
                assert int(saved["n"]) == int(mask.sum()), "Subgroup count"
                if mask.any():
                    close(float(saved["mae"]), np.abs(error[mask]).mean(), "MAE")
                    close(float(saved["rmse"]), np.sqrt(np.mean(error[mask] ** 2)), "RMSE")
                    close(float(saved["mean_signed_error"]), error[mask].mean(), "Mean signed error")
                else:
                    assert saved["mae"] == saved["rmse"] == saved["mean_signed_error"] == ""
                assert int(saved["negative_predictions"]) == int((predicted[mask] < 0).sum())
    assert not lookup, "Unexpected predictions, including an unselected candidate on test dates"
    raw = ROOT / "data" / "raw" / "uci_beijing_multi_site.zip"
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == manifest["raw_sha256"]
    result = {"status": "passed", "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "method": "Independent pivoted-QR OLS and observed-date-pair HAC (no statsmodels/project imports)",
              "station": manifest["station"], "selected_model": choice, "models_checked": 3,
              "hac_covariances_checked": 3 * len(config["hac_lag_days"]),
              "prediction_rows_checked": predictions_checked,
              "nested_f_joint_wald_influence_and_performance_match": True,
              "calendar_serial_bp_jb_and_primary_holm_checks_match": True,
              "source_archive_unchanged": True,
              "oracle_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "stage2_run_sha256": hashlib.sha256((directory / "run.json").read_bytes()).hexdigest()}
    (ROOT / "reports" / "independent_model_check.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    verify()
