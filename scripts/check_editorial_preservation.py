"""Prove that the editorial revision preserves the completed Stage 4 science."""

import ast
import hashlib
import json
from pathlib import Path
import re
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function_ast(source, name):
    return ast.dump(next(node for node in ast.parse(source).body
                         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name==name),
                    include_attributes=False)


def verification_prefix(source):
    """Comparison logic before constructing/writing the human-readable result."""
    body=next(node.body for node in ast.parse(source).body
              if isinstance(node,ast.FunctionDef) and node.name=="main")
    result=[]
    for node in body:
        if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=="result"
                                              for target in node.targets):
            break
        result.append(node)
    return ast.dump(ast.Module(body=result,type_ignores=[]),include_attributes=False)


def main():
    folder = ROOT/"reports/stage5"
    baseline = json.loads((folder/"baseline.json").read_text())
    archive = ROOT/baseline["archive"]
    if digest(archive) != baseline["archive_sha256"]:
        raise ValueError("The pre-editorial archive was modified")
    for path,expected in baseline["scientific_file_sha256"].items():
        if digest(ROOT/path) != expected:
            raise ValueError(f"Scientific input, method, table or verified figure changed: {path}")
    historical = []
    with zipfile.ZipFile(archive) as original:
        for path,expected in baseline["file_sha256"].items():
            if hashlib.sha256(original.read(path)).hexdigest() != expected:
                raise ValueError(f"Archived Stage 4 evidence differs: {path}")
            if (path.startswith("reports/archive/") or path.startswith("reports/stage4/") and
                    (path.endswith(".json") or "/evidence/" in path or "/reproduction/" in path)):
                if digest(ROOT/path) != expected:
                    raise ValueError(f"Historical experiment evidence changed: {path}")
                historical.append(path)
        old_frozen = json.loads(original.read("results/stage2/frozen_model.json"))
        frozen = json.loads((ROOT/"results/stage2/frozen_model.json").read_text())
        administrative = {"frozen_at_utc","protocol_sha256","stage1_run_sha256"}
        if {k:v for k,v in frozen.items() if k not in administrative} != {
                k:v for k,v in old_frozen.items() if k not in administrative}:
            raise ValueError("A frozen evaluation value changed beyond permitted metadata refresh")
        builder = (ROOT/"scripts/build_submission.py").read_text()
        old_builder = original.read("scripts/build_submission.py").decode()
        for name in ("number","score","logit","figures"):
            if function_ast(builder,name) != function_ast(old_builder,name):
                raise ValueError(f"Numerical lookup or scientific figure code changed: {name}")
        for name in ("scripts/verify_extensions.py","scripts/audit_ar1_calendar.py"):
            current=(ROOT/name).read_text().replace('"reports/verification"','"reports/stage4"')
            if ast.dump(ast.parse(current),include_attributes=False) != ast.dump(
                    ast.parse(original.read(name).decode()),include_attributes=False):
                raise ValueError(f"Numerical oracle changed beyond its JSON destination: {name}")
        for name in ("scripts/check_frozen_stage2.py","scripts/check_stage3_preservation.py"):
            if verification_prefix((ROOT/name).read_text()) != verification_prefix(original.read(name).decode()):
                raise ValueError(f"Result-preservation testing rules changed: {name}")
        if function_ast((ROOT/"src/beijing_pm25/pipeline.py").read_text(),"run_stage1") != function_ast(
                original.read("src/beijing_pm25/pipeline.py").decode(),"run_stage1"):
            raise ValueError("Stage 1 execution/selection/preprocessing changed")
        old_claims = json.loads(original.read("submission/build_manifest.json"))["numerical_claims"]
    claims = json.loads((ROOT/"submission/build_manifest.json").read_text())["numerical_claims"]
    def key(claim):
        return json.dumps([claim["source"],claim["column"],claim["where"],claim["format"]],sort_keys=True)
    current = {key(claim):claim for claim in claims}
    shared = 0
    for claim in old_claims:
        if key(claim) in current:
            if current[key(claim)] != claim:
                raise ValueError(f"A retained numerical claim changed: {claim}")
            shared += 1
    expected_figures = {name for name in baseline["scientific_file_sha256"] if name.startswith("submission/figures/")}
    actual_figures = {str(path.relative_to(ROOT)) for path in (ROOT/"submission/figures").glob("*.png")}
    if actual_figures != expected_figures:
        raise ValueError("The document revision introduced or removed a scientific figure")
    text=(ROOT/"README.md").read_text()
    words=len(re.sub(r"```[\s\S]*?```","",text).split())
    if not 500<=words<=800:
        raise ValueError(f"README outside the requested length: {words} words")
    result={"status":"passed","scientific_files_unchanged_exactly":len(baseline["scientific_file_sha256"]),
            "archived_pre_edit_files_verified":len(baseline["file_sha256"]),
            "historical_records_unchanged_exactly":len(historical),
            "frozen_values_unchanged_exactly":True,"only_frozen_metadata_refreshed":sorted(administrative),
            "numerical_lookup_and_figure_functions_unchanged":True,"stage1_execution_unchanged":True,
            "verification_calculations_and_preservation_rules_unchanged":True,
            "existing_figures_retained_without_byte_changes":len(expected_figures),
            "shared_numerical_claims_unchanged_exactly":shared,
            "readme_words_excluding_fenced_code":{"before":baseline["readme_words_excluding_fenced_code"],"after":words},
            "archive_sha256":baseline["archive_sha256"]}
    (folder/"preservation_check.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
