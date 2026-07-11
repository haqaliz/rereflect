# Card — feat/jira-status-sync (freeform)

**Type:** feat
**Slug:** jira-status-sync
**Branch:** feat/jira-status-sync
**Source:** freeform (no GitHub issue) — brief captured from the `rereflect-next` recommendation (2026-07-11) + user go-ahead.

## Brief

Build **inbound status-sync for Jira** to close the integration loop. Today the Jira
integration (shipped 2026-07-05, slice 1) is outbound-only: it creates Jira issues from
feedback items. When the linked Jira issue's status later changes (e.g. an engineer moves
it to *Done*), Rereflect's feedback item does not reflect it. This feature reconciles the
Jira issue status back onto the linked feedback item.

### Core behavior (first testable slice)
- A **Celery beat** polls Jira for the current status of issues recorded in the existing
  `feedback_jira_issues` link table (`services/backend-api/src/models/jira_integration.py`).
- Each status change maps onto the linked feedback item's `workflow_status`.
- Emit a `jira_status_synced` timeline event on the feedback item when a change is applied.
- Scope the first slice to a single org: poll → map → update `workflow_status` + timeline event.

### Design constraints / decisions carried from the recommendation
- **Poll-first.** Self-hosted instances are frequently behind NAT/firewalls, so inbound
  webhooks are unreliable. Build polling first; a Jira webhook path is optional v2.
- **Reuse existing plumbing.** Mirror the existing **Linear inbound pattern**
  (`services/backend-api/src/api/routes/linear_webhook.py`) and reuse the encrypted Jira
  API-token client from the outbound slice.
- **Zero-config default mapping.** A small per-org status-mapping (Jira status → feedback
  `workflow_status`) with a working default so it works out of the box:
  `Done → resolved`, `In Progress → in_progress` (exact defaults TBD in PRD against the
  real `workflow_status` enum).
- **Generalize the core.** After Jira works, factor the mapping/reconcile core so Zendesk
  and Asana (both have the same inbound-sync v2 deferral) can adopt it.
- **Rate limits.** Batch by JQL over stored issue keys; respect Jira Cloud rate limits and
  429 `Retry-After` (the Zendesk poller already has a throttle precedent).

## Provenance (from AI-TRACKING.md / DEV-TRACKING.md)
- Jira slice 1 shipped 2026-07-05 (`DEV-TRACKING.md:189`). **Deferred v2** explicitly includes
  "inbound webhook / status sync back to Rereflect, project/status mapping config"
  (`DEV-TRACKING.md:198`).
- Same inbound-sync deferral exists for **Asana** (`DEV-TRACKING.md:209`) and **Zendesk**
  (`DEV-TRACKING.md:220`) — this feature is the first of a cross-integration close-the-loop.
- **Linear** already does inbound sync via `linear_webhook.py` — the in-repo pattern to mirror.

## Open questions (for the deep dig / PRD)
- What is the exact `workflow_status` enum on the feedback model, and what is the sensible
  default Jira-status → workflow_status mapping?
- Poll cadence (beat interval) and batching strategy (JQL `issue in (...)` chunk size).
- Where does per-org status-mapping config live (new column/table vs. reuse of Jira
  integration config), and is it editable in the frontend in this slice or deferred?
- Conflict policy: if a user manually changed `workflow_status` in Rereflect after the Jira
  link was made, does an inbound Jira change overwrite it? (last-writer-wins vs. guard)
- Should sync be bidirectional-aware (avoid ping-pong) given outbound only creates, never
  updates, Jira today?
