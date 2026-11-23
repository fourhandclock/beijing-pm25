"""Inspect the PR #1 merge's recorded hashes against that exact Git tree.

This is a read-only Git audit. Missing ignored processed data in a fresh clone
are expected and are distinguished from stale hashes of committed files.
"""

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def main():
    baseline = json.loads((ROOT / "reports/stage4/baseline_main.json").read_text())
    commit = baseline["baseline_main_commit"]

    def git_bytes(path):
        return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT,
                                       stderr=subprocess.DEVNULL, timeout=15)

    tree = set(subprocess.check_output(["git", "ls-tree", "-r", "--name-only", commit],
                                      cwd=ROOT, text=True, timeout=15).splitlines())
    sources = {p for p in tree if p.startswith("src/beijing_pm25/") and p.endswith(".py")}
    records = []
    for name in ("results/stage1_run.json", "results/stage2/run.json", "results/stage3/run.json"):
        record = json.loads(git_bytes(name))
        stale, untracked_outputs = [], []
        for section in ("input_sha256", "source_code_sha256", "output_sha256"):
            for path, expected in record.get(section, {}).items():
                if section == "source_code_sha256":
                    path = "src/beijing_pm25/" + path
                if path not in tree:
                    untracked_outputs.append({"section": section, "path": path})
                else:
                    actual = hashlib.sha256(git_bytes(path)).hexdigest()
                    if actual != expected:
                        stale.append({"section": section, "path": path,
                                      "recorded_sha256": expected, "tree_sha256": actual})
        records.append({"manifest": name, "stale_tracked_hashes": stale,
                        "source_files_added_since_record": sorted(sources-{
                            "src/beijing_pm25/"+p for p in record["source_code_sha256"]}),
                        "ignored_generated_files_absent_from_git": untracked_outputs})
    result = {"baseline_commit": commit, "records": records,
              "remedy": "Regenerate Stage 1, then Stage 2, then Stage 3; preserve the original scientific methods and scores."}
    target = ROOT / "reports/stage4/baseline_manifest_audit.json"
    target.write_text(json.dumps(result, indent=2)+"\n")
    for record in records:
        print(record["manifest"], "stale tracked hashes:", len(record["stale_tracked_hashes"]),
              "new source files:", len(record["source_files_added_since_record"]),
              "expected ignored outputs:", len(record["ignored_generated_files_absent_from_git"]))


if __name__ == "__main__":
    main()
