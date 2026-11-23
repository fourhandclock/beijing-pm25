"""Reproducible Stage 1 audit and report. Intentionally contains no model fitting."""

import importlib.metadata
import json
from pathlib import Path
import platform
import shlex
import sys
import time

import pandas as pd

from . import __version__
from .acquire import iter_station_csvs, sha256_file, utc_now, verify_raw, write_json
from .config import Stage1Config, UNITS
from .data import aggregate_daily, coverage_rows, rank_stations, read_station, station_audit
from .describe import calendar_acf, response_summary
from .figures import make_figures


def _csv(path, frame, *, index=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=index, float_format="%.12g", date_format="%Y-%m-%d")
    return path


def _number(value):
    return "unavailable" if pd.isna(value) else f"{value:.3f}"


def _markdown_table(columns, rows):
    return "\n".join([
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
        *("| " + " | ".join(str(value) for value in row) + " |" for row in rows),
    ])


def _report(config, selected, ranking, coverage, statistics, acf, provenance, invocation):
    chosen = ranking.loc[ranking["station"].eq(selected)].iloc[0]
    selected_coverage = coverage.loc[coverage["station"].eq(selected)]
    split_table = _markdown_table(
        ["Interval", "Calendar days", "PM2.5-qualified days", "Analysis-eligible days", "Excluded days"],
        selected_coverage[["scope", "calendar_days", "pm25_qualified_days", "analysis_eligible_days", "excluded_days"]].itertuples(index=False, name=None),
    )
    rank_table = _markdown_table(
        ["Rank", "Station", "Eligible training days", "Valid training PM2.5 hours"],
        ranking[["training_completeness_rank", "station", "training_analysis_days", "training_pm25_valid_hours"]].itertuples(index=False, name=None),
    )
    distribution = statistics.loc[
        statistics["subset"].eq("daily_analysis_eligible_training") & statistics["scale"].eq("original")
    ].iloc[0]
    logged = statistics.loc[
        statistics["subset"].eq("daily_analysis_eligible_training") & statistics["scale"].eq("log1p")
    ].iloc[0]
    lag1 = acf.loc[acf["lag_days"].eq(1)].iloc[0]
    n_stations = len(ranking)
    rationale = (
        "Automatic choice: most analysis-eligible **training** days, then most valid training PM2.5 hours, "
        "then alphabetical station name."
        if config.station == "auto" else
        f"Manual override in the configuration (`station = {config.station}`). The training-completeness ranking is still reported."
    )
    warning = "" if n_stations == 12 else (
        f"\n**Coverage warning:** this input contains {n_stations} stations, whereas UCI describes 12. "
        "This run must not be described as an audit of the full original release.\n"
    )
    return f"""# Stage 1 — data audit and baseline infrastructure

Run completed at {utc_now()}. **This stage audits the data and does not fit models.** Regression results are reported separately in [Stage 2](stage2_analysis.md); subsequent extensions are [exploratory](stage3_extensions.md).

## Source and reproducibility

- Source: [UCI Beijing Multi-Site Air Quality]({provenance['source_page']}); [dataset DOI]({provenance['doi']}).
- Citation: {provenance['citation']} License: {provenance['license']}.
- Acquisition: `{provenance['source']['kind']}`, {provenance['retrieved_at_utc']}. {provenance['origin_note']}
- Preserved archive: `data/raw/{provenance['archive_name']}` ({provenance['size_bytes']:,} bytes).
- Archive SHA-256: `{provenance['sha256']}`. No provider release-version string is assumed.
- All {n_stations} original station CSVs were checked; the wrapper's auxiliary `data.csv` and `test.csv` were excluded.
- Per-station member hashes, row counts, missingness, calendar gaps, configuration, code hashes, environment versions, and output hashes are saved in the tables and `results/stage1_run.json`.
{warning}
Exact invocation for this run:

```bash
{shlex.join(invocation)}
```

From the project directory, reproduce with:

```bash
.venv/bin/python -m beijing_pm25 download
.venv/bin/python -m beijing_pm25 stage1
.venv/bin/python -m beijing_pm25 verify
.venv/bin/python -m pytest
```

The download command reuses a preserved archive only after checking its hash. Tests use small explicitly synthetic fixtures, separate from the empirical dataset; test outcomes are recorded in `reports/implementation_checks.md` when that check has been run by the implementer.

## Declared calendar and cleaning decisions

- Complete calendar: `{config.calendar_start}` inclusive to `{config.calendar_end_exclusive}` exclusive, separately for each station.
- Training: start to `{config.train_end_exclusive}` exclusive. Validation: `{config.train_end_exclusive}` to `{config.validation_end_exclusive}` exclusive. Final test: `{config.validation_end_exclusive}` to calendar end exclusive. The two full training years and one year each for validation/test in the default configuration cover all seasons.
- Hour fields are interpreted as local civil time, assumed **Asia/Shanghai**; UCI's displayed metadata do not explicitly tag a timezone. No UTC or daylight-saving conversion is imposed.
- A missing calendar hour remains a missing observation; absent dates remain explicit daily rows. Duplicate station/timestamp rows, mixed station labels, invalid calendar fields, and malformed numeric text are errors, not silently repaired. Unordered input is sorted by calendar alignment and counted.
- Original missing values remain missing. Nonfinite measurements, negative pollutant concentrations/rainfall/wind speed, nonpositive pressure, and unrecognized wind directions are masked and counted. Negative temperatures are valid. High positive concentrations are retained. No imputation or clipping is performed.
- PM2.5, temperature, pressure, and wind speed use arithmetic means of their own valid hourly values, with **at least {config.min_valid_hours}/24** valid hours each.
- Rainfall is the sum of **all 24 valid hourly precipitation entries**. A partial total, including an all-missing total, remains missing. This assumes the hourly precipitation entries are interval amounts; sensor semantics are not independently validated.
- An analysis day also needs at least **{config.min_valid_hours} hours with all five core fields observed together**. Variable-specific means can still use different subsets; the overlap count is retained. Every exclusion reason is saved; reason counts overlap and must not be added together.
- Seasons are fixed meteorological seasons: DJF/MAM/JJA/SON. No seasonal boundaries were tuned.

## Station choice and retention

**Selected primary station: {selected}.** {rationale} Validation/test coverage and concentration levels do not enter the choice. The rule was declared in `config/stage1.json` and the implementation before the first empirical run.

{rank_table}

For {selected}, there are {int(chosen['source_hourly_rows']):,} source hourly rows of {int(chosen['expected_hourly_rows']):,} expected slots, {int(chosen['missing_hour_rows']):,} absent hourly rows, and no duplicate timestamps. {int(chosen['invalid_values_masked']):,} invalid measurement cells were masked. See `hourly_missingness.csv` for missing-value counts by variable and interval.

{split_table}

`data/processed/{selected}_daily.csv` retains the entire calendar with counts, split labels, eligibility flags and exclusion reasons. `{selected}_analysis_ready.csv` contains only the eligible days and carries the same metadata. It supplies a common sample for the nested comparisons; retention alone is not evidence that OLS assumptions hold.

## Training response and time structure

Among {int(distribution['n']):,} eligible training days, daily PM2.5 has mean {_number(distribution['mean'])}, median {_number(distribution['q50'])}, standard deviation {_number(distribution['std'])}, minimum {_number(distribution['min'])}, maximum {_number(distribution['max'])}, and skewness {_number(distribution['skewness'])} on the original µg/m³ scale. Log1p skewness is {_number(logged['skewness'])}; this is a descriptive comparison, **not a finalized model response transformation**.

Lag-one response correlation is {_number(lag1['correlation'])}, based on {int(lag1['paired_days'])} paired calendar days. The ACF uses qualified training daily responses, preserving missing calendar dates. It is descriptive: this stage computes no residuals, independence p-value or white-noise confidence bands. Daily aggregation does not establish independent errors.

All six figures use training observations or training completeness only. Each is saved as PNG and editable/exportable SVG in `results/figures/`:

1. `station_training_completeness`: transparent selection ranking.
2. `hourly_training_missingness`: unusable core-field percentages at each station.
3. `training_daily_series`: qualified daily response and valid-hour counts.
4. `training_response_distribution`: original and log1p daily response distributions.
5. `training_seasonal_distribution`: within-training seasonal response distributions; extremes retained.
6. `training_calendar_acf`: response correlation at calendar-day lags, with gaps retained.

The full-archive missingness audit is descriptive. Validation/test target distributions are not plotted or used for station/response decisions. No imputation, scaling, model selection, extreme-day cutoff, or adaptive smoothing parameter has been learned from those intervals.

## Interpretation limits and implications for regression

- This is one station in a historical observational dataset. Missingness may be informative; completeness filtering can change seasonal composition. Other stations and years need separate assessment.
- Meteorology in UCI is matched from nearby weather stations. These associations cannot establish causal pollution effects or identify an emissions source.
- Same-day observed weather and daily target means support a contemporaneous explanatory study. They do not establish a deployable advance forecast.
- Response-scale decisions must precede fitting on a common sample. Marginal response skewness alone does not require log1p or diagnose conditional regression errors.
- Residual dependence, heteroscedasticity and influence require checks after fitting. Classical partial F-tests and HAC joint Wald tests have different assumptions and reference distributions.
- Reproduction instructions and current document checks are documented in [reproducibility](reproducibility.md) and [editorial verification](stage5_refinement.md).

This report supplies the data-quality evidence for the regression study. It makes no claim of model adequacy or estimation performance.
"""


