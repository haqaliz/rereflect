# Card — feat/zendesk-status-sync (freeform)

**Type:** feat
**Slug/id:** zendesk-status-sync
**Branch:** feat/zendesk-status-sync
**GitHub issue:** none (freeform — selected via `rereflect-next`)

## Brief (source: rereflect-next recommendation)

Build **inbound Zendesk status-sync** as the direct follow-on to the shipped Jira
status-sync. Reuse the provider-agnostic reconcile core shipped with Jira
(`services/{worker-service,backend-api}/src/services/status_sync_core.py`) to map a
linked Zendesk ticket's current status back onto the feedback's `workflow_status`.

Mirror the Jira status-sync slice's shape exactly:
- Poll-first Celery beat (15-min, per-org fan-out `sync_all_zendesk` → `sync_zendesk_org`),
  mirroring the existing Zendesk incremental poller two-task pattern.
- **Opt-in per org, off by default.**
- Non-destructive first-poll baseline seed (no retroactive bulk backfill).
- 429/`Retry-After` throttle; auth-error records (no disconnect); manual "Sync now" (`POST /sync`).
- Status-sync toggle + last-synced/error indicator on the Zendesk integration tile.
- Apply via `apply_status_change` (worker mirror) emitting one `status_changed` timeline
  event tagged `source=zendesk`.
- Strict TDD on the reconcile mapping + change-gate + no-op path.

## Key design decisions the dig must nail

1. **Zendesk has no Jira-style 3-bucket `statusCategory`.** Zendesk ticket statuses are
   `new / open / pending / hold / solved / closed`. The slice must define a status→category
   mapping with a per-org `status_mapping` JSON override, mirroring Jira. Proposed default:
   - `solved`, `closed` → `resolved`
   - `open`, `pending`, `hold` → `in_review`
   - `new` → `new`

2. **The poll set.** Jira used a dedicated `feedback_jira_issues` link table. Zendesk stores
   each ticket ID on `feedback.source_external_id` (deduped by ticket ID at ingest, `source='zendesk'`).
   The existing Zendesk poller is **new-tickets-only** (incremental cursor) and does NOT re-poll
   already-linked tickets' statuses. Status-sync needs a **new poll path over the existing
   linked-ticket set** (feedback rows where `source='zendesk'`, keyed by `source_external_id`).

## Grounding (files)

- Reconcile core (both mirrors): `services/{worker-service,backend-api}/src/services/status_sync_core.py`
- Jira status-sync template: `services/worker-service/src/tasks/jira_sync.py`, `docs/planning/jira-status-sync/`
- Jira PRD out-of-scope names Zendesk/Asana inbound-sync as the reconcile-core reuse targets:
  `docs/planning/jira-status-sync/prd.md:193`
- Zendesk deferred-v2 includes "write-back / bidirectional status sync to Zendesk": `DEV-TRACKING.md:221`
- Zendesk models: `services/backend-api/src/models/zendesk_integration.py`; `feedback.source_external_id`
  (`services/backend-api/src/models/feedback.py:17`)

## Caveat (stated honestly for the dig)

- Direction is **inbound** (Zendesk → Rereflect feedback status), matching the Jira status-sync
  reuse target. Outbound write-back (Rereflect → Zendesk) is a separate deferred item — out of scope here.
- `feat/asana-status-sync` has a worktree open in a parallel session (the *Asana* reuse of the same
  core). This slice is the *Zendesk* reuse — no overlap, but the reconcile core is shared code; treat
  any core changes as characterization-locked (Jira behavior must stay byte-identical).
