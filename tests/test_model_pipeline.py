"""Full offline workflow on explicitly synthetic hourly input."""

import json
import pandas as pd
import pytest

from beijing_pm25.acquire import acquire, sha256_file
from beijing_pm25.config import Stage1Config
from beijing_pm25.model_config import Stage2Config
import beijing_pm25.model_pipeline as model_pipeline
from beijing_pm25.models import evaluate_frozen
from beijing_pm25.pipeline import run_stage1, verify_run
from conftest import write_archive
from test_models import synthetic_daily


def make_project(tmp_path):
    daily = synthetic_daily()
    rows = []
    for day, row in daily.iterrows():
        for hour in range(24):
            pm = float(row["pm25"]) if row["analysis_eligible"] else "NA"
            rows.append({
                "No": len(rows) + 1, "year": day.year, "month": day.month,
                "day": day.day, "hour": hour, "PM2.5": pm, "PM10": 60,
                "SO2": 5, "NO2": 20, "CO": 600, "O3": 30,
                "TEMP": row["temperature"], "PRES": row["pressure"],
                "DEWP": row["temperature"] - 8, "RAIN": row["rainfall"] / 24,
                "wd": "N", "WSPM": row["wind_speed"], "station": "Synthetic",
            })
    root = tmp_path / "project"
    (root / "config").mkdir(parents=True)
    (root / "reports").mkdir()
    config = Stage1Config(
        calendar_start=daily.index[0].date().isoformat(),
        train_end_exclusive=daily.index[365].date().isoformat(),
        validation_end_exclusive=daily.index[465].date().isoformat(),
        calendar_end_exclusive=(daily.index[-1] + pd.offsets.Day(1)).date().isoformat(),
        max_acf_lag=3,
    )
    (root / "config" / "stage1.json").write_text(json.dumps(config.as_dict()))
    (root / "config" / "stage2.json").write_text(json.dumps(Stage2Config().as_dict()))
    (root / "reports" / "stage2_protocol.md").write_text("Explicit synthetic fixture; not empirical project results.\n")
    archive = write_archive(tmp_path / "synthetic.zip", {"Synthetic": rows})
    acquire(root, archive)
    run_stage1(root)
    return root


def test_full_workflow_freezes_before_test_and_detects_stale_outputs(tmp_path, monkeypatch):
    root = make_project(tmp_path)
    raw_path = root / "data" / "raw" / "uci_beijing_multi_site.zip"
    raw_hash = sha256_file(raw_path)
    observed = []

    def check_freeze_before_evaluation(test, frozen):
        path = root / "results" / "stage2" / "frozen_model.json"
        persisted = json.loads(path.read_text())
        assert persisted == frozen
        assert "test_performance" not in persisted
        assert persisted["test_used_for_selection"] is False
        observed.append(len(test))
        return evaluate_frozen(test, frozen)

    monkeypatch.setattr(model_pipeline, "evaluate_frozen", check_freeze_before_evaluation)
    result = model_pipeline.run_stage2(root)
    assert observed == [100]
    assert result["n_train"] == 362
    assert result["n_validation"] == result["n_test"] == 100
    assert sha256_file(raw_path) == raw_hash
    assert verify_run(root)["status"] == "verified"
    assert model_pipeline.verify_stage2(root)["status"] == "verified"
    predictions = pd.read_csv(root / "results" / "stage2" / "tables" / "predictions.csv")
    test_predictions = predictions.loc[predictions["split"].eq("test")]
    assert set(test_predictions["model"]) == {result["selected_model"], "training_mean"}
    residuals = pd.read_csv(root / "results" / "stage2" / "tables" / "training_residual_calendar.csv")
    assert len(residuals) == 3 * 365
    assert residuals["residual"].isna().sum() == 9
    assert len(list((root / "results" / "stage2" / "figures").glob("*.png"))) == 9
    frozen_path = root / "results" / "stage2" / "frozen_model.json"
    frozen_path.write_text(frozen_path.read_text() + " ")
    with pytest.raises(ValueError, match="Changed or missing Stage 2"):
        model_pipeline.verify_stage2(root)

    def intentional_failure(test, frozen):
        raise RuntimeError("Synthetic interruption check")

    monkeypatch.setattr(model_pipeline, "evaluate_frozen", intentional_failure)
    with pytest.raises(RuntimeError, match="Synthetic interruption"):
        model_pipeline.run_stage2(root)
    manifest = json.loads((root / "results" / "stage2" / "run.json").read_text())
    assert manifest["status"] == "failed"
    with pytest.raises(ValueError, match="Stage 2 is not complete"):
        model_pipeline.verify_stage2(root)


def test_protocol_required_before_stage2(tmp_path):
    with pytest.raises(ValueError, match="Record the analysis protocol"):
        model_pipeline.run_stage2(tmp_path)
