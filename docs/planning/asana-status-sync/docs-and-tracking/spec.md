# Aspect: docs-and-tracking

## Problem slice & outcome
Ship the operator-facing docs and mark the feature shipped in the roadmap/tracking files, honestly and
consistently with how `jira-status-sync` was recorded.

## In scope
- **`docs/SELF_HOSTING.md`** — add an "Asana status-sync" subsection: how to enable (opt-in, off by
  default), the default mapping `{done: resolved, new: new}`, how to remap via the API, poll-first (no
  webhook) behavior, and the 15-min cadence. State plainly that Asana has no intermediate state in slice
  1 (only completed vs not).
- **`AI-TRACKING.md`** — update the Asana row (line ~60): note inbound status-sync shipped
  2026-07-12, opt-in per org, bidirectional (reopen reverts), reuses the provider-agnostic reconcile
  core; move "inbound status-sync" out of the deferred-v2 list; keep section/custom-field mapping +
  webhook + OAuth in deferred-v2.
- **`DEV-TRACKING.md`** — same update on the Asana M3.3 block (lines ~201-210): mark inbound
  status-sync shipped, adjust the deferred-v2 bullet.

## Out of scope
- Landing-page copy (Asana slice 1 already lists Asana as available; no new marketing claim needed —
  optional, defer unless trivial).
- Any code.

## Acceptance criteria
- `SELF_HOSTING.md` has a clear, honest Asana status-sync section (no implied intermediate state).
- `AI-TRACKING.md` + `DEV-TRACKING.md` reflect shipped state with the date and the retained deferrals;
  no stale "outbound-only" claim for Asana remains.

## Dependencies & sequencing
- **Last.** Written after the implementation aspects land so the described behavior is accurate.
- Depends on nothing at code level; depends on the final shipped behavior for accuracy.

## Open questions / risks
- Keep tracking edits factual (cite the date, the opt-in default, the reused core) — no hype, matching
  the Jira row's tone.
