"""Stage 2 orchestration: declare, develop, freeze, then evaluate and report."""

import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np
import pandas as pd

from . import __version__
from .acquire import sha256_file, utc_now, write_json
from .config import Stage1Config
from .data import split_labels
from .model_config import Stage2Config
from .model_diagnostics import model_tables, residual_tables, seasonal_wind_slopes
from .model_figures import make_model_figures
from .model_report import render_report
from .models import WEATHER, develop_models, evaluate_frozen, frozen_specification, score_predictions
from .pipeline import _project_file, verify_run


def _write_csv(path, frame):
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, float_format="%.15g", date_format="%Y-%m-%d")
    return path


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def _load_daily(root, stage1):
    station = stage1["selected_station"]
    path = root / "data" / "processed" / f"{station}_daily.csv"
    daily = pd.read_csv(path, parse_dates=["date"]).set_index("date")
    first = Stage1Config(**stage1["configuration"])
    expected = pd.date_range(first.calendar_start, first.calendar_end_exclusive,
                             inclusive="left", freq="D", name="date")
    if not daily.index.equals(expected) or not daily["station"].eq(station).all():
        raise ValueError("Stage 2 needs the full unchanged, single-station Stage 1 daily calendar.")
    if not daily["split"].equals(split_labels(daily.index, first)):
        raise ValueError("Stored split labels differ from the chronological Stage 1 calendar.")
    if not pd.api.types.is_bool_dtype(daily["analysis_eligible"]) or daily["analysis_eligible"].isna().any():
        raise ValueError("The daily analysis eligibility flag must be complete and boolean.")
    eligible = daily.loc[daily["analysis_eligible"]]
    if not np.isfinite(eligible[["pm25", *WEATHER]].to_numpy()).all():
        raise ValueError("Analysis-eligible daily values must be finite.")
    for split in ("train", "validation", "test"):
        if int(eligible["split"].eq(split).sum()) != stage1["retention"][split]["analysis_eligible_days"]:
            raise ValueError("The Stage 1 sample count differs from the current daily data.")
    return daily, path


