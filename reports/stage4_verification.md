# Stage 4 — Final verification and submission readiness

**Historical Stage 4 verification: passed.** Verified on **23 November 2026**. Current document layouts and checks are described in [Stage 5](stage5_refinement.md). The complete pre-editorial working tree, including this original report and the verified PDFs, is preserved in [the baseline archive](archive/stage4_before_editorial_refinement.zip).

Repository: `fourhandclock/beijing-pm25`. Main was synchronized before work began; the baseline is merged PR #1, commit `87152460db5eb73c58c11df66d0964e0fd9e8467`. Changes are on **`stage4-verification-submission`**. No Stage 4 commit, push, PR creation or merge was performed.

The frozen Stage 2 model, selection rule, coefficients, training centers, high-day cutoff and numerical evaluation are preserved. Stage 3 remains exploratory. No EWMA, ridge, neural-network or forecasting extension was added. The only additional statistical calculation is the requested, separate training-only audit of AR(1) calendar gaps.

## Submission materials

The report and presentation use the title **Beyond R²: Seasonal Effects, Residual Dependence, and Model Adequacy in Beijing PM2.5 Regression**.

| Deliverable | Status |
| --- | --- |
| [Academic report, PDF](../submission/report.pdf) · [Markdown](../submission/report.md) | 10 pages; regenerated and inspected |
| [Presentation, PDF](../submission/slides.pdf) · [PowerPoint](../submission/slides.pptx) | 16 slides; same text and geometry |
| [Speaker notes](../submission/speaker_notes.md) | Notes supplied for all 16 slides, including assumptions and interpretation |
| [Document build manifest](../submission/build_manifest.json) | Exact input/output hashes and 88 source-linked numerical claims |
| [Statistical audit](stage4/statistical_audit.md) | OLS/ANOVA/HAC/Holm, transformations, lags, classification, stations, clusters and AR(1) |
| [PR review summary](stage4/pr_review_summary.md) | Concise description and validation for review |

Title pages are neutral as requested. The report and slides contain an explicit AI-assistance disclosure, without inventing author/course details or asserting compliance with an unknown course policy. Their main argument centers on regression, joint tests and residual adequacy; the additional techniques supply supporting exploratory analyses.

## Fresh-clone reproducibility

Two separate clones were exercised, each with a new virtual environment and a new original-UCI download. No environment, raw archive or processed CSV was copied into either clone.

1. **Untouched merged main:** `/tmp/beijing-pm25-stage4-baseline-hb7pxmzz`. Installed the exact committed `requirements.lock` and editable package. Stages 1–3, all **72 original tests**, both existing independent scripts, `verify` after regeneration and `pip check` passed. The new extension oracle also passed against these untouched-main results.
2. **Final candidate snapshot:** `/tmp/beijing-pm25-stage4-final-20261123`. Cloned local main with `git clone --no-local --branch main`, then replayed the candidate's tracked/new nonignored files byte for byte. This is explicitly a fresh clone plus the uncommitted candidate, rather than a claim that a Stage 4 commit was already published. [The source snapshot](stage4/candidate_source_snapshot.json) identifies the base, branch and **49 source/configuration/test/documentation files** by checksum. Both copies were checked against it. Installed `requirements-submission.lock` (which includes the unchanged scientific lock) and the editable project. **All 15 reproduction steps passed**, including **82 tests**. End-to-end runner time was **149.876 seconds**, excluding installation and the separate first download.

Verified interpreter: **Python 3.13.16**, Linux. The scientific versions remain those in `requirements.lock`; document packages are separately pinned. Exact bitwise identity across other OS/BLAS/Python combinations is not claimed. Other supported Python versions have not all been tested.

Both new downloads matched the committed provenance:

```text
Archive bytes: 8,192,212
SHA-256: b04da438b2f331ac0ffd45aebdfec0d20d2367feb5f6948c4b1f7ce1191e33c4
```

`data/raw/provenance.json` was preserved unchanged, including its original acquisition record. The new acquisition events appear in the command logs. Generated artifacts from the final candidate run were copied back to the working branch; `verify` and the document integrity check passed there again.

Machine-readable status: [reproducibility.json](stage4/reproducibility.json). Exact installation and bounded verification commands, working directories, UTC times, durations and exit codes: [audit command records](stage4/evidence/audit_commands/commands.jsonl). The successful final pipeline's exact subprocess commands are in [reproduction/commands.json](stage4/reproduction/commands.json), with a corresponding log for every step.

### Installation and execution commands

