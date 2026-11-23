"""Guard the original Stage 2 methodology and frozen numerical evaluation."""

import csv
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def compare(actual, expected, location):
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ValueError(f"Changed numerical record keys at {location}")
        for key in expected:
            compare(actual[key], expected[key], location+"/"+key)
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(f"Changed record length at {location}")
        for i, (left, right) in enumerate(zip(actual, expected)):
            compare(left, right, location+f"/{i}")
    elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not math.isclose(float(actual), float(expected), rel_tol=1e-10, abs_tol=1e-10):
            raise ValueError(f"Numerical discrepancy at {location}: {actual!r} versus {expected!r}")
    elif isinstance(expected, str):
        try:
            left, right = float(actual), float(expected)
        except (ValueError, TypeError):
            if actual != expected:
                raise ValueError(f"Changed value at {location}")
        else:
            if not math.isclose(left, right, rel_tol=1e-10, abs_tol=1e-10):
                raise ValueError(f"Numerical discrepancy at {location}")
    elif actual != expected:
        raise ValueError(f"Changed value at {location}")


def main():
    baseline = json.loads((ROOT/"reports/stage4/baseline_main.json").read_text())
    for name, expected in baseline["frozen_method_source_sha256"].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Original Stage 2 method source changed: {name}")
    for name in ("config/stage1.json", "config/stage2.json", "data/raw/provenance.json"):
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != baseline["artifact_sha256"][name]:
            raise ValueError(f"Original Stage 2 input changed: {name}")
    frozen = json.loads((ROOT/"results/stage2/frozen_model.json").read_text())
    expected = baseline["stage2_frozen"]
    semantic = [name for name in expected if name not in {
        "frozen_at_utc", "protocol_sha256", "config_sha256", "stage1_run_sha256", "daily_data_sha256",
    }]
    compare({name: frozen[name] for name in semantic}, {name: expected[name] for name in semantic}, "frozen model")
    archived = ROOT/"reports/archive/stage2_protocol_original_20261119.md"
    if hashlib.sha256(archived.read_bytes()).hexdigest() != expected["protocol_sha256"]:
        raise ValueError("The original dated protocol was not preserved exactly")
    parameters = json.loads((ROOT/"results/stage2/model_parameters.json").read_text())
    compare(parameters, baseline["stage2_parameters"], "all Stage 2 fits")
    for key, name in (("stage2_performance", "performance"), ("stage2_anova", "nested_anova"),
                      ("stage2_hac_tests", "hac_joint_tests")):
        with (ROOT/f"results/stage2/tables/{name}.csv").open(newline="") as handle:
            actual = list(csv.DictReader(handle))
        compare(actual, baseline[key], name)
    result = {"status": "passed", "baseline_main_commit": baseline["baseline_main_commit"],
              "original_method_sources_unchanged": True, "original_inputs_unchanged": True,
              "original_protocol_preserved_exactly": True,
              "frozen_model_selection_coefficients_centering_cutoff_and_scores_preserved": True,
              "allowed_metadata_refresh": ["timestamps", "administrative protocol text", "run/source hash references"],
              "numerical_tolerance": {"rtol": 1e-10, "atol": 1e-10}}
    destination = ROOT/"reports/verification"
    destination.mkdir(parents=True,exist_ok=True)
    (destination/"stage2_preservation.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
