# Aspect spec — Docs, changelog & tracking markers

**Feature:** `intercom-backlog-drain-visibility` (prd.md R7) · **Aspect:** `docs-tracking-changelog`

## Problem slice

The feature adds an operator-visible number with honest semantics that must be
documented, and closes the last unblocked Intercom deferred-v2 entry.

## In-scope

- `docs/SELF_HOSTING.md` Intercom section: the pull bullet + honest-limits gain the
  estimate semantics — token-paste-only, computed from Intercom's `total_count` for
  the run's window (an estimate, not a queue count), absent until a run completes,
  reset on error, drain mechanics unchanged.
- `CHANGELOG.md`: new entry (added — remaining-backlog estimate on the Intercom
  settings page) with the honest framing.
- `DEV-TRACKING.md`: deferred-v2 `intercom-backlog-drain-visibility` (:517-518) →
  **SHIPPED** (house strikethrough + shipped summary + `(merged <merge-sha>, PR
  <# pending>)` placeholder, filled post-merge per house rule); the block header count
  updates (3 SHIPPED, 1 NOT STARTED — only `intercom-oauth-path-retirement` remains).
- Grep sweep validation: no stale claims ("count but not remaining" phrasing gone from
  the SHIPPED entry; the settings-page description in docs matches the shipped row).

## Out of scope

- `intercom-oauth-path-retirement` marker (gated on evidence of use — stays).
- The webhook reply/rating follow-up defect note (already recorded in the
  pull-replies-and-ratings SHIPPED entry).
- Landing page (nothing claims a remaining count there — verify with a grep).

## Acceptance criteria (testable)

1. The deferred-v2 entry reads SHIPPED with the shipped summary + placeholders; header
   count correct.
2. No surviving claim that the settings page lacks a remaining count.
3. Docs state the estimate semantics (honest-limits).

## Dependencies & sequencing

- Last aspect (after code lands; merge facts filled post-merge).

## Open questions / risks

- None material.