The documented installation was exercised using a new environment. Network commands additionally used bounded pip socket/retry settings; their exact forms are retained in the command records.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
# Optional document build; includes the same scientific lock:
.venv/bin/python -m pip install -r requirements-submission.lock
.venv/bin/python -m beijing_pm25 download
.venv/bin/python scripts/reproduce.py --with-submission
```

The final runner executed the following, in order. Each exited **0**; warnings were treated as errors for the analysis, tests and numerical/document verification steps shown with `-W error`.

| Command | Final result |
| --- | --- |
| `.venv/bin/python -m beijing_pm25 download` | Reverified/reused the newly downloaded original archive |
| `.venv/bin/python -W error -m beijing_pm25 stage1` | Complete; Wanliu; 725/359/357 eligible dates |
| `.venv/bin/python -W error -m beijing_pm25 stage2` | Complete; original M3 choice and frozen scores preserved |
| `.venv/bin/python -W error -m beijing_pm25 stage3` | Complete; 12 stations; exploratory results regenerated |
| `.venv/bin/python -W error -m pytest -q` | **82 passed**; no failed/skipped tests reported |
| `.venv/bin/python scripts/verify_aggregation.py` | PASS: separate standard-library raw aggregation, ranking and 1,461-date calendar |
| `.venv/bin/python -W error scripts/verify_models.py` | PASS: 3 QR fits, 9 HAC matrices, 5,050 predictions, tests, diagnostics and scores |
| `.venv/bin/python -W error scripts/verify_extensions.py` | PASS: 5 extensions, 8,580 estimates, logistic fit/cutoff/AUC, original GLSAR, 12 stations and Ward groups |
| `.venv/bin/python -W error scripts/audit_ar1_calendar.py` | PASS: paired row/calendar sensitivity and dense conditional-covariance checks |
| `.venv/bin/python scripts/check_frozen_stage2.py` | PASS: original method sources/inputs/protocol and frozen numerical evaluation |
| `.venv/bin/python scripts/check_stage3_preservation.py` | PASS: all 12 original numerical tables preserved within tolerance |
| `.venv/bin/python -W error scripts/build_submission.py` | PASS: report, slides, notes, figures and claim/hash manifest |
| `.venv/bin/python -W error scripts/check_submission.py` | PASS: 88 claims, hashes, PDF bounds/text, PPTX bounds/notes and matching slide text |
| `.venv/bin/python -m beijing_pm25 verify` | PASS: **21 Stage 1 + 35 Stage 2 + 17 Stage 3 outputs** |
| `.venv/bin/python -m pip check` | No broken requirements |

Additional checks included `scripts/audit_baseline_manifests.py`, the targeted extension/AR synthetic tests during development, final source/provenance checksum comparisons, PDF rasterization/layout inspection and `git diff --check`. The final whitespace check passes. Matplotlib's harmless line-ending spaces inside generated SVG path attributes are declared in `.gitattributes`; the SVG bytes are retained as generated.

### Expected and resolved failures

There are **no failures in the final 15-step run**. Earlier nonzero checks are retained rather than discarded:

- Before regenerating an untouched fresh clone, `verify` exited 1 because ignored processed CSVs do not exist in Git. This is expected and is now explained in README instructions. Regeneration resolved it.
- The first working document build and a subsequent layout check rejected overlong table/title text. Column widths and titles were corrected. The strict layout guard, final build, document checks and rendered review then passed. These were document layout failures, not failed empirical tests.
- The initial whitespace check flagged the README's Markdown hard-break spaces and generator-emitted SVG spaces. The README was cleaned and generated SVG whitespace declared explicitly; the final check passes.

The initial main run also emitted an unwritable Matplotlib-cache logging message. Stage 3 now initializes headless plotting and its local cache when generating figures; the final run completes without that message. No scientific calculation was altered for this fix.

## Run records and preservation

[The baseline manifest audit](stage4/baseline_manifest_audit.json) compares the records committed by PR #1 with that exact main tree. Stage 1 had stale hashes for `acquire.py`, `cli.py` and `model_report.py`, and omitted the three new Stage 3 modules. Stage 2 had the same source issues and a stale hash for its edited report. Its recorded Stage 1 dependency also referred to the old run. Stage 3's own committed source/output hashes were consistent.

Rerunning Stage 1, then Stage 2, then Stage 3 refreshed their records, dependency links, report timestamps and output hashes. New SVG exports contain generator IDs/timestamps, so their bytes need not match prior exports even when plots are unchanged. Per-run integrity is checked against the newly generated files; scientific numerical equality is checked separately.

[Stage 2 preservation evidence](stage4/stage2_preservation.json) checks seven original aggregation/model/configuration/diagnostic source files, the original Stage 1/2 configurations, raw provenance, all fitted parameter records, the validation-selected frozen specification, the training cutoff and original ANOVA/HAC/performance tables. Tolerance is `rtol=1e-10`, `atol=1e-10`. The numerical Stage 2 CSVs reproduce unchanged. Only administrative reporting text and run metadata were refreshed.

The [original prefit protocol](archive/stage2_protocol_original_20261119.md) is preserved byte for byte and checked against its original frozen-model checksum. Its original chronology is retained as historical evidence. Administrative submission metadata are omitted from the active copy; its methodological rules have not been rewritten after viewing results.

All **18 original PR #1 Stage 3 artifacts** are preserved byte for byte in [stage3_pr1_original.zip](archive/stage3_pr1_original.zip), checked against [baseline_main.json](stage4/baseline_main.json). This includes the original GLSAR results, figures, report and run record. [Stage 3 preservation evidence](stage4/stage3_preservation.json) separately compares the regenerated 12 CSV tables with the originals.

## Numerical discrepancies and interpretation corrections

**No material numerical discrepancy required changing the original calculations or frozen evaluation.** The following distinctions and differences are explicit:

| Issue | Finding and treatment |
| --- | --- |
| Stage 2 model choice | M3 remains chosen by the unchanged validation-MAE/1% simplicity rule; M2 is only 1.11% above the minimum |
| Original test evaluation | M3 MAE **46.784656**, RMSE **60.934771**; baseline MAE **55.297393**, RMSE **73.005863**, across 357 days |
| Planned robust inference | Primary HAC p-values 0.035939 / 0.030923; both Holm-adjusted p-values **0.061845**; neither rejects at 5% |
| Repeated Stage 3 serialization | Largest absolute difference from original CSV cells: **9.89786 × 10⁻¹²**; no numerical method changed. Guard uses `rtol=1e-9`, `atol=1e-8` |
| Independent extension oracle | Maximum estimate difference about **1.35 × 10⁻¹⁰**; maximum cutoff difference about **2.11 × 10⁻¹³**. Raw aggregation and separate solvers agree within stated tolerances |
| Common-sample M3 | Stage 3 refits on **721/354/355** dates, versus Stage 2's **725/359/357**. Its label now explicitly says “M3 refit on common sample.” These scores are not substituted for the frozen test |
| Log retransformation | `exp(linear predictor) × mean(exp(training residual)) − 1`; factors about 1.239 / 1.117. Estimates are above −1, not guaranteed nonnegative. Zero negatives is empirical. The log-lag term is now included in the selected-term display |
| Daily lag | Constructed before filtering on the complete calendar; never bridges an unavailable PM2.5 day. Past actual test outcomes can inform later rolling same-day estimates; no current/future target tunes the model |
| Logistic threshold | Validation F1 chooses **0.13229904066**. Test TP/FP/FN/TN = **15/44/2/296**. AUC **0.927336**, recall **0.882353**, precision **0.254237**. The class is a training quantile, not a health standard |
| Stations and clusters | M2 wind intervals are below zero at all 12 sites. H1/H2 pass within-station Holm at 6/2 sites; no full 24-test correction. Ward selects two descriptive groups; unsupported urban/suburban claims were removed |

The independent model oracle defaults to `rtol=1e-8`, `atol=1e-8`; the extension oracle to `1e-7` for each. Observed differences are far smaller. Exact source/raw/artifact hashes are compared exactly, rather than by numerical tolerance. Full per-quantity differences appear in [the extension check](stage4/independent_extensions_check.json).

### Does AR(1)'s treatment of missing days affect its conclusions?

The original GLSAR compresses retained observations and bridges **five two-day training gaps** as one-step transitions. Its original artifact is retained. To isolate spacing from estimation, a separate paired conditional-likelihood calculation uses the same first-observation treatment and predictors, changing only row versus actual-calendar distances. Calendar transitions use ρᵈ and variance `(1−ρ^(2d))/(1−ρ²)`. A dense conditional-covariance calculation verifies the wind coefficient and profile objective at each fitted ρ; synthetic tests independently verify all coefficients/covariance at fixed ρ, including zero/negative values and complete-calendar equality.

| Method | M2 ρ | H1 nominal p | M3 ρ | H2 nominal p |
| --- | ---: | ---: | ---: | ---: |
| Original iterative GLSAR, row spacing | 0.572133 | 0.003317 | 0.569018 | 0.461571 |
| Conditional likelihood, row spacing | 0.571500 | 0.003330 | 0.568407 | 0.460974 |
| Conditional likelihood, calendar spacing | 0.583015 | 0.002613 | 0.580155 | 0.447549 |

The paired change leaves signs and nominal decisions unchanged, including within-method Holm adjustment. M2 wind changes from −34.002 to −34.051; M3 winter wind from −36.644 to −37.180. The result concerns these five short gaps and does not show that missing days are generally harmless. The F references and coefficient intervals treat estimated ρ as fixed; its uncertainty is not fully accounted for. This exploratory sensitivity neither validates AR(1)/Gaussian/stationarity assumptions nor overrides the primary Stage 2 HAC/Holm conclusion. See [the separate table](../results/stage4/tables/ar1_calendar_sensitivity.csv) and [check](stage4/ar1_calendar_check.json).

## Remaining statistical limitations

- Observational associations do not establish causation. Omitted emissions, transport and boundary-layer information can affect conditional relations.
- Same-day observed weather gives contemporaneous estimation, **not genuine future forecasting**. The lagged models also consume actual earlier outcomes as they become available.
- Daily aggregation does not remove dependence. HAC joint tests are asymptotic; bandwidth, mean specification, informative missingness and temporal instability remain concerns.
- M3 retains substantial residual dependence, skewness and unequal spread. Overall positive bias conceals **−160.945 µg/m³ high-day bias** on only 17 days. Three negative estimates are retained.
- Stations share one city's pollution/weather and are dependent. Individual intervals and station-wise Holm pairs are not simultaneous protection over the many exploratory analyses.
- A common log smearing factor can be inadequate when the conditional residual distribution varies. Original/log response R² values are not directly comparable.
- Logistic odds-ratio intervals assume independent observations; rare events and validation threshold tuning limit generalization. The classification outcome is not a public-health category.
- Ward clusters summarize training profiles on pollutant-specific date sets; geographic meaning and stability on unseen periods have not been established.
- The test year was already viewed before Stage 3. Computational agreement is not independent scientific replication. Future confirmation requires an unseen period and prespecified rules.

## Report and presentation readiness

All figures/tables used by the submission can be regenerated from the committed source and checksum-verified original data. The final build checks **88 registered numerical claims** against source rows, validates all input/output hashes, checks that the PDFs have nonblank text and no replacement glyphs, and checks PDF/PPTX bounds, slide text identity and speaker notes. [Document check](stage4/submission_check.json).

Dataset attribution, the Duan citation and the official method references were checked against primary sources. The original handoff's two forecasting-paper references were also checked against their current arXiv records/revised text and remain separate from the final empirical evidence. [Reference check](stage4/reference_check.md).

All **10 report pages and 16 slides** were rasterized and inspected in contact sheets; scientific figures/tables were also inspected separately. Final rendered pages were compared pixel by pixel with the reviewed versions. Only slide 4 changed (the explicit M2 wind interpretation was added) and was inspected separately. No remaining clipping, overlap or unreadable figure was identified. [Visual review record](stage4/visual_review.json).

**Rendering limit:** an Office-compatible presentation application is unavailable in this environment, so native PowerPoint rendering/font substitution has not been tested. The PDF is the verified presentation view; the PPTX has identical text, checked bounds and notes. Author/course metadata remain neutral by request, and the submitter should apply any course-specific AI-disclosure requirement before submission.

## Files changed

[The complete file inventory](stage4/files_changed.json) enumerates modified and new paths relative to main, including generated artifacts and command evidence. The principal groups are:

| Files | Purpose |
| --- | --- |
| `README.md`, `PROJECT_BRIEF.md`, `reports/stage2_protocol.md`, `reports/stage2_checks.md` | Navigation, research scope, reproducibility and historical/current distinction |
| `src/beijing_pm25/pipeline.py`, `model_report.py`, `extension_pipeline.py`, `extensions.py` | Academic reporting, common-sample/response-scale labels and lazy headless plotting; no original Stage 2 numerical method changes |
| `src/beijing_pm25/ar1_audit.py`, `tests/test_ar1_audit.py`, `tests/test_extensions.py` | Isolated calendar-gap sensitivity, dense-reference tests and test-period leakage checks |
| `scripts/stage4_reference.py`, `verify_extensions.py`, `audit_ar1_calendar.py` | Independent Stage 3 and AR(1) checks |
| `scripts/audit_baseline_manifests.py`, `check_frozen_stage2.py`, `check_stage3_preservation.py` | Baseline hash diagnosis and preservation guards |
| `scripts/reproduce.py`, `build_submission.py`, `check_submission.py` | Bounded complete reproduction and source-linked submission generation/checks |
| `pyproject.toml`, `requirements-submission.lock`, `.gitattributes` | Optional document dependencies and generated/binary file handling; scientific lock unchanged |
| `reports/archive/stage2_protocol_original_20261119.md`, `stage3_pr1_original.zip` | Exact original evidence preserved |
| `reports/stage1_summary.md`, `stage2_analysis.md`, `stage3_extensions.md`; stage run/frozen metadata and generated exports | Refreshed reports and internally consistent run/source/output hashes |
| `reports/stage4/`, `results/stage4/`, `reports/stage4_verification.md` | Numerical audit, sensitivity tables, source snapshots, logs, machine-readable evidence and this report |
| `submission/` | Final report, slides, notes, seven readable scientific figures, content and build manifest |

The raw archive, committed provenance, Stage 1/2 configurations, scientific dependency lock and seven guarded original method sources remain unchanged. Existing analysis artifacts are preserved in Git history and the explicit archives; refreshed artifacts retain the original scientific results within the documented precision.