def run_stage2(root: Path, config_path: Path | None = None):
    root = root.resolve()
    config_path = (config_path or root / "config" / "stage2.json").resolve()
    if not config_path.is_relative_to(root):
        raise ValueError("Keep the Stage 2 configuration inside the project.")
    protocol = root / "reports" / "stage2_protocol.md"
    if not protocol.is_file():
        raise ValueError("Record the analysis protocol before running Stage 2.")
    config = Stage2Config.read(config_path)
    verify_run(root)
    stage1_path = root / "results" / "stage1_run.json"
    stage1 = json.loads(stage1_path.read_text(encoding="utf-8"))
    daily, daily_path = _load_daily(root, stage1)
    directory = root / "results" / "stage2"
    run_path = directory / "run.json"
    started_at, started = utc_now(), time.monotonic()
    write_json(run_path, {"status": "running", "stage": 2, "started_at_utc": started_at})
    try:
        eligible = daily.loc[daily["analysis_eligible"]]
        training = eligible.loc[eligible["split"].eq("train")]
        validation = eligible.loc[eligible["split"].eq("validation")]
        training_calendar = daily.index[daily["split"].eq("train")]
        print(f"Fitting M1–M3 on {len(training)} identical eligible training dates.", flush=True)
        development = develop_models(training, validation, config)
        summaries, coefficients, classical, robust, covariances = model_tables(development.models, config)
        diagnostics, influences, acf, residual_calendar = residual_tables(
            development.models, training_calendar, config,
        )
        slopes = seasonal_wind_slopes(development.models["M3"],
                                      covariances["M3"][config.primary_hac_lag_days],
                                      config.alpha, config.primary_hac_lag_days)

        frozen = frozen_specification(development, config)
        frozen.update({
            "frozen_at_utc": utc_now(), "station": stage1["selected_station"],
            "protocol_sha256": sha256_file(protocol), "config_sha256": sha256_file(config_path),
            "stage1_run_sha256": sha256_file(stage1_path), "daily_data_sha256": sha256_file(daily_path),
            "validation_first_date": validation.index.min().date().isoformat(),
            "validation_last_date": validation.index.max().date().isoformat(),
            "validation_observations": len(validation),
        })
        frozen_path = directory / "frozen_model.json"
        write_json(frozen_path, frozen)
        print(f"Validation selected {development.selected_model}; coefficients/cutoff saved before final-test evaluation.", flush=True)
        # Read back the persisted frozen specification. Nothing in test outcomes
        # can influence the model, centering, coefficient or cutoff decisions.
        frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
        test = eligible.loc[eligible["split"].eq("test")]
        if test.index.min() <= validation.index.max():
            raise ValueError("Final test dates must follow all validation dates.")
        test_predictions = evaluate_frozen(test, frozen)
        predictions = pd.concat([development.predictions, test_predictions], ignore_index=True)
        metrics = score_predictions(predictions)
        print(f"Evaluated frozen {development.selected_model} and training-mean baseline on {len(test)} test dates.", flush=True)

        tables = directory / "tables"
        correlation = training[["pm25", *WEATHER]].corr().rename_axis("variable").reset_index()
        covariance_rows = []
        for model, by_lag in covariances.items():
            names = list(development.models[model].params.index)
            for lag, covariance in by_lag.items():
                covariance_rows.extend({"model": model, "hac_lag_calendar_days": lag,
                                        "row_term": row_name, "column_term": column_name,
                                        "covariance": float(covariance[row, column])}
                                       for row, row_name in enumerate(names)
                                       for column, column_name in enumerate(names))
        outputs = [frozen_path]
        for name, frame in (
            ("model_fit", summaries), ("coefficients", coefficients),
            ("nested_anova", classical), ("hac_joint_tests", robust),
            ("hac_covariances", pd.DataFrame(covariance_rows)),
            ("residual_diagnostics", diagnostics), ("training_influence", influences),
            ("training_residual_acf", acf), ("training_residual_calendar", residual_calendar),
            ("m3_seasonal_wind_slopes", slopes), ("validation_selection", development.selection),
            ("performance", metrics), ("predictions", predictions),
            ("training_correlations", correlation),
        ):
            outputs.append(_write_csv(tables / f"{name}.csv", frame))
        parameters_path = directory / "model_parameters.json"
        write_json(parameters_path, {
            "response": "original daily PM2.5 in ug/m^3", "training_centers": development.centers,
            "reference_season": "winter", "training_only": True,
            "models": {name: {"columns": list(result.params.index),
                              "coefficients": {term: float(value) for term, value in result.params.items()},
                              "training_n": int(result.nobs)}
                       for name, result in development.models.items()},
        })
        outputs.append(parameters_path)
        outputs.extend(make_model_figures(root, training, development, influences, acf,
                                           residual_calendar, slopes, test_predictions, config))
        report = root / "reports" / "stage2_analysis.md"
        invocation = list(getattr(sys, "orig_argv", sys.argv))
        report.write_text(render_report(stage1["selected_station"], stage1, config, development,
                                        summaries, coefficients, classical, robust, diagnostics,
                                        influences, slopes, metrics, frozen, invocation), encoding="utf-8")
        outputs.append(report)
        inputs = {str(config_path.relative_to(root)): sha256_file(config_path),
                  str(protocol.relative_to(root)): sha256_file(protocol),
                  str(stage1_path.relative_to(root)): sha256_file(stage1_path),
                  str(daily_path.relative_to(root)): sha256_file(daily_path)}
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
            "status": "complete", "stage": 2, "package_version": __version__,
            "started_at_utc": started_at, "completed_at_utc": utc_now(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "invocation": invocation, "configuration": config.as_dict(),
            "source_code_sha256": {path.name: sha256_file(path) for path in sorted(Path(__file__).parent.glob("*.py"))},
            "input_sha256": inputs, "environment": environment,
            "station": stage1["selected_station"], "raw_sha256": stage1["raw_provenance"]["sha256"],
            "selected_model": development.selected_model,
            "n_train": len(training), "n_validation": len(validation), "n_test": len(test),
            "response_scale": "original", "high_pollution_training_cutoff": development.threshold,
            "training_centers": development.centers, "models_fitted": ["M1", "M2", "M3"],
            "final_test_models": [development.selected_model, "training_mean"],
            "test_used_for_selection": False, "refitted_on_validation_or_test": False,
            "final_test_performance": metrics.loc[metrics["split"].eq("test")].to_dict(orient="records"),
            "frozen_model_sha256": sha256_file(frozen_path),
            "output_sha256": {str(path.relative_to(root)): sha256_file(path) for path in outputs},
        }
        write_json(run_path, _json_safe(manifest))
        return {"status": "complete", "station": stage1["selected_station"],
                "selected_model": development.selected_model, "n_train": len(training),
                "n_validation": len(validation), "n_test": len(test),
                "test_overall": _json_safe(metrics.loc[metrics["split"].eq("test") & metrics["subgroup"].eq("all")].to_dict(orient="records")),
                "generated_artifacts": len(outputs), "report": str(report)}
    except BaseException as exc:
        write_json(run_path, {"status": "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                              "stage": 2, "started_at_utc": started_at, "finished_at_utc": utc_now(),
                              "error": f"{type(exc).__name__}: {exc}"})
        raise


def verify_stage2(root: Path):
    root = root.resolve()
    verify_run(root)
    path = root / "results" / "stage2" / "run.json"
    if not path.is_file():
        raise ValueError("No Stage 2 run found. Run Stage 2 after the recorded protocol.")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError(f"Stage 2 is not complete: {manifest.get('status')}")
    for group in ("input_sha256", "output_sha256"):
        for relative, expected in manifest[group].items():
            path = _project_file(root, relative)
            if not path.is_file() or sha256_file(path) != expected:
                raise ValueError(f"Changed or missing Stage 2 {group} file: {relative}")
    current_code = {path.name: sha256_file(path) for path in sorted(Path(__file__).parent.glob("*.py"))}
    if current_code != manifest["source_code_sha256"]:
        raise ValueError("Stage 2 analysis code changed after the run.")
    return {"status": "verified", "station": manifest["station"], "selected_model": manifest["selected_model"],
            "raw_sha256": manifest["raw_sha256"], "verified_outputs": len(manifest["output_sha256"]),
            "test_used_for_selection": manifest["test_used_for_selection"]}
