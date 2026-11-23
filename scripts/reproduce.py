"""Run the declared analysis and verification in order, stopping on any failure."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def run(label, command, directory, records, timeout=600):
    start = time.monotonic()
    record = {"label":label,"command":command,"shell_display":shlex.join(command),
              "cwd":"repository root","started_at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "timeout_seconds":timeout,"log":label+".log"}
    print(f"[{label}] {record['shell_display']}",flush=True)
    with (directory/record["log"]).open("w") as output:
        process = subprocess.Popen(command,cwd=ROOT,stdout=output,stderr=subprocess.STDOUT)
        try:
            code = process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired,KeyboardInterrupt) as error:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            code = 124 if isinstance(error,subprocess.TimeoutExpired) else 130
    record.update(exit_code=code,elapsed_seconds=round(time.monotonic()-start,3))
    records.append(record)
    (directory/"commands.json").write_text(json.dumps(records,indent=2)+"\n")
    if code:
        print((directory/record["log"]).read_text()[-6000:],file=sys.stderr)
        raise SystemExit(f"{label} failed (exit {code}); see {directory/record['log']}")
    print(f"[{label}] PASS ({record['elapsed_seconds']:.2f}s)",flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-submission",action="store_true",help="Also rebuild/check PDF and PowerPoint materials (optional dependencies required)")
    parser.add_argument("--log-dir",type=Path,default=Path("reports/reproduction"))
    args = parser.parse_args()
    directory = args.log_dir if args.log_dir.is_absolute() else ROOT/args.log_dir
    directory.mkdir(parents=True,exist_ok=True)
    # Preserve relative invocations in stage manifests when using the documented environment.
    executable = ".venv/bin/python" if ROOT/".venv/bin/python"==Path(sys.executable).absolute() else sys.executable
    python = [executable,"-W","error"]
    tasks = [("download",[executable,"-m","beijing_pm25","download"]),
             *[("stage"+str(stage),python+["-m","beijing_pm25","stage"+str(stage)]) for stage in (1,2,3)],
             ("pytest",python+["-m","pytest","-q"]),
             ("aggregation-oracle",[executable,"scripts/verify_aggregation.py"]),
             ("model-oracle",python+["scripts/verify_models.py"]),
             ("extension-oracle",python+["scripts/verify_extensions.py"]),
             ("ar1-calendar",python+["scripts/audit_ar1_calendar.py"]),
             ("frozen-stage2",[executable,"scripts/check_frozen_stage2.py"]),
             ("preserved-stage3",[executable,"scripts/check_stage3_preservation.py"])]
    if args.with_submission:
        tasks += [("build-submission",python+["scripts/build_submission.py"]),
                  ("check-submission",python+["scripts/check_submission.py"])]
    tasks += [("verify",[executable,"-m","beijing_pm25","verify"]),
              ("pip-check",[executable,"-m","pip","check"])]
    records=[]
    for label,command in tasks:
        run(label,command,directory,records)
    print(f"All {len(records)} reproduction steps passed. Commands and logs: {directory}")


if __name__=="__main__":
    main()
