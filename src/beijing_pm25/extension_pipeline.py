"""Stage 3 orchestration: exploratory extensions, figures, report and run record.

Stage 3 does not depend on Stage 2's run record. It re-reads the preserved raw
archive with Stage 1's rules and records each station member's SHA-256, so its
verification checks content, not just the archive wrapper.
"""

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import time

from scipy.cluster.hierarchy import dendrogram
import numpy as np
import pandas as pd

from . import __version__
from .acquire import iter_station_csvs, sha256_file, utc_now, verify_raw, write_json
from .config import Stage1Config
from .data import read_station
from .extension_config import Stage3Config
from .extensions import (MODEL_LABELS, added_block_tests, ar1_error_tests, build_station_daily,
                         cluster_stations, coefficient_table, common_sample, compare_models,
                         partitions, pollutant_profiles, smog_logistic, station_replication)
from .model_pipeline import _json_safe, _write_csv
from .pipeline import _project_file


def _fmt(value, digits=3):
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "–"
    if isinstance(value, (bool, np.bool_)):
        return "yes" if value else "no"
    if isinstance(value, (int, np.integer)):
        return f"{int(value):,}"
    if isinstance(value, (float, np.floating)):
        if value != 0 and abs(value) < 10 ** -digits:
            return f"{value:.1e}"
        return f"{value:,.{digits}f}"
    return str(value)


def _table(frame, columns, headers, digits=None):
    digits = digits or {}
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for _, row in frame.iterrows():
        lines.append("| " + " | ".join(_fmt(row[c], digits.get(c, 3)) for c in columns) + " |")
    return "\n".join(lines)


def _figures(root, comparison, stations, clusters, logistic):
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".mplconfig"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    folder = root / "results" / "stage3" / "figures"
    folder.mkdir(parents=True, exist_ok=True)
    outputs = []

    def save(fig, name):
        path = folder / name
        fig.savefig(path, dpi=150, bbox_inches="tight", metadata={"Software": None})
        plt.close(fig)
        outputs.append(path)

    scores = comparison["scores"]
    overall = scores.loc[scores["subgroup"].eq("all") & scores["split"].isin(["validation", "test"])]
    order = list(MODEL_LABELS)
    fig, ax = plt.subplots(figsize=(10, 5))
    width = 0.38
    for offset, (split, colour) in enumerate((("validation", "#3D7EBF"), ("test", "#D9822B"))):
        values = overall.loc[overall["split"].eq(split)].set_index("model").reindex(order)["mae"]
        ax.barh(np.arange(len(order)) + (offset - 0.5) * width, values, height=width, color=colour, label=split)
    ax.set_yticks(np.arange(len(order)), [MODEL_LABELS[name] for name in order])
    ax.invert_yaxis()
    ax.set_xlabel("Mean absolute error (µg/m³)")
    ax.set_title("Exploratory models: validation and test MAE (test year already seen in Stage 2)")
    ax.legend(frameon=False)
    save(fig, "extension_model_mae.png")

    table = stations.sort_values("m2_wind_coefficient")
    fig, ax = plt.subplots(figsize=(8, 6))
    y = np.arange(len(table))
    ax.errorbar(table["m2_wind_coefficient"], y,
                xerr=[table["m2_wind_coefficient"] - table["m2_wind_hac_ci_lower"],
                      table["m2_wind_hac_ci_upper"] - table["m2_wind_coefficient"]],
                fmt="o", color="#1B2430", ecolor="#8A94A6", capsize=3)
    ax.axvline(0, color="#999999", linewidth=1)
    ax.set_yticks(y, table["station"])
    ax.set_xlabel("M2 wind-speed coefficient, µg/m³ per 1 m/s (HAC 95% CI)")
    ax.set_title("Wind association at all 12 stations (training years)")
    save(fig, "station_wind_coefficients.png")

    fig, ax = plt.subplots(figsize=(9, 5))
    dendrogram(clusters["tree"], labels=clusters["labels"], ax=ax, color_threshold=None)
    ax.set_ylabel("Ward merge height (z-scored pollutant profile)")
    ax.set_title(f"Hierarchical clustering of stations by pollutant profile (k = {clusters['k']})")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    save(fig, "station_dendrogram.png")

    daily = logistic["daily"].loc[logistic["daily"]["split"].isin(["validation", "test"])]
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(daily["date"], daily["probability"], color="#3D7EBF", linewidth=0.9, label="Predicted probability")
    smog = daily.loc[daily["smog_day"]]
    ax.scatter(smog["date"], smog["probability"], color="#D9822B", s=22, zorder=3, label="Observed smog day")
    ax.axhline(logistic["cutoff"], color="#1B2430", linestyle="--", linewidth=1,
               label=f"Cutoff chosen on validation ({logistic['cutoff']:.3f})")
    ax.set_ylabel("P(smog day)")
    ax.set_title("Logistic smog-day model, validation and test years")
    ax.legend(frameon=False, loc="upper right")
    save(fig, "smog_logistic_probabilities.png")
    return outputs


