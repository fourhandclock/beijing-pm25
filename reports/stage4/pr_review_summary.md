# Verify reproducibility and prepare the final Beijing PM2.5 submission

Refresh the stale Stage 1–2 run/source records introduced by PR #1 and prepare a 10-page academic report plus a 16-slide PDF/PowerPoint presentation. Preserve the original Stage 2 numerical methods, model choice and frozen evaluation. Clarify common-sample Stage 3 comparisons, log retransformation, validation-selected classification, station dependence and exploratory status.

Validation: untouched-main fresh clone passed 72 tests; the final candidate in a separate fresh clone passed all 15 reproduction steps and 82 tests. New UCI downloads match the committed checksum. Independent aggregation, QR/ANOVA/HAC/Holm, extension/logistic/station/Ward checks and repository `verify` pass. Original Stage 3 artifacts are archived exactly; regenerated tables differ by at most 9.90 × 10⁻¹². Calendar-aware AR(1) sensitivity leaves nominal conclusions unchanged. The document build checks 88 source-linked claims; all 26 PDF pages were rendered and reviewed.

Remaining limits: observational same-day estimation, residual dependence/high-day failure, reused test data for exploratory extensions, dependent stations and approximate AR(1) uncertainty. Native PowerPoint rendering was not available; PDF slides are the verified view. Title pages are neutral and AI assistance is disclosed. No new predictive extension, remote publication or merge is included.

Full evidence and file inventory: [Stage 4 verification report](../stage4_verification.md).