def run_stage1(project_root: Path, config_path: Path | None = None):
    project_root = project_root.resolve()
    config_path = (config_path or project_root / "config" / "stage1.json").resolve()
    try:
        config_relative = str(config_path.relative_to(project_root))
    except ValueError as exc:
        raise ValueError("Keep the configuration file inside the project for reproducibility.") from exc
    config = Stage1Config.read(config_path)
    archive, provenance = verify_raw(project_root)
    started = time.monotonic()
    started_at = utc_now()
    run_path = project_root / "results" / "stage1_run.json"
    # Never leave a previous run marked 'complete' while replacing its outputs.
    write_json(run_path, {"status": "running", "started_at_utc": started_at})

    try:
        audits, missingness_rows, coverage, gap_rows = [], [], [], []
        daily_by_station = {}
        training_hourly_by_station = {}
        for station, member, content in iter_station_csvs(archive):
            data = read_station(station, member, content, config)
            daily = aggregate_daily(data, config)
            audits.append(station_audit(data, daily))
            missingness_rows.extend(data.missingness)
            coverage.extend(coverage_rows(daily, station))
            gap_rows.extend(data.gaps)
            daily_by_station[station] = daily
            training_hourly_by_station[station] = data.hourly.loc[
                data.hourly["split"].eq("train"), "PM2.5"
            ].copy()
            print(f"Audited {station}: {audits[-1]['training_analysis_days']} eligible training days", flush=True)

        ranking = rank_stations(audits)
        selected = str(ranking.iloc[0]["station"]) if config.station == "auto" else config.station
        if selected not in daily_by_station:
            raise ValueError(f"Requested station {selected!r} is not present in this archive.")
        daily = daily_by_station[selected]
        training = daily.loc[daily["split"].eq("train")]
        if int(training["analysis_eligible"].sum()) < 3:
            raise ValueError("Selected station has fewer than three eligible training days; inspect the input/configuration.")
        missingness = pd.DataFrame(missingness_rows)
        coverage = pd.DataFrame(coverage)
        gaps = pd.DataFrame(gap_rows, columns=["station", "start_hour", "end_hour_inclusive", "missing_hours"])
        statistics = response_summary(training_hourly_by_station[selected], training)
        acf = calendar_acf(training["pm25"], config.max_acf_lag)

        tables = project_root / "results" / "tables"
        outputs = [
            _csv(tables / "station_audit.csv", ranking),
            _csv(tables / "hourly_missingness.csv", missingness),
            _csv(tables / "daily_completeness.csv", coverage),
            _csv(tables / "timestamp_gaps.csv", gaps),
            _csv(tables / "training_response_summary.csv", statistics),
            _csv(tables / "training_calendar_acf.csv", acf),
            _csv(project_root / "data" / "processed" / f"{selected}_daily.csv", daily, index=True),
            _csv(project_root / "data" / "processed" / f"{selected}_analysis_ready.csv",
                 daily.loc[daily["analysis_eligible"]], index=True),
        ]
        outputs.extend(make_figures(project_root, daily, ranking, missingness, acf, config))
        report = project_root / "reports" / "stage1_summary.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        invocation = list(getattr(sys, "orig_argv", sys.argv))
        report.write_text(_report(config, selected, ranking, coverage, statistics, acf,
                                  provenance, invocation), encoding="utf-8")
        outputs.append(report)

        inputs = {config_relative: sha256_file(config_path)}
        for name in ("pyproject.toml", "requirements.lock", "AGENTS.md", "PROJECT_BRIEF.md"):
            path = project_root / name
            if path.is_file():
                inputs[name] = sha256_file(path)
        selected_retention = coverage.loc[coverage["station"].eq(selected)].set_index("scope")
        environment = {"python": platform.python_version(), "platform": platform.platform()}
        for package in ("numpy", "pandas", "matplotlib", "pytest"):
            try:
                environment[package] = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                environment[package] = "not installed"
        manifest = {
            "status": "complete", "stage": 1, "package_version": __version__,
            "started_at_utc": started_at, "completed_at_utc": utc_now(),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "invocation": invocation, "configuration": config.as_dict(),
            "config_path": config_relative, "input_sha256": inputs,
            "source_code_sha256": {path.name: sha256_file(path) for path in sorted(Path(__file__).parent.glob("*.py"))},
            "raw_provenance": provenance, "environment": environment,
            "selected_station": selected,
            "selection_rule": "training eligible days DESC, training valid PM2.5 hours DESC, station ASC",
            "selection_mode": "automatic" if config.station == "auto" else "manual override",
            "stations_audited": len(ranking), "units": UNITS,
            "time_assumption": "Asia/Shanghai local civil time; no conversion; source metadata do not specify timezone",
            "rainfall_rule": "Sum 24 valid hourly interval amounts; partial daily sums are missing",
            "joint_hours_minimum": config.min_valid_hours,
            "retention": {
                scope: {key: int(row[key]) for key in (
                    "calendar_days", "pm25_qualified_days", "analysis_eligible_days", "excluded_days",
                )} for scope, row in selected_retention.iterrows()
            },
            "output_sha256": {str(path.relative_to(project_root)): sha256_file(path) for path in outputs},
            "models_fitted": False,
        }
        write_json(run_path, manifest)
        return {"selected_station": selected, "stations_audited": len(ranking),
                "retention": manifest["retention"], "report": str(report),
                "generated_artifacts": len(outputs), "models_fitted": False}
    except BaseException as exc:
        write_json(run_path, {"status": "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                              "started_at_utc": started_at, "finished_at_utc": utc_now(),
                              "error": f"{type(exc).__name__}: {exc}"})
        raise


