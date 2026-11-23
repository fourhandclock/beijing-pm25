# Stage 5 — Research presentation and documentation refinement

**Complete.** This is an editorial revision of the completed investigation. The
original confirmatory methods, fitted values, preprocessing, testing rules and
frozen evaluation are unchanged. Work is on `stage5-research-presentation`;
no commit, push or merge was performed.

## Editorial changes

The [README](../README.md) is now a research landing page: a short abstract,
a research question, three principal findings, a brief method description and
an existing residual-correlation visualization precede the deliverable links
and reproduction commands. Its length fell from **1,486 to 632 words**, excluding
fenced command snippets. Technical acquisition, provenance, individual-command
and stale-record details are in [the reproduction guide](reproducibility.md),
with cleaning and inference details linked to their existing reports.

The [report](../submission/report.pdf) remains **10 pages**. Extracted PDF text
fell from **2,825 to 2,317 words**; these counts include captions, tables and
footers, but exclude text inside raster figures. Body type increased from 9.5
to 10.1 points. Paragraphs now introduce and interpret the tables and figures.
Repeated qualifications were consolidated into the relevant methods and
limitations sections. The narrative centers on multiple regression, ANOVA,
HAC/Holm inference, residual dependence and the frozen test evaluation.
Supporting analyses remain explicitly exploratory. Equations, units, original
statistics and the distinction between original and common-sample M3 are retained.

The [presentation PDF](../submission/slides.pdf) and
[PowerPoint](../submission/slides.pptx) retain **16 slides**, with shorter
[speaker notes](../submission/speaker_notes.md). Extractable slide text fell
from **1,005 to 798 words**. Thirteen content-appropriate layouts replace a
repeated full-width takeaway banner on every slide. Diagnostic figures have
more space; the existing classification table is displayed as a readable
confusion matrix, and the clustering slide uses the **existing verified
pollutant-profile heatmap**. No new scientific figure or result was introduced.

Scheduling metadata were removed from the README, current brief, active
reporting text, title pages, footers, slide metadata and generator templates.
Original experiment timestamps, collection dates, archived protocols and
historical evidence remain intact. Neutral author pages and a concise,
transparent AI-assistance disclosure are retained.

## README structure before and after

| Before | After, in reading order |
| --- | --- |
| Status, administrative information and submission links | Project title and short research abstract |
| Several paragraphs covering nearly every analysis | Research question and confirmatory/exploratory distinction |
| Main findings mixed with supplementary results | Exactly three principal findings focused on regression adequacy |
| Extensive cleaning/configuration detail | Brief methodology and substantive limitations |
| No selected figure | Existing M3 residual-correlation figure with interpretation |
| Detailed output inventories | Report, slides and focused documentation links |
| Multiple command lists and acquisition details | Short reproduction instructions; detailed guide linked |
| Separate limitations and workflow disclosure | References, data attribution and concise AI disclosure |

## Preservation and historical evidence

Stage 4 was still uncommitted when this work began. Its **219 nonignored files**
were preserved byte for byte in
[stage4_before_editorial_refinement.zip](archive/stage4_before_editorial_refinement.zip)
before editing. [The baseline manifest](stage5/baseline.json) records the original
file hashes and separately guards scientific inputs, methods and artifacts.
The original prefit protocol and original PR #1 artifacts were not rewritten.

The [editorial preservation check](stage5/preservation_check.json) confirms:

- **66 scientific files match exactly**, including raw/processed data,
  configurations, numerical model modules, all analysis CSV tables, all-model
  parameters and the seven submission figures.
- **88 retained source-linked numerical claims match exactly**. All seven
  scientific PNG files and their generation functions are unchanged.
- **71 historical records match exactly**, including the archived protocols and
  Stage 4 JSON/log evidence. All 219 files inside the pre-edit archive match
  their recorded hashes.
- Frozen Stage 2 values are exactly equal after excluding only refreshed
  `frozen_at_utc`, `protocol_sha256` and `stage1_run_sha256` metadata. Those fields
  describe this actual regeneration; earlier records remain in the archive.
- Stage 1 execution/selection/preprocessing and the numerical verification
  calculations are unchanged. The extension/AR audit scripts changed only their
  JSON destinations; preservation-test logic is unchanged.

Current extension, preservation and document-check records now go to
`reports/verification/`. Default reproduction logs go to `reports/reproduction/`.
This avoids overwriting the historical Stage 4 evidence. Existing scientific
artifact paths remain unchanged. [The Stage 4 evidence index](stage4/README.md)
explains the historical records; its active methodological discussion remains
available in [the statistical audit](stage4/statistical_audit.md).

## Validation commands and results

The analysis and numerical checks were regenerated using the existing pipeline:

```bash
.venv/bin/python scripts/reproduce.py --with-submission --log-dir reports/stage5/reproduction
```

That run passed acquisition verification, Stages 1–3, **all 82 pytest tests**,
independent aggregation/model/extension checks, AR(1) sensitivity and both
original-result preservation guards. It stopped at the new document geometry
check, which detected overlapping image/title *boxes*. The boxes were separated;
no calculation or testing rule was altered. The stopped run and its exit code
are retained in [the ordered command record](stage5/reproduction/commands.json)
and [the full bounded-run log](stage5/build_review/stage5-complete-reproduction.log).

After correcting the document geometry, the affected document checks and
remaining verification steps passed:

| Command | Result |
| --- | --- |
| `.venv/bin/python -W error scripts/build_submission.py` | PASS: 10-page report, 16-slide PDF/PPTX, notes and manifest |
| `.venv/bin/python -W error scripts/check_submission.py` | PASS: 88 claims; source/output hashes; PDF text/bounds; PPTX bounds/notes; identical slide text; matching bibliographies/reference hyperlinks; no image/text-box overlap |
| `.venv/bin/python -m beijing_pm25 verify` | PASS: 21 Stage 1, 35 Stage 2 and 17 Stage 3 outputs |
| `.venv/bin/python -m pip check` | PASS: no broken requirements |
| `.venv/bin/python scripts/check_editorial_preservation.py` | PASS: exact scientific/historical preservation and README length |

[Final-check commands](stage5/final_checks/commands.json) retain their timings,
exit codes and logs. A final wording clarification about the conditional-mean
limitations of a common smearing factor was followed by another successful
build, document check and preservation guard, recorded in
[wording checks](stage5/wording_checks/commands.json). The numerical suite was
not repeated for that prose-only change. Current document results are in
[submission_check.json](verification/submission_check.json).

A preliminary report draft also produced a one-line overflow page. The relevant
paragraphs were shortened without dropping their qualifications, restoring ten
pages; the document check now rejects sparse/orphan report pages. This was a
pagination issue, not an empirical failure.

All **26 PDF pages** were rasterized and inspected. The final wording revision
changed only report page 7; that page was inspected again, and the other 25
renders matched the reviewed versions pixel for pixel. Bibliographic hyperlinks
were checked in the report PDF, slide PDF and PowerPoint. Local Markdown links,
active scheduling-metadata removal and whitespace were checked separately.
[Visual review](stage5/visual_review.json) · [link/document checks](stage5/links_check.json).

## Files modified

[The complete incremental inventory](stage5/files_changed.json) compares this
revision with the preserved Stage 4 working tree, rather than attributing all
previously uncommitted Stage 4 work to this stage. Principal files are:

| Files | Editorial purpose |
| --- | --- |
| `README.md`, `PROJECT_BRIEF.md` | Research-first landing page; remove active scheduling metadata |
| `reports/reproducibility.md` | Detailed setup, acquisition, verification and regeneration instructions |
| `reports/stage2_protocol.md`, `stage2_checks.md`, `stage4_verification.md`, `stage4/statistical_audit.md`, `stage4/pr_review_summary.md`, `stage4/README.md` | Active administrative cleanup and historical/current documentation distinction |
| `src/beijing_pm25/pipeline.py`, `model_report.py` | Remove scheduling text from generated audit/report templates; refresh current documentation links |
| `scripts/build_submission.py`, `check_submission.py` | Concise report, varied slide compositions, references/links and stronger document checks |
| `scripts/reproduce.py`, `verify_extensions.py`, `audit_ar1_calendar.py`, `check_frozen_stage2.py`, `check_stage3_preservation.py` | Current log/JSON destinations; reporting metadata only |
| `scripts/check_editorial_preservation.py` | Verify exact science, figure, frozen-value and historical-record preservation |
| `submission/report.md`, `report.pdf`, `slides.pdf`, `slides.pptx`, `speaker_notes.md`, `slide_content.json`, `build_manifest.json` | Regenerated academic deliverables; figure files unchanged |
| Stage run/frozen metadata, generated audit reports and SVG exports | Refresh source/input/output references through actual regeneration; SVG generator IDs/timestamps may change |
| `reports/stage5/`, `reports/verification/`, the baseline archive and this report | Editorial baseline, command evidence, current checks and completion record |

## Unresolved issues

No unresolved statistical, numerical, link or PDF-layout failure remains.
Native PowerPoint rendering/font substitution cannot be checked without an
Office-compatible viewer in this environment. The PPTX content, notes,
relationships and bounds were checked; the rendered PDF is the verified visual
presentation. The study's observational, same-day and exploratory limitations
remain substantive qualifications, not editorial issues claimed to be solved.
