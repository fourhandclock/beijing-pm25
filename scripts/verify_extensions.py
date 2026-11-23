"""Separate numerical verification of Stage 3; no production/statsmodels imports."""

import argparse
import csv
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import linalg, special, stats

from stage4_reference import (EXTRA, POLLUTANTS, SPECIFICATIONS, WEATHER, centres,
                             classification, cutoff_from_validation, daily_data, design,
                             extended_design, glsar_reference, logistic_fit, pair_auc,
                             pairwise_hac, qr_fit, ward_reference)


def rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


ERRORS = {}


def compare(actual, expected, label, atol=1e-7, rtol=1e-7):
    actual, expected = np.asarray(actual, float), np.asarray(expected, float)
    if actual.size:
        ERRORS[label] = max(ERRORS.get(label, 0), float(np.max(np.abs(actual-expected))))
    np.testing.assert_allclose(actual, expected, atol=atol, rtol=rtol, err_msg=label)


def holm_two(values):
    order = np.argsort(values)
    adjusted = np.zeros(2)
    adjusted[order[0]] = min(1, 2*values[order[0]])
    adjusted[order[1]] = max(adjusted[order[0]], values[order[1]])
    return adjusted


def main(root):
    directory = root/"results/stage3"
    run = json.loads((directory/"run.json").read_text())
    if run.get("status") != "complete" or not run.get("exploratory"):
        raise ValueError("A complete exploratory Stage 3 run is required")
    config = json.loads((root/"config/stage1.json").read_text())
    extension_config = run["configuration"]
    primary = extension_config["primary_station"]
    lag = extension_config["primary_hac_lag_days"]
    alpha = extension_config["alpha"]
    raw = root/"data/raw/uci_beijing_multi_site.zip"
    provenance = json.loads((root/"data/raw/provenance.json").read_text())
    if hashlib.sha256(raw.read_bytes()).hexdigest() != provenance["sha256"]:
        raise ValueError("Raw archive differs from committed provenance")
    dailies = daily_data(raw, config)
    eligible = [row for row in dailies[primary] if row["analysis_eligible"]]
    common = [row for row in eligible if all(row[name] is not None for name in (*EXTRA, "pm25_lag1"))]
    parts = {split: [row for row in common if row["split"] == split] for split in ("train", "validation", "test")}
    train = parts["train"]
    center = centres(train)
    y = np.array([row["pm25"] for row in train])
    dates = [date.fromisoformat(row["date"]) for row in train]
    threshold = float(np.quantile(y, extension_config["extreme_training_quantile"]))
    fit_rows = {row["model"]: row for row in rows(directory/"tables/model_comparison_fits.csv")}
    coefficient_rows = rows(directory/"tables/extension_coefficients.csv")
    fitted = {}
    for name, (log, _, _) in SPECIFICATIONS.items():
        x, terms = extended_design(train, center, name)
        fit = qr_fit(x, np.log1p(y) if log else y)
        fit.update(x=x, terms=terms, smearing=float(np.mean(np.exp(fit["residual"]))) if log else None)
        fitted[name] = fit
        saved = fit_rows[name]
        assert int(saved["n_train"]) == len(train) and int(saved["parameters"]) == x.shape[1]
        compare(float(saved["r2_fitted_scale"]), fit["r2"], "response-specific R-squared")
        if log:
            compare(float(saved["smearing_factor"]), fit["smearing"], "training-only smearing factor")
        relevant = [row for row in coefficient_rows if row["model"] == name]
        if relevant:
            covariance = pairwise_hac(x, fit["residual"], dates, lag)
            for row in relevant:
                position = terms.index(row["term"])
                compare(float(row["estimate"]), fit["beta"][position], "extension coefficient")
                compare(float(row["hac_se"]), np.sqrt(covariance[position, position]), "extension HAC SE")
    for saved in rows(directory/"tables/added_block_tests.csv"):
        name = saved["comparison"].split(" -> ")[1]
        base, full = fitted["M3"], fitted[name]
        q = full["x"].shape[1]-base["x"].shape[1]
        df = len(train)-full["x"].shape[1]
        f = ((base["sse"]-full["sse"])/q)/(full["sse"]/df)
        compare(float(saved["classical_f"]), f, "added-block F statistic")
        covariance = pairwise_hac(full["x"], full["residual"], dates, lag)[-q:, -q:]
        wald = float(full["beta"][-q:]@linalg.solve(covariance, full["beta"][-q:], assume_a="pos"))
        compare(float(saved["hac_wald_chi2"]), wald, "added-block HAC Wald statistic")
    predictions = {(row["split"], row["model"], row["date"]): row
                   for row in rows(directory/"tables/model_comparison_predictions.csv")}
    performance = {(row["split"], row["model"], row["subgroup"]): row
                   for row in rows(directory/"tables/model_comparison_scores.csv")}
    validation = {}
    checked = 0
    for split, part in parts.items():
        observed = np.array([row["pm25"] for row in part])
        for name in (*SPECIFICATIONS, "training_mean"):
            if name == "training_mean":
                predicted = np.full(len(part), y.mean())
            else:
                fit = fitted[name]
                predicted = extended_design(part, center, name)[0]@fit["beta"]
                if SPECIFICATIONS[name][0]:
                    predicted = np.exp(predicted)*fit["smearing"]-1
            error = predicted-observed
            for i, row in enumerate(part):
                saved = predictions.pop((split, name, row["date"]))
                compare(float(saved["predicted"]), predicted[i], "extension prediction")
                compare(float(saved["observed"]), observed[i], "independent hourly aggregation")
                assert (saved["high_pollution_day"] == "True") == (observed[i] >= threshold)
                checked += 1
            for group, mask in (("all", np.ones(len(part), bool)), ("high", observed >= threshold), ("below_cutoff", observed < threshold)):
                saved = performance[split, name, group]
                assert int(saved["n"]) == int(mask.sum())
                if mask.any():
                    compare(float(saved["mae"]), np.abs(error[mask]).mean(), "extension MAE")
                    compare(float(saved["rmse"]), np.sqrt(np.mean(error[mask]**2)), "extension RMSE")
                    compare(float(saved["mean_signed_error"]), error[mask].mean(), "extension signed error")
                assert int(saved["negative_predictions"]) == int((predicted[mask] < 0).sum())
            if split == "validation" and name != "training_mean":
                validation[name] = float(np.abs(error).mean())
    assert not predictions
    chosen = min(validation, key=lambda name: (validation[name], name))
    assert chosen == run["selected_by_validation_mae"]

    # Logistic fit is independently optimized, including the validation-only F1 cutoff.
    core_parts = {split: [row for row in eligible if row["split"] == split] for split in parts}
    core_train = core_parts["train"]
    core_y = np.array([row["pm25"] for row in core_train])
    core_center = {name: float(np.mean([row[name] for row in core_train])) for name in WEATHER}
    core_threshold = float(np.quantile(core_y, extension_config["extreme_training_quantile"]))
    matrices = {split: design(part, core_center, "M2")[0] for split, part in core_parts.items()}
    truth = {split: np.array([row["pm25"] >= core_threshold for row in part]) for split, part in core_parts.items()}
    beta, covariance = logistic_fit(matrices["train"], truth["train"].astype(float))
    probability = {split: special.expit(x@beta) for split, x in matrices.items()}
    cutoff = cutoff_from_validation(probability["validation"], truth["validation"])
    logistic = {(row["split"], row["cutoff_rule"]): row for row in rows(directory/"tables/smog_logistic_performance.csv")}
    daily_logistic = {(row["split"], row["date"]): row for row in rows(directory/"tables/smog_logistic_daily.csv")}
    for split, part in core_parts.items():
        for i, row in enumerate(part):
            compare(float(daily_logistic[split, row["date"]]["probability"]), probability[split][i], "logistic probability")
            assert (daily_logistic[split, row["date"]]["smog_day"] == "True") == truth[split][i]
        for rule, value in (("validation_max_f1", cutoff), ("fixed_0.5", 0.5)):
            saved = logistic[split, rule]
            compare(float(saved["cutoff"]), value, "validation-selected probability cutoff")
            compare(float(saved["auc"]), pair_auc(probability[split], truth[split]), "pair-count AUC")
            expected = classification(probability[split], truth[split], value)
            for name in ("true_positive", "false_positive", "false_negative", "true_negative"):
                assert int(saved[name]) == expected[name], (split, rule, name)
    terms = design(core_train, core_center, "M2")[1]
    for saved in rows(directory/"tables/smog_logistic_odds_ratios.csv"):
        i = terms.index(saved["term"])
        se = np.sqrt(covariance[i, i])
        compare(float(saved["coefficient"]), beta[i], "logistic coefficient")
        compare(float(saved["odds_ratio"]), np.exp(beta[i]), "logistic odds ratio")
        compare(float(saved["odds_ratio_ci_lower"]), np.exp(beta[i]-stats.norm.ppf(1-alpha/2)*se), "logistic nominal interval")

    # Original compressed-row GLSAR is checked without calling statsmodels.
    for saved in rows(directory/"tables/ar1_error_tests.csv"):
        x, names = design(core_train, core_center, saved["model"])
        beta_ar, covariance_ar, rho = glsar_reference(x, core_y)
        prefix = "season_" if saved["model"] == "M2" else "wind_x_"
        positions = [i for i, term in enumerate(names) if term.startswith(prefix)]
        b = beta_ar[positions]
        f = float(b@linalg.solve(covariance_ar[np.ix_(positions, positions)], b, assume_a="pos")/len(positions))
        compare(float(saved["ar1_rho"]), rho, "original GLSAR rho")
        compare(float(saved["f_statistic"]), f, "original GLSAR F")
        compare(float(saved["p_value"]), stats.f.sf(f, len(positions), len(core_y)-1-x.shape[1]), "original GLSAR p")

    # Station-level QR fits, actual-date HAC, within-station Holm, and fixed M3 scores.
    station_rows = {row["station"]: row for row in rows(directory/"tables/station_replication.csv")}
    for station, days in sorted(dailies.items()):
        training = [row for row in days if row["split"] == "train" and row["analysis_eligible"]]
        test = [row for row in days if row["split"] == "test" and row["analysis_eligible"]]
        center_station = {name: float(np.mean([row[name] for row in training])) for name in WEATHER}
        target = np.array([row["pm25"] for row in training])
        dates_station = [date.fromisoformat(row["date"]) for row in training]
        estimates, covs, terms_station = {}, {}, {}
        for model in ("M1", "M2", "M3"):
            x, names = design(training, center_station, model)
            estimates[model] = qr_fit(x, target)
            terms_station[model] = names
            if model != "M1":
                covs[model] = pairwise_hac(x, estimates[model]["residual"], dates_station, lag)
        pvalues = []
        for model, prefix in (("M2", "season_"), ("M3", "wind_x_")):
            positions = [i for i, name in enumerate(terms_station[model]) if name.startswith(prefix)]
            b = estimates[model]["beta"][positions]
            statistic = float(b@linalg.solve(covs[model][np.ix_(positions, positions)], b, assume_a="pos"))
            pvalues.append(float(stats.chi2.sf(statistic, len(positions))))
        adjusted = holm_two(pvalues)
        saved = station_rows[station]
        assert int(saved["n_train"]) == len(training) and int(saved["n_test"]) == len(test)
        compare([float(saved["h1_holm_p"]), float(saved["h2_holm_p"])], adjusted, "station Holm p-values")
        wind = terms_station["M2"].index("wind_speed_c")
        compare(float(saved["m2_wind_coefficient"]), estimates["M2"]["beta"][wind], "station wind coefficient")
        compare(float(saved["m2_wind_hac_ci_upper"]), estimates["M2"]["beta"][wind]+stats.norm.ppf(1-alpha/2)*np.sqrt(covs["M2"][wind, wind]), "station HAC interval")
        predicted = design(test, center_station, "M3")[0]@estimates["M3"]["beta"]
        compare(float(saved["test_m3_mae"]), np.abs(predicted-np.array([row["pm25"] for row in test])).mean(), "station fixed-M3 MAE")

    # Direct Ward SSE merging independently verifies profiles, z-scores, gaps and labels.
    variables = extension_config["cluster_variables"]
    station_names = sorted(dailies)
    profiles = []
    for station in station_names:
        training = [row for row in dailies[station] if row["split"] == "train"]
        profiles.append([float(np.mean([row[POLLUTANTS[column]] for row in training if row[POLLUTANTS[column]] is not None])) for column in variables])
    profiles = np.array(profiles)
    k, labels, gaps, scaled = ward_reference(profiles, profiles[:, list(variables).index("PM2.5")], *extension_config["cluster_k_range"])
    clusters = {row["station"]: row for row in rows(directory/"tables/station_clusters.csv")}
    for i, station in enumerate(station_names):
        assert int(clusters[station]["cluster"]) == int(labels[i])
        for j, column in enumerate(variables):
            name = POLLUTANTS[column]
            compare(float(clusters[station][name]), profiles[i, j], "training pollutant profile")
            compare(float(clusters[station][name+"_z"]), scaled[i, j], "profile standardization")
    for saved in rows(directory/"tables/station_cluster_gaps.csv"):
        compare(float(saved["merge_height_gap"]), gaps[int(saved["k"])], "Ward merge-height gap")
        assert (saved["chosen"] == "True") == (int(saved["k"]) == k)
    result = {"status": "passed", "checked_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "method": "Separate CSV/calendar aggregation, QR fits, direct date-pair HAC, trust-region logistic likelihood, and direct Ward SSE merging; no statsmodels/production imports",
              "primary_station": primary, "stations_checked": len(dailies),
              "common_sample_counts": {split: len(part) for split, part in parts.items()},
              "extension_models_checked": len(fitted), "extension_predictions_checked": checked,
              "selected_exploratory_model": chosen, "logistic_validation_cutoff": cutoff,
              "clusters": k, "maximum_absolute_differences": ERRORS,
              "ordinary_and_log_models_lags_smearing_logistic_ar1_stations_clusters_match": True,
              "raw_sha256": provenance["sha256"],
              "stage3_run_sha256": hashlib.sha256((directory/"run.json").read_bytes()).hexdigest()}
    folder = root/"reports/verification"
    folder.mkdir(parents=True, exist_ok=True)
    (folder/"independent_extensions_check.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({key: value for key, value in result.items() if key != "maximum_absolute_differences"}, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    main(parser.parse_args().project_root.resolve())