def _project_file(project_root, relative):
    path = (project_root / relative).resolve()
    if not path.is_relative_to(project_root.resolve()):
        raise ValueError("Run manifest contains a path outside the project.")
    return path


def verify_run(project_root: Path):
    _, provenance = verify_raw(project_root)
    run_path = project_root / "results" / "stage1_run.json"
    if not run_path.is_file():
        raise ValueError("No Stage 1 run manifest found. Run Stage 1 first.")
    manifest = json.loads(run_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError(f"Stage 1 is not complete: {manifest.get('status')}")
    if manifest["raw_provenance"] != provenance:
        raise ValueError("Source provenance changed since this run.")
    for group in ("input_sha256", "output_sha256"):
        for relative, expected in manifest[group].items():
            path = _project_file(project_root, relative)
            if not path.is_file() or sha256_file(path) != expected:
                raise ValueError(f"Changed or missing {group} file: {relative}. Rerun Stage 1 to refresh derived outputs.")
    current_code = {path.name: sha256_file(path) for path in sorted(Path(__file__).parent.glob("*.py"))}
    if current_code != manifest["source_code_sha256"]:
        raise ValueError("Analysis source code changed after this run; rerun Stage 1.")
    return {"status": "verified", "raw_sha256": provenance["sha256"],
            "selected_station": manifest["selected_station"],
            "verified_outputs": len(manifest["output_sha256"]), "models_fitted": manifest["models_fitted"]}