def _report(config, comparison, blocks, coefficients, ar1, logistic, stations, clusters, sample_note, invocation):
    scores = comparison["scores"]
    overall = scores.loc[scores["subgroup"].eq("all")].copy()
    high = scores.loc[scores["subgroup"].eq("high")].copy()
    wide = overall.pivot(index="model", columns="split", values="mae").reindex(list(MODEL_LABELS))
    rmse = overall.pivot(index="model", columns="split", values="rmse").reindex(list(MODEL_LABELS))
    bias = high.pivot(index="model", columns="split", values="mean_signed_error").reindex(list(MODEL_LABELS))
    negatives = overall.pivot(index="model", columns="split", values="negative_predictions").reindex(list(MODEL_LABELS))
    perf = pd.DataFrame({
        "model": [MODEL_LABELS[name] for name in wide.index],
        "val_mae": wide["validation"].to_numpy(), "test_mae": wide["test"].to_numpy(),
        "test_rmse": rmse["test"].to_numpy(), "test_high_bias": bias["test"].to_numpy(),
        "test_negative": negatives["test"].to_numpy(),
    })
    summary = comparison["summary"].copy()
    summary["label"] = summary["model"].map(MODEL_LABELS)
    chosen = comparison["chosen"]
    m3_val = float(wide.loc["M3", "validation"])
    chosen_val = float(wide.loc[chosen, "validation"])
    log_perf = logistic["performance"]
    tuned = log_perf.loc[log_perf["cutoff_rule"].eq("validation_max_f1")]
    fixed = log_perf.loc[log_perf["cutoff_rule"].eq("fixed_0.5")]
    odds = logistic["odds"].loc[~logistic["odds"]["term"].eq("Intercept")]
    coefficient_display = coefficients.copy()
    coefficient_display["response_scale"] = coefficient_display["model"].map(
        lambda name: "log1p" if comparison["fitted"][name].spec["log"] else "original"
    )
    assignments = clusters["assignments"].sort_values(["cluster", "station"])
    wind_all_negative = bool((stations["m2_wind_hac_ci_upper"] < 0).all())
    h1_sig = int((stations["h1_holm_p"] < config.alpha).sum())
    h2_sig = int((stations["h2_holm_p"] < config.alpha).sum())
    beats = int((stations["test_m3_mae"] < stations["test_baseline_mae"]).sum())
    return f"""# Stage 3 — exploratory extensions

> **Status: exploratory.** These analyses were added after the Stage 2 test year had been scored.
> Fitting and preprocessing use training observations; the logistic probability cutoff uses validation.
> Because the test year had already been examined, these results provide no new confirmatory test.
> The prespecified Stage 2 analysis and its frozen test evaluation remain separate.

Command: `{invocation}`

## 1. Exploratory model comparisons at {config.primary_station}

{sample_note}

{_table(perf, ["model", "val_mae", "test_mae", "test_rmse", "test_high_bias", "test_negative"],
        ["Model", "Validation MAE", "Test MAE", "Test RMSE", "Test smog-day mean error", "Test predictions < 0"],
        {"val_mae": 1, "test_mae": 1, "test_rmse": 1, "test_high_bias": 1})}

Smog day = PM2.5 ≥ {comparison['threshold']:.1f} µg/m³ (training {100 * config.extreme_training_quantile:g}th percentile of this sample).
Negative mean error = underestimate. Lowest validation MAE: **{MODEL_LABELS[chosen]}** ({chosen_val:.1f} vs {m3_val:.1f} for M3).

{_table(summary, ["label", "response_scale", "parameters", "r2_fitted_scale", "smearing_factor", "training_negative_predictions"],
        ["Model", "Scale", "Parameters", "Training R² (own scale)", "Smearing factor", "Training predictions < 0"],
        {"r2_fitted_scale": 3, "smearing_factor": 3})}

The M3 row is refitted on this smaller common sample; it is not the original frozen Stage 2 evaluation.
R² on the log scale is not comparable with R² on the original scale. For a log1p model, estimates are
back-transformed as exp(fitted log1p response) × mean(exp(training residual)) − 1. This global Duan
smearing factor uses training residuals only and need not remove conditional bias under heteroscedasticity.
The transformation permits estimates above −1; nonnegative estimates in these runs are an empirical result,
not a mathematical guarantee. No estimate is silently clipped.

### Do the added variables help beyond M3? (training data)

{_table(blocks, ["comparison", "added_block", "df", "classical_f", "classical_p", "hac_p", "delta_r2"],
        ["Comparison", "Added", "df", "Partial F", "Classical p", f"HAC({config.primary_hac_lag_days}-day) p", "ΔR²"],
        {"classical_f": 2, "delta_r2": 3})}

### Coefficients of the added variables (HAC {config.primary_hac_lag_days}-day standard errors)

{_table(coefficient_display.loc[coefficient_display["term"].isin(["dew_point_c", "southerly_c", "westerly_c", "pm25_lag1_c", "log_pm25_lag1_c"])],
        ["model", "response_scale", "term", "estimate", "hac_ci_lower", "hac_ci_upper", "hac_p"],
        ["Model", "Response scale", "Term", "Estimate", "95% CI low", "95% CI high", "HAC p"], {"estimate": 2, "hac_ci_lower": 2, "hac_ci_upper": 2})}

Units: dew point per °C; southerly/westerly per 1 m/s of mean wind vector from the south/west; previous-day PM2.5 per µg/m³.
Original-response coefficients describe changes in µg/m³. Log1p-response coefficients describe changes
in log(1 + PM2.5); exp(coefficient) scales 1 + PM2.5 for a unit change in the stated predictor.
The combined model uses log(1 + previous-day PM2.5), not the untransformed lag.

## 2. Modelling the autocorrelation directly: regression with AR(1) errors

Feasible GLS (iterated Cochrane–Orcutt, statsmodels GLSAR) on the Stage 2 training sample.

{_table(ar1, ["hypothesis", "ar1_rho", "f_statistic", "df_num", "df_denom", "p_value", "wind_coefficient", "wind_ci_lower", "wind_ci_upper"],
        ["Test", "AR(1) ρ", "F", "df1", "df2", "p", "Wind coef.", "CI low", "CI high"],
        {"f_statistic": 2, "df_denom": 0, "wind_coefficient": 1, "wind_ci_lower": 1, "wind_ci_upper": 1})}

GLSAR treats consecutive eligible rows as consecutive days; it bridges {int(ar1['calendar_gaps_bridged'].iloc[0])} calendar gaps in training.
Its nominal tests are exploratory and conditional on the fitted error model; they do not override the
primary HAC/Holm conclusions. The original values are retained. A paired likelihood sensitivity to
actual calendar gaps is reported separately in [the Stage 4 statistical audit](stage4/statistical_audit.md).

## 3. Logistic regression for smog days

Outcome: daily PM2.5 ≥ {logistic['threshold']:.1f} µg/m³ (training {100 * config.extreme_training_quantile:g}th percentile); predictors as M2.
{logistic['training_smog_days']} training smog days; McFadden pseudo-R² {logistic['pseudo_r2']:.3f}.
Cutoff chosen to maximise F1 on **validation**: {logistic['cutoff']:.3f}, then applied unchanged to test.

{_table(tuned, ["split", "n", "smog_days", "auc", "true_positive", "false_positive", "false_negative", "recall", "precision"],
        ["Split", "Days", "Smog days", "AUC", "Caught", "False alarms", "Missed", "Recall", "Precision"],
        {"auc": 3, "recall": 2, "precision": 2})}

With the default 0.5 cutoff the model flags {int(fixed.loc[fixed['split'].eq('test'), 'true_positive'].iloc[0])} of {int(fixed.loc[fixed['split'].eq('test'), 'smog_days'].iloc[0])} test smog days.

{_table(odds, ["term", "odds_ratio", "odds_ratio_ci_lower", "odds_ratio_ci_upper", "p_value_assuming_independence"],
        ["Term", "Odds ratio", "CI low", "CI high", "p (assumes independence)"], {"odds_ratio": 3, "odds_ratio_ci_lower": 3, "odds_ratio_ci_upper": 3})}

Odds ratios are per 1 unit of the centred predictor (°C, m/s, mm, hPa) or versus winter. Their usual
intervals and p-values assume independent days; residual dependence in the core models motivates
caution about that assumption here. These are exploratory associations. The high-day definition is
a training-sample quantile, not a health-based regulatory threshold.

## 4. Do the Stage 2 findings hold at the other 11 stations?

Same Stage 1 rules and Stage 2 models, fitted on each station's own training days.

{_table(stations, ["station", "n_train", "m3_r2", "m2_wind_coefficient", "m2_wind_hac_ci_lower", "m2_wind_hac_ci_upper", "h1_holm_p", "h2_holm_p", "test_m3_mae", "test_baseline_mae"],
        ["Station", "Train days", "M3 R²", "M2 wind coef.", "CI low", "CI high", "H1 Holm p", "H2 Holm p", "Test MAE M3", "Test MAE baseline"],
        {"m2_wind_coefficient": 1, "m2_wind_hac_ci_lower": 1, "m2_wind_hac_ci_upper": 1, "test_m3_mae": 1, "test_baseline_mae": 1})}

- Wind interval below zero at every station: **{'yes' if wind_all_negative else 'no'}**.
- H1 (season) significant after Holm at {h1_sig} of {len(stations)} stations; H2 (wind × season) at {h2_sig} of {len(stations)}.
- M3 beats the training-mean baseline on test MAE at {beats} of {len(stations)} stations.

The 12 stations share one city's air, so agreement shows cross-station consistency, not independent
scientific replication. Holm correction covers two hypotheses within each station, not all 24 tests
across stations. These comparisons are exploratory and use station-specific eligible samples.

## 5. Cluster analysis of stations

Ward hierarchical clustering on z-scored training-period means of {', '.join(config.cluster_variables)}.
k chosen as the largest gap in merge heights for k in {config.cluster_k_range[0]}–{config.cluster_k_range[1]}: **k = {clusters['k']}**.
Cluster numbers are ordered by training mean PM2.5 (1 = lower mean PM2.5).

{_table(assignments, ["station", "cluster", "pm25", "pm10", "so2", "no2", "co", "o3"],
        ["Station", "Cluster", "PM2.5", "PM10", "SO2", "NO2", "CO", "O3"],
        {"pm25": 1, "pm10": 1, "so2": 1, "no2": 1, "co": 0, "o3": 1})}

{_table(clusters['gaps'], ["k", "merge_height_gap", "chosen"], ["k", "Merge-height gap", "Chosen"], {"merge_height_gap": 3})}

Units: µg/m³. Profiles average each pollutant's qualified training daily means; available days can
differ by pollutant. With 12 stations, the groups are descriptive. No geographical or causal separation
is established by clustering pollutant profiles alone.

## What this adds and what it cannot fix

- Adding the previous day's PM2.5 is the largest single improvement: day-to-day persistence is what the
  weather-only model misses most. It turns the model into a same-day explanation that uses yesterday's
  measurement, which is still not a forecast of tomorrow.
- The log models produced no negative estimates in these runs and reduced high-day underestimation;
  their response scale and information set differ from the core regression.
- None of this can make the results causal, recover missing drivers (emissions, regional transport,
  mixing height), or provide a fresh confirmatory test year: that would need data after February 2017.

Figures: `results/stage3/figures/`. Tables: `results/stage3/tables/`. Run record: `results/stage3/run.json`.
"""


