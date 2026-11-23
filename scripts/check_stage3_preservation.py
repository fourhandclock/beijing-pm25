"""Compare regenerated Stage 3 tables with the byte-preserved PR #1 artifacts."""

import csv
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def main():
    baseline = json.loads((ROOT/"reports/stage4/baseline_main.json").read_text())
    records = []
    with zipfile.ZipFile(ROOT/"reports/archive/stage3_pr1_original.zip") as archive:
        for name in sorted(archive.namelist()):
            original = archive.read(name)
            if hashlib.sha256(original).hexdigest() != baseline["artifact_sha256"][name]:
                raise ValueError(f"Original archived artifact differs from PR #1: {name}")
            if not name.endswith(".csv"):
                continue
            old_reader = csv.DictReader(io.StringIO(original.decode()))
            new_reader = csv.DictReader(io.StringIO((ROOT/name).read_text()))
            if old_reader.fieldnames != new_reader.fieldnames:
                raise ValueError(f"Stage 3 table columns changed: {name}")
            old_rows,new_rows = list(old_reader),list(new_reader)
            if len(old_rows) != len(new_rows):
                raise ValueError(f"Stage 3 table row count changed: {name}")
            largest = relative = 0.0
            changed_numeric = changed_labels = 0
            for i,(old,new) in enumerate(zip(old_rows,new_rows)):
                for column,left in old.items():
                    right = new[column]
                    if left == right:
                        continue
                    if (name.endswith("model_comparison_fits.csv") and column=="label"
                            and old["model"]=="M3" and left=="Stage 2 M3 (original scale)"
                            and right=="M3 refit on common sample"):
                        changed_labels += 1
                        continue
                    try:
                        a,b = float(left),float(right)
                    except ValueError as error:
                        raise ValueError(f"Stage 3 nonnumeric value changed: {name}/{i}/{column}") from error
                    if not math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-8):
                        raise ValueError(f"Stage 3 numerical discrepancy: {name}/{i}/{column}: {a} -> {b}")
                    delta = abs(a-b)
                    largest=max(largest,delta)
                    relative=max(relative,delta/max(1,abs(a)))
                    changed_numeric += 1
            records.append({"table":name,"rows":len(old_rows),"max_absolute_difference":largest,
                            "max_difference_scaled_by_max_1_absolute_baseline":relative,
                            "floating_point_cells_differing_in_serialized_text":changed_numeric,
                            "clarified_common_sample_M3_labels":changed_labels})
    result = {"status":"passed","baseline_main_commit":baseline["baseline_main_commit"],
              "original_stage3_artifacts_preserved_byte_for_byte":True,
              "numerical_tolerance":{"rtol":1e-9,"atol":1e-8},"tables":records,
              "interpretation":"Small floating-point/CSV serialization differences are reported explicitly; no Stage 3 numerical method was changed."}
    destination = ROOT/"reports/verification"
    destination.mkdir(parents=True,exist_ok=True)
    (destination/"stage3_preservation.json").write_text(json.dumps(result,indent=2)+"\n")
    print(f"PASS: {len(records)} Stage 3 tables preserved numerically; original artifacts archived exactly.")
    print("Largest absolute table difference:",max(r["max_absolute_difference"] for r in records))


if __name__=="__main__":
    main()
