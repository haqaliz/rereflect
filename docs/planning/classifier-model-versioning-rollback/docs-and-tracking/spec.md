# Aspect spec — docs-and-tracking

**Parent PRD:** `../prd.md` (M10) · **Depends on:** all code aspects (write last, describing shipped behavior).

## Problem slice
Record the durable-rollback behavior for operators and correct the stale roadmap
checkbox.

## In scope
- **`AI-TRACKING.md`:** check the M4.2 box at line ~384 ("Model versioning: track
  model performance over time, rollback if accuracy drops") — now delivered. Add a
  short durable-rollback note under the M5.2 rows (63-65) linking
  `docs/planning/classifier-model-versioning-rollback/`. Do NOT overstate — the hold
  is a manual escape hatch, not auto-promotion gating (PRD R6).
- **`SELF_HOSTING.md`:** document (a) the weekly promotion cadence (Mon 06:30 UTC)
  the hold pauses, (b) how rollback engages the hold, (c) how to resume
  auto-promotion, per classifier_type. Honest framing: held models don't
  auto-improve until resumed; the card nudges when a challenger would beat the held
  version.
- **`CHANGELOG.md`:** one entry summarizing durable rollback + version list + resume.

## Out of scope
- Marketing/landing copy. New docs pages.

## Acceptance criteria
- The three files updated; claims match shipped endpoints/behavior exactly (no
  fabricated metrics; honesty brand).
- `AI-TRACKING.md:384` box checked with a dated note.

## Dependencies / notes
- Write after the code aspects land so the docs describe real behavior. Mirror the
  tone/structure of the most recent CHANGELOG + SELF_HOSTING entries
  (e.g. the `usage-decline-churn-labels` / `usage-trend-*` sections).
