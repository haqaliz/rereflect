# Spec — docs-changelog-tracking (close-out)

## Problem slice

Repo convention (visible across every shipped feature's commit history) is that a feature
lands with its docs: CHANGELOG entries, SELF_HOSTING upgrade callouts, AI-TRACKING
markers, DEV-TRACKING FIXED markers, and planning close-outs. Without this aspect,
AI-TRACKING M5.3 stays "planned" and the beat-defect NOTE stays stale.

## In scope

- **CHANGELOG.md** entries (Unreleased): the beat-registration fix, the gate decision,
  the churn classifier head (mode, shadow A/B, promotion rule, rollback), each in the
  repo's honest-limits voice.
- **`docs/SELF_HOSTING.md`**: upgrade callout for the new `churn_classifier_mode` /
  `churn_autopromote_hold` settings, the readiness/gate number if it moved, and any
  air-gap/pre-bake note if the core adds model assets (it should not — JSON artifacts
  only, no HF downloads).
- **AI-TRACKING.md**: M5.3 markers — the gate caveat section (542-553) gets the study's
  decision appended; M5.3 moves to COMPLETE (or PARTIAL with the honest reason) per the
  actual verdict.
- **DEV-TRACKING.md**: FIXED marker for the undecorated churn-calibration tasks; update
  the TRACKING.md note and the `usage_metrics.py:482-485` NOTE once the fix lands (the
  NOTE explicitly says "Do NOT edit churn_calibration.py here; address in a separate
  audit pass" — that pass is aspect 1).
- **`docs/planning/per-org-churn-model/`** close-out: PRD Decision Record entries
  (gate verdict, abort/continue outcome), aspect statuses.

## Out of scope

- Blog posts / marketing copy.
- Docs for aspects' internals beyond what SELF_HOSTING covers.

## Acceptance criteria

1. `git grep -n "refit_all_orgs\|NotRegistered"` in the worktree finds no stale NOTE
   claiming the tasks are unregistered.
2. AI-TRACKING M5.3 status + gate caveat reflect the actual verdict; CHANGELOG has the
   entries; SELF_HOSTING has the callout.
3. Docs diff reviewed and committed as part of the feature branch.

## Dependencies / sequencing

- Last aspect — everything else must land first; the AI-TRACKING marker especially needs
  the gate verdict (aspect 2) and the beat fix (aspect 1) proven.

## Open questions / risks

- Whether the gate verdict warrants a "PARTIAL" vs "COMPLETE" M5.3 marker — decided by
  the actual outcome, never pre-committed.
