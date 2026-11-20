# Codex project instructions

This workspace contains a course statistics project about the UCI Beijing PM2.5 dataset. Before starting work, read `PROJECT_BRIEF.md` in full and align every task with its research question, scope, inference limitations, and stage boundaries.

- Prioritize syllabus-relevant methods: multiple OLS regression, nested-model ANOVA/partial F-tests, joint robust tests when justified, residual diagnostics, and interpretable reporting.
- Work **one stage at a time**. Begin with data audit and baseline infrastructure; **stop for approval before moving into model fitting or optional extensions**.
- Preserve raw data. Record provenance and all cleaning decisions. Do not invent data, metrics, plots, literature claims, or completed experiments.
- Treat time-series dependence and information leakage as first-class correctness risks. Chronological evaluation; train-only preprocessing; same-day estimation vs forecasting clearly labeled.
- Distinguish statistical association from causation, numerical stability from statistical coefficient uncertainty, and reported papers' results from our experiments.
- Prefer simple readable Python, documented commands, tests and reproducible figures over heavy ML pipelines.
- Keep memory use modest and guard long-running jobs with timeouts and cancellation.
- Do not run Git commands, commit, push, open PRs, edit unrelated directories, or publish/upload anything unless the user explicitly authorizes it.
- After each stage, provide a concise report: changes, checks run, empirical results (if any), limitations, and next-stage proposal.
