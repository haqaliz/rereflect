# Card — feat/intercom-writeback (freeform, no GitHub issue)

Source: `rereflect-next` recommendation + handoff (2026-08-14), grounded in
`DEV-TRACKING.md` P2 `intercom-writeback-orphaned` and the Intercom "Deferred v2"
`intercom-writeback` entry. Branch `feat/intercom-writeback`, worktree
`.claude/worktrees/feat-intercom-writeback`.

## Brief

Wire the orphaned Intercom write-back module into the feedback status-change path so
that resolving an Intercom-sourced feedback appends a note and closes the linked
Intercom conversation. This is the P2 "wire or delete" decision in
`DEV-TRACKING.md:589-602` (`intercom-writeback-orphaned`): `intercom_service.py`
(`add_note_to_conversation`, `close_conversation`, `get_admin_id`) has zero production
callers; the landing page's "Two-Way Sync" claim was removed and must not return until
the module is actually wired (`DEV-TRACKING.md:514`).

## Caveats (carried into the PRD, must not be papered over)

- **Write-scope uncertainty.** The token-paste private-app credential may lack Intercom
  `conversation:write` scope. The write-back needs an explicit scope check with honest
  degradation (mirror the HubSpot/Salesforce writeback soft-pause pattern — never
  auto-disable, never claim success).
- **Linkage uncertainty.** The adapter stores `conversation_id` in `source_metadata`
  for pull-ingested items; verify the linkage is equally present for webhook-ingested
  items before assuming the write-back can find its conversation.
- **Surprise factor.** Closing a support conversation automatically can surprise a
  support team — the feature must be opt-in per org, off by default, and copy must be
  explicit about what it does.
- **Worker mirror.** `intercom_service.py` lives in backend-api; worker-service cannot
  import backend-api. If the write-back fires from the worker's status-change path, a
  mirror is required (the established pattern).

## Roadmap facts (from DEV-TRACKING.md, cited)

- P2 `intercom-writeback-orphaned` (`DEV-TRACKING.md:589-602`): `intercom_service.py`
  has no production caller anywhere — grep across services/ returns only
  `tests/test_intercom.py`. No route, task, workflow hook or automation engine imports
  it. Decision: wire the module into the feedback status-change path or delete it — the
  "Two-Way Sync" copy must not return until it is wired.
- Intercom Deferred v2, `intercom-writeback` (`DEV-TRACKING.md:504-519`): "still no
  write-back; `intercom_service.py` remains orphaned with zero production callers.
  Existing P2 below covers the wire-or-delete decision."
- The Intercom integration itself is COMPLETE (`AI-TRACKING.md:66`):
  `intercom-selfhost-ingestion` — token-paste access token (BYOK, Fernet-encrypted,
  validated against `GET /me`), 15-min conversation pull, per-workspace webhook HMAC,
  `customer_email` from customer authors only.
- Precedents to reuse:
  - `salesforce-crm-writeback` (`AI-TRACKING.md:205`): opt-in per-org, off by default,
    on-change trigger + backfill, idempotent, soft-pause (never flips `is_active`).
  - `hubspot-crm-enrichment` writeback (`AI-TRACKING.md:195`): opt-in, on-change +
    backfill, soft-pause on missing write scope/field.
  - Status-syncs (`AI-TRACKING.md:59-61`): opt-in per org, off by default,
    non-destructive, source-tagged `status_changed` timeline events, worker mirror via
    source-tagged writers.
  - Outreach (`DEV-TRACKING.md:1275`, 2026-08-12): `customer-outreach-email-actions`.

## Deliverables (proposed, refine in PRD)

1. Opt-in per-org write-back config (off by default) in the Settings > Integrations
   Intercom tile.
2. On feedback `workflow_status` → resolved (or configured target status) for an
   Intercom-sourced feedback: append a note (configurable? fixed?) and close the
   conversation, idempotently, with honest failure handling.
3. `intercom_writeback` timeline event (source-tagged) + changelog + SELF_HOSTING
   docs + DEV-TRACKING FIXED marker.

## Out of scope (guardrails)

- No new vendor dependency; token-paste credential already exists.
- No plan gates; everything unlocked.
- No claiming "Two-Way Sync" on the landing page until the write path is real and
  documented.
- Not building the other three Intercom v2 deferrals (pull replies/ratings, backlog
  drain visibility, OAuth path retirement) — those are separate slices.
