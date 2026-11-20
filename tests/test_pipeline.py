import json

import pandas as pd
import pytest

from beijing_pm25.acquire import acquire
from beijing_pm25.pipeline import run_stage1, verify_run
from conftest import hourly_rows, write_archive


def test_entire_stage1_offline_and_output_integrity(tmp_path, small_config):
    root = tmp_path / "project"
    config_path = root / "config" / "stage1.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps(small_config.as_dict()))
    archive = write_archive(tmp_path / "fixture.zip", {
        "Alpha": hourly_rows("Alpha"), "Beta": hourly_rows("Beta", offset=1000),
    })
    acquire(root, archive)
    result = run_stage1(root)
    assert result["selected_station"] == "Alpha"
    assert result["models_fitted"] is False
    assert result["retention"]["all"]["analysis_eligible_days"] == 8
    assert result["retention"]["train"]["analysis_eligible_days"] == 4
    daily = pd.read_csv(root / "data" / "processed" / "Alpha_daily.csv")
    assert set(daily["station"]) == {"Alpha"}
    assert daily.iloc[0]["pm25"] == 21.5  # Never averaged together with Beta's much larger values.
    assert len(list((root / "results" / "figures").glob("*.png"))) == 6
    assert len(list((root / "results" / "figures").glob("*.svg"))) == 6
    manifest = json.loads((root / "results" / "stage1_run.json").read_text())
    assert manifest["status"] == "complete"
    assert verify_run(root)["verified_outputs"] == result["generated_artifacts"]
    response = root / "results" / "tables" / "training_response_summary.csv"
    response.write_text(response.read_text() + "changed\n")
    with pytest.raises(ValueError, match="Changed or missing"):
        verify_run(root)
