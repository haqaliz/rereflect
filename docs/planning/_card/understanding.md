# Understanding — status-sync-realtime-mapping (Phase 2 dig)

## What the task is really asking
Close the "engineer resolves the ticket → Rereflect reflects it instantly,
mapped to your states" loop across the three shipped issue integrations
(Jira, Asana, Zendesk) by adding (a) **operator-facing status mapping** and
(b) **real-time inbound webhooks**.

## ⚠️ Premise corrections (the dig contradicts the brief — surface at review gate)

The original brief (from `rereflect-next`, which read `AI-TRACKING.md`) is
**partly stale against the actual worktree code**:

1. **"Zendesk status-sync toggle is API-only" is FALSE here.** All three
   providers already ship an in-app **Inbound Status Sync toggle card**:
   `components/settings/{Jira,Asana,Zendesk}StatusSyncCard.tsx`, each wired into
   its provider page (Zendesk at `zendesk/page.tsx:514`). No new toggle needed.
2. **Operator-configurable mapping already partly exists.** `PATCH
   /api/v1/integrations/{provider}/status-sync` accepts `{enabled, status_mapping}`
   for all three, persists a per-org `status_mapping` JSON that **overrides a
   hardcoded default map per key**. The frontend `patch*StatusSync(enabled,
   statusMapping?)` clients **already serialize `status_mapping`** — the UI just
   never passes it.
3. **A full mapping editor already exists for Linear** (`LinearSettings.tsx`
   "Status Mapping" tab → `linearAPI.updateStatusMappings`). That is the
   reusable blueprint to generalize, not a from-scratch build.

So the genuinely-missing pieces are narrower and clearer than the brief implied:
- **No mapping editor UI** for Jira/Asana/Zendesk (only Linear has one).
- **GET `/status` omits `status_mapping`** for Jira & Asana (Zendesk returns it),
  so an editor can't hydrate current values without a small backend change.
- **No real-time inbound webhook** for Jira or Asana (poll-only, 15 min). Zendesk
  and Linear already have webhook receivers — the reference patterns.

## Mapping granularity differs by provider (key design constraint)
- **Zendesk** — `status_mapping` keyed by **raw foreign status**
  (`new/open/pending/hold/solved/closed`, 6 known values). True per-status-name.
  Default in `services/*/services/zendesk_status_core.py::DEFAULT_ZENDESK_MAP`.
- **Jira & Asana** — `status_mapping` keyed by **category** (`new/indeterminate/
  done`), NOT raw status name. Default in the duplicated
  `services/{backend-api,worker-service}/src/services/status_sync_core.py::
  DEFAULT_CATEGORY_MAP`. Jira derives category from its own `statusCategory`;
  Asana derives it from the boolean `completed` flag only (section-name →
  `indeterminate` is deferred v2). The `JiraIntegration.status_mapping` model
  comment ("{jira_status_name: ...}") is **misleading** — it's category-keyed.
- **Target states** (both) = `VALID_STATUSES = ("new","in_review","resolved",
  "closed")` = `FeedbackItem.workflow_status` (`models/feedback.py:65`). Frontend
  mirror: `REREFLECT_STATUSES` in `lib/api/linear.ts:227`.

→ A "shared editor" is feasible if parameterized by (provider's foreign-status/
category list, current mapping, REREFLECT_STATUSES). But its left column means
different things per provider (raw statuses for Zendesk; 3 categories for Jira;
2 for Asana). **Open question for the interview:** ship the honest
category-level editor for Jira/Asana now, or invest in per-raw-status-name
granularity (deeper — requires extending the raw→category step + client status
discovery)?

## The reference architecture to generalize (from Zendesk + Linear)
- **Pure, no-I/O core** (`*_status_core.py`) holds the foreign-status set +
  default map + `resolve_target_status(foreign, mapping)` — **duplicated verbatim
  in backend-api and worker-service** (worker can't import backend-api). Any
  change touches both copies.
- **Sidecar** (`FeedbackZendeskSync` / `FeedbackJiraIssue` / `FeedbackAsanaTask`)
  stores last-observed foreign status; `decide_update` → seed/noop/changed.
- **Race-safe apply**: Zendesk uses a conditional `UPDATE ... WHERE
  workflow_status=:old` guard and writes exactly one `FeedbackWorkflowEvent`.
  Jira/Asana use shared `worker-service/src/services/status_writer.py::
  apply_status_change_worker` — **verify whether it has the same race guard**
  (Zendesk's docstring claims Jira lacked it; possible latent bug to fix).
- **Webhook receiver** (Zendesk in `source_webhooks.py:449`; Linear in
  `routes/linear_webhook.py`): fail-closed HMAC verify over raw bytes, resolve
  org, anti-spoof event discriminator, then route through the SAME core +
  apply path as the poller so poll and webhook stay consistent. Provider-specific:
  signature scheme + event discriminator field.

## Affected areas by service
- **backend-api**: `models/{jira,asana,zendesk}_integration.py`,
  `api/routes/{jira,asana,zendesk}_integration.py` (GET status + PATCH
  status-sync), `services/status_sync_core.py`, `services/zendesk_status_*.py`,
  new `routes/{jira,asana}_webhook.py`, `api/main.py` registration, alembic if any
  new columns.
- **worker-service**: `services/status_sync_core.py` (copy), `tasks/{jira,asana}_sync.py`,
  `services/status_writer.py`, `celery_app.py` schedules.
- **frontend-web**: `components/settings/{Jira,Asana,Zendesk}StatusSyncCard.tsx`,
  new shared `components/settings/StatusMappingEditor.tsx` (from `LinearSettings`),
  `lib/api/{jira,asana,zendesk}.ts` (add `status_mapping` to Jira/Asana status
  types), relocate/share `REREFLECT_STATUSES`.

## Proposed slicing (to confirm in interview / at review gate)
- **Slice 1 — Operator-mapped (mostly frontend + tiny backend):** shared
  `StatusMappingEditor`, wired into the 3 status-sync cards, saving via existing
  `patch*StatusSync`; add `status_mapping` to Jira/Asana GET status responses so
  it round-trips. Honest scope: category-level for Jira/Asana, raw-status for
  Zendesk.
- **Slice 2 — Jira real-time inbound webhook** (generalize Zendesk/Linear
  receiver → shared core → status_writer; keep 15-min poll as fallback).
- **Slice 3 — Asana real-time inbound webhook.**
- **Optional hardening:** race-guard parity fix in `status_writer.py`.

## Out of scope (unchanged)
Outbound webhook-on-change; OAuth 3LO / Jira Server-DC / multiple sites; Asana
section-name granularity (unless pulled in as the "deeper" option above).