def run_stage3(root: Path, config_path: Path | None = None):
    root = root.resolve()
    started, started_at = time.monotonic(), utc_now()
    config_path = (config_path or root / "config" / "stage3.json").resolve()
    stage1_path = root / "config" / "stage1.json"
    run_path = root / "results" / "stage3" / "run.json"
    invocation = "python -m beijing_pm25 stage3" + ("" if config_path == root / "config" / "stage3.json"
                                                     else f" --config {config_path}")
    try:
        config = Stage3Config.read(config_path)
        stage1 = Stage1Config.read(stage1_path)
        if config.min_valid_hours != stage1.min_valid_hours:
            raise ValueError("Stage 3 must use Stage 1's completeness rule.")
        archive, provenance = verify_raw(root)
        dailies, members = {}, {}
        for station, member, content in iter_station_csvs(archive):
            data = read_station(station, member, content, stage1)
            dailies[station] = build_station_daily(data, stage1, config.min_valid_hours)
            members[station] = data.audit["member_sha256"]
        if config.primary_station not in dailies:
            raise ValueError(f"Primary station {config.primary_station} is not in the archive.")

        primary = dailies[config.primary_station]
        sample = common_sample(primary)
        stage2_eligible = primary.loc[primary["analysis_eligible"]]
        dropped = len(stage2_eligible) - len(sample)
        counts = sample["split"].value_counts()
        sample_note = (f"Common sample: Stage 2's eligible days that also have dew point, wind direction and the previous "
                       f"calendar day's PM2.5 ({counts.get('train', 0)} training, {counts.get('validation', 0)} validation, "
                       f"{counts.get('test', 0)} test days; {dropped} fewer than Stage 2 in total).")
        comparison = compare_models(sample, config.extreme_training_quantile)
        blocks = added_block_tests(comparison["fitted"], config.primary_hac_lag_days)
        coefficients = coefficient_table(comparison["fitted"], ["M3_met", "M3_lag", "M3_log_lag_met"],
                                         config.primary_hac_lag_days, config.alpha)
        stage2_parts = partitions(stage2_eligible)
        ar1 = ar1_error_tests(stage2_parts["train"], config.alpha)
        logistic = smog_logistic(stage2_parts, config.extreme_training_quantile, config.alpha)
        stations = pd.DataFrame([station_replication(name, daily, config.extreme_training_quantile,
                                                     config.primary_hac_lag_days, config.alpha)
                                 for name, daily in sorted(dailies.items())])
        profiles = pollutant_profiles(dailies, config.cluster_variables)
        clusters = cluster_stations(profiles, config.cluster_variables, config.cluster_k_range)

        tables = root / "results" / "stage3" / "tables"
        outputs = [
            _write_csv(tables / "model_comparison_scores.csv", comparison["scores"]),
            _write_csv(tables / "model_comparison_fits.csv", comparison["summary"]),
            _write_csv(tables / "model_comparison_predictions.csv", comparison["predictions"]),
            _write_csv(tables / "added_block_tests.csv", blocks),
            _write_csv(tables / "extension_coefficients.csv", coefficients),
            _write_csv(tables / "ar1_error_tests.csv", ar1),
            _write_csv(tables / "smog_logistic_performance.csv", logistic["performance"]),
            _write_csv(tables / "smog_logistic_odds_ratios.csv", logistic["odds"]),
            _write_csv(tables / "smog_logistic_daily.csv", logistic["daily"]),
            _write_csv(tables / "station_replication.csv", stations),
            _write_csv(tables / "station_clusters.csv", clusters["assignments"]),
            _write_csv(tables / "station_cluster_gaps.csv", clusters["gaps"]),
        ]
        outputs += _figures(root, comparison, stations, clusters, logistic)
        report = root / "reports" / "stage3_extensions.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(_report(config, comparison, blocks, coefficients, ar1, logistic, stations,
                                  clusters, sample_note, invocation), encoding="utf-8")
        outputs.append(report)

        inputs = {str(config_path.relative_to(root)): sha256_file(config_path),
                  str(stage1_path.relative_to(root)): sha256_file(stage1_path)}
        for name in ("pyproject.toml", "requirements.lock"):
            if (root / name).is_file():
                inputs[name] = sha256_file(root / name)
        environment = {"python": platform.python_version(), "platform": platform.platform()}
        for package in ("numpy", "pandas", "scipy", "statsmodels", "matplotlib", "pytest"):
            try:
                environment[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                environment[package] = "not installed"
        manifest = {
            "status": "complete", "stage": 3, "exploratory": True, "package_version": __version__,
            "started_at_utc": started_at, "completed_at_utc": utc_now(),
            "elapsed_seconds": round(time.monotonic() - started, 3), "invocation": invocation,
            "configuration": config.as_dict(), "station_member_sha256": members,
            "source_code_sha256": {path.name: sha256_file(path) for path in sorted(Path(__file__).parent.glob("*.py"))},
            "input_sha256": inputs, "environment": environment,
            "primary_station": config.primary_station, "selected_by_validation_mae": comparison["chosen"],
            "test_year_previously_scored_in_stage2": True,
            "output_sha256": {str(path.relative_to(root)): sha256_file(path) for path in outputs},
        }
        write_json(run_path, _json_safe(manifest))
        return {"status": "complete", "exploratory": True, "primary_station": config.primary_station,
                "selected_by_validation_mae": comparison["chosen"], "stations": len(dailies),
                "clusters": clusters["k"], "generated_artifacts": len(outputs), "report": str(report)}
    except BaseException as exc:
        write_json(run_path, {"status": "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                              "stage": 3, "started_at_utc": started_at, "finished_at_utc": utc_now(),
                              "error": f"{type(exc).__name__}: {exc}"})
        raise


def verify_stage3(root: Path):
    root = root.resolve()
    path = root / "results" / "stage3" / "run.json"
    if not path.is_file():
        raise ValueError("No Stage 3 run found. Run: python -m beijing_pm25 stage3")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError(f"Stage 3 is not complete: {manifest.get('status')}")
    archive, _ = verify_raw(root)
    members = {station: hashlib.sha256(content).hexdigest()
               for station, _, content in iter_station_csvs(archive)}
    if members != manifest["station_member_sha256"]:
        raise ValueError("The station CSVs in the raw archive differ from those Stage 3 used.")
    for group in ("input_sha256", "output_sha256"):
        for relative, expected in manifest[group].items():
            target = _project_file(root, relative)
            if not target.is_file() or sha256_file(target) != expected:
                raise ValueError(f"Changed or missing Stage 3 {group} file: {relative}")
    current = {p.name: sha256_file(p) for p in sorted(Path(__file__).parent.glob("*.py"))}
    if current != manifest["source_code_sha256"]:
        raise ValueError("Analysis source code changed after the Stage 3 run; rerun Stage 3.")
    return {"status": "verified", "exploratory": True, "stations": len(members),
            "verified_outputs": len(manifest["output_sha256"])}
