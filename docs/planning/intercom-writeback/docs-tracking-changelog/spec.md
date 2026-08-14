# Aspect spec — Docs, changelog & tracking markers

**Feature:** `intercom-writeback` (prd.md R10) · **Aspect:** `docs-tracking-changelog`

## Problem slice

The feature ships with honesty obligations: flip the operator-facing "No write-back"
statement, record the claim discipline ("Two-Way Sync" returns only as what shipped),
close the P2 wire-or-delete entry with a shipped summary, and correct the deferred-v2
list. This is part of "done" (prd.md R10), not an afterthought.

## In-scope

- `docs/SELF_HOSTING.md:1752` — the "**No write-back.**" line becomes a new
  subsection: what the write-back does (note + close on resolve, opt-in, off by
  default), the `note_only` alternative, the `conversation:write` scope requirement and
  how `missing_write_scope` surfaces, transitions-after-enable-only, and the honest
  limits (resolved-only trigger; crash-window duplicate-note note; the worker task is
  fire-and-forget). Match the surrounding section's tone and heading style.
- `CHANGELOG.md` — an entry in the standard house format: added feature (opt-in
  write-back; note + close; config API; card), the deleted orphan
  (`intercom_service.py`), the honesty framing (what it does / doesn't claim — no
  backfill, resolved-only), and the FIXED markers for the beat/registration-adjacent
  naming (task name consistency). Mirror the tone of the Intercom ingestion entry
  (CHANGELOG.md:284-315) and the two-way-sync removal entry (:348-350).
- `DEV-TRACKING.md`:
  - P2 `intercom-writeback-orphaned` (:589-602) → **FIXED** with a `> Shipped:` block:
    merge commit, what shipped (delete + port, task, 5 dispatch seams + seam tests,
    marker, config API, card), and test counts. Retitle per house convention ("mark
    FIXED with the merge commit, the shipped summary" — `oauth-tokens-encryption-at-rest`
    precedent).
  - Deferred-v2 `intercom-writeback` (:512-514) → **SHIPPED**; the other three entries
    stay NOT STARTED.
  - `intercom-service` references elsewhere (e.g. any line quoting the orphan) updated.
- Check for other stale references: `docs/planning/intercom-selfhost-ingestion/prd.md:294-297`
  (the out-of-scope note referencing the wire-or-delete decision — add a pointer to the
  shipped card rather than editing history) and the `models/integration.py:19-25` stale
  "plaintext" comment (flag-only; fixing it is a separate chore — or fix it in the
  same commit if trivial, note the decision).
- Landing page: **no copy change** (prd.md OQ3). The stale OAuth-era Intercom entry in
  `services/landing-web/lib/integrations.ts:136-171` is flagged for a separate chore,
  not edited here.

## Out of scope

- Landing page copy (OQ3).
- README changes (README has zero Intercom mentions; nothing to add).
- Editing the archived `intercom-selfhost-ingestion` PRD beyond a pointer.

## Acceptance criteria (testable)

1. `SELF_HOSTING.md` no longer claims "No write-back"; the new subsection states
   defaults, scope requirement, and honest limits.
2. CHANGELOG entry exists in house format with the honesty framing.
3. DEV-TRACKING P2 carries **FIXED** + shipped summary (merge commit, what shipped,
   test counts); deferred-v2 `intercom-writeback` is **SHIPPED**.
4. No remaining production code or docs reference the deleted `intercom_service.py`
   as live code (grep sweep clean).

## Dependencies & sequencing

- Last aspect: needs the shipped summary facts (merge commit, test counts) and the
  final list of what shipped. Written after all code aspects merge into the branch.

## Open questions / risks

- Whether to fix the stale `models/integration.py:19-25` comment in this branch (it is
  adjacent — the write-back resolves credentials through that model) or leave it to the
  flagged chore. Lean: fix the comment in `config-api-routes` or this aspect only if
  it is a one-line truth correction; otherwise flag.
