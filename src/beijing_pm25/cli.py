"""Separate acquisition, audit, approved regression stage, and verification."""

import argparse
import json
from pathlib import Path
import sys
import urllib.error
import zipfile

from .acquire import acquire


def parser():
    root = argparse.ArgumentParser(description="Beijing PM2.5: reproducible, staged statistical investigation.")
    commands = root.add_subparsers(dest="command", required=True)
    download = commands.add_parser("download", help="Preserve the original UCI archive and provenance.")
    download.add_argument("--project-root", type=Path, default=Path.cwd())
    download.add_argument("--import-archive", type=Path, help="Use an existing original UCI ZIP offline.")
    download.add_argument("--timeout", type=int, default=30, help="Socket timeout, in seconds (1–120).")
    stage = commands.add_parser("stage1", help="Audit, aggregate, select a station, and report; fit no models.")
    stage.add_argument("--project-root", type=Path, default=Path.cwd())
    stage.add_argument("--config", type=Path, help="Default: <project-root>/config/stage1.json")
    model = commands.add_parser("stage2", help="Fit the approved M1–M3 analysis, freeze, evaluate and report.")
    model.add_argument("--project-root", type=Path, default=Path.cwd())
    model.add_argument("--config", type=Path, help="Default: <project-root>/config/stage2.json")
    extend = commands.add_parser("stage3", help="Exploratory extensions: alternative models, other stations, clustering.")
    extend.add_argument("--project-root", type=Path, default=Path.cwd())
    extend.add_argument("--config", type=Path, help="Default: <project-root>/config/stage3.json")
    verify = commands.add_parser("verify", help="Check the source, configuration, code, and output hashes.")
    verify.add_argument("--project-root", type=Path, default=Path.cwd())
    verify.add_argument("--stage", choices=("1", "2", "3", "all"), default="all")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        root = args.project_root.resolve()
        if args.command == "download":
            path, manifest = acquire(root, args.import_archive, args.timeout)
            print(f"Preserved raw archive: {path}")
            print(f"SHA-256: {manifest['sha256']}")
            print(f"Stations found: {len(manifest['stations'])}")
        elif args.command == "stage1":
            from .pipeline import run_stage1
            result = run_stage1(root, args.config)
            print(json.dumps(result, indent=2, allow_nan=False))
            print("Stage 1 complete. Model fitting requires review of this stage first.")
        elif args.command == "stage2":
            from .model_pipeline import run_stage2
            print(json.dumps(run_stage2(root, args.config), indent=2, allow_nan=False))
        elif args.command == "stage3":
            from .extension_pipeline import run_stage3
            print(json.dumps(run_stage3(root, args.config), indent=2, allow_nan=False))
            print("Stage 3 is exploratory: the test year was already scored in Stage 2.")
        else:
            from .pipeline import verify_run
            results = {}
            if args.stage in ("1", "all"):
                results["stage1"] = verify_run(root)
            if args.stage == "2" or (args.stage == "all" and (root / "results" / "stage2" / "run.json").exists()):
                from .model_pipeline import verify_stage2
                results["stage2"] = verify_stage2(root)
            if args.stage == "3" or (args.stage == "all" and (root / "results" / "stage3" / "run.json").exists()):
                from .extension_pipeline import verify_stage3
                results["stage3"] = verify_stage3(root)
            print(json.dumps(results, indent=2, allow_nan=False))
        return 0
    except KeyboardInterrupt:
        print("Interrupted; raw inputs have not been overwritten.", file=sys.stderr)
        return 130
    except (ValueError, OSError, urllib.error.URLError, zipfile.BadZipFile) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except ModuleNotFoundError as exc:
        print(f"ERROR: {exc}. Install the project: python -m pip install -e '.[dev]'", file=sys.stderr)
        return 1
