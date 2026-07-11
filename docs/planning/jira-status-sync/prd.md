# PRD — Jira Inbound Status-Sync (close the integration loop)

**Slug:** `jira-status-sync`
**Branch:** `feat/jira-status-sync`
**Type:** feat (freeform — no GitHub issue)
**Status:** Draft (pre review-gate)
**Author:** rereflect-begin-fast pipeline, 2026-07-11
**Sources:** `docs/planning/_card/card.md`, `docs/planning/_card/understanding.md`

---

## Problem Statement

Rereflect's Jira integration (slice 1, shipped 2026-07-05) is **outbound-only**: it creates a
Jira issue from a feedback item and records the link in `feedback_jira_issues`. Once created, the
Jira issue lives its own life — an engineer moves it *To Do → In Progress → Done* — but the linked
Rereflect feedback item's `workflow_status` never changes. The loop is open.

**Who feels it:** CS managers, PMs, and support leads (Rereflect's core personas) who triage
feedback and route it into Jira. They must manually re-check Jira and hand-update Rereflect, or the
feedback item silently rots in the wrong status. Every downstream signal that reads
`workflow_status` — dashboard counts, "resolved" analytics, customer timeline, health scoring —
inherits the staleness, quietly eroding trust in the very status field the workflow feature exists
to maintain.

**Evidence it's real:** inbound status-sync is an explicitly-recorded v2 deferral for Jira
(`DEV-TRACKING.md:198`), and the *same* deferral exists for Asana (`:209`) and Zendesk (`:220`) —
the whole integration layer is one-directional. Linear is the lone exception; it already syncs
inbound (`api/routes/linear_webhook.py`), proving the pattern is wanted and viable in-repo.

---

## Goals & Success Metrics

**Goal:** When a linked Jira issue's status category changes, the linked Rereflect feedback item's
`workflow_status` reflects it automatically (for orgs that opt in), with a visible audit trail —
without clobbering statuses a human set by hand and without requiring a public inbound URL.

**Success metrics (self-hosted, so instrument honestly, not vanity):**
- **Correctness:** for an opted-in org, a Jira issue moved to a *Done*-category status results in the
  linked feedback item reaching its mapped `workflow_status` within one poll interval (≤ ~15 min),
  and emits exactly one `status_changed` timeline event tagged `source=jira`. Verified by tests.
- **Safety:** zero spurious status writes — a poll where no Jira category changed writes nothing
  (no timeline noise, no webhook storm). Verified by a "poll twice, second is a no-op" test **and** a
  "first poll after enable seeds the baseline but applies no status change" test.
- **Resilience:** a Jira 429 / 5xx / auth failure never crashes the beat, never disconnects the
  integration on a recoverable error, and records `last_sync_status`/`last_error` durably.
- **Adoption enablement:** an operator can turn it on, see "last synced" + any error, and trigger a
  manual sync — all from the existing Jira settings tile.

**Non-goals as metrics:** no accuracy %, no cross-tenant benchmark — this is deterministic plumbing.

---

## User Personas & Scenarios

- **CS Manager (opt-in operator):** connects Jira, flips "Sync issue status back to Rereflect" on.
  Routes a churn-risk complaint to Jira; when engineering closes it, the feedback item auto-moves to
  `resolved` and the customer timeline shows "status synced from Jira: Done". They stop babysitting.
- **Self-hoster behind NAT:** cannot expose a public webhook endpoint. Poll-first means it works
  anyway — no ingress, no tunnel. They optionally hit "Sync now" to pull immediately.
- **Skeptical PM:** manually set a feedback item to `closed`. Jira issue is still "In Progress", so
  the sync leaves it alone (Jira category unchanged since last sync). Trust preserved.

---

## Requirements

### Must-have (slice 1)
1. **Per-org opt-in.** New `status_sync_enabled` boolean on `jira_integrations`, **default false**.
   Sync only runs for `is_active=True AND status_sync_enabled=True` orgs.
2. **Poll-first reconcile.** A Celery beat (`sync_all_jira` fan-out → `sync_jira_org` per-org,
   mirroring the Zendesk poller) reads current Jira status for the issues in `feedback_jira_issues`
   for that org, batched via JQL `issue in (KEY-1, KEY-2, ...)`.
3. **statusCategory mapping (not status name).** Map Jira `fields.status.statusCategory.key`
   (`new` | `indeterminate` | `done`) → `workflow_status`. Zero-config default:
   `done → resolved`, `indeterminate → in_review`, `new → new`. Stored as a `status_mapping` JSON
   column on `jira_integrations`; absent/partial mapping falls back to the code default per key.
4. **Change-gated apply.** Persist `jira_status` (display name) + `jira_status_category` (key) +
   `last_status_synced_at` on `feedback_jira_issues` (distinct from the integration-level
   `last_synced_at`, which keeps its existing "connection last verified/polled" meaning; the
   change-gate and UI indicator read the new per-link `last_status_synced_at`). Apply a
   `workflow_status` change **only when the fetched category differs from the stored
   `jira_status_category`** → no re-clobber on every poll; never fights a manual edit unless Jira
   genuinely moved (last-writer-wins on Jira change).
   - **First-poll baseline seed (safety-critical).** On the first poll after an org enables sync,
     every link has `jira_status_category = NULL`. To honor the "no surprise bulk status changes"
     goal, the first observation **seeds** `jira_status`/`jira_status_category`/`last_status_synced_at`
     **without** applying a `workflow_status` change (NULL → value is a seed, not a "change"). Only a
     *subsequent* category transition (value → different value) applies a status change. This makes
     enablement non-destructive: no retroactive bulk backfill of existing linked items.
   - **Multi-issue resolution.** A feedback item may link to multiple Jira issues
     (`feedback_jira_issues` is one-feedback-to-many). Each link's category is tracked
     independently; when a link transitions, the target `workflow_status` is resolved by
     **most-advanced category across that feedback's links wins** (`done` > `indeterminate` > `new`),
     so re-opening one of several linked issues doesn't regress a feedback whose other issue is done.
     Deterministic and testable.
5. **Apply through the tested helper.** Route the mutation through `apply_status_change(...)`
   (`services/workflow_service.py`) with `actor_id=None`, `actor_label="jira-sync"`, so we inherit
   its no-op-on-same semantics and one-event emission; the caller then commits, invalidates
   dashboard/analytics cache, and dispatches the `feedback.status_changed` webhook (so external
   subscribers finally learn about tracker-originated changes). The emitted `status_changed` event
   carries metadata `{source:"jira", jira_status, jira_status_category, jira_issue_key}`.
   *(No echo-loop risk: outbound Jira only creates issues, never pushes status back.)*
6. **Rate-limit & error handling.** Worker Jira client translates 429 (`Retry-After`) / 5xx →
   transient (task `self.retry`, `max_retries=3`), 401/403 → auth error (record, no retry, **no**
   auto-disconnect since a static-ish API token is recoverable), 404 → treat that one issue as gone
   (skip/mark, don't fail the batch). Durable terminal-status write in a fresh session on failure.
7. **Manual "Sync now".** `POST /api/v1/integrations/jira/sync` (RBAC `require_admin_or_owner`,
   org-scoped) enqueues `send_task("src.tasks.jira_sync.sync_jira_org", args=[integ.id])`; broker
   failure → clean 502, never 500.
8. **Minimal UI** on the existing Jira settings tile: an enable/disable **toggle** bound to
   `status_sync_enabled`, plus a read-only **"Last synced / last status"** line surfacing
   `last_synced_at` + `last_sync_status`/`last_error`, and a **"Sync now"** button.
9. **Reusable reconcile core.** Factor the "(external category, mapping, stored category) → target
   status + apply + record" logic so Zendesk/Asana inbound-sync can adopt it later (pure function,
   unit-tested independent of Jira/Celery).

### Should-have
- `status_mapping` supports overriding `closed` targeting (e.g. an org maps `done → closed`).
- `GET /status` surfaces `status_sync_enabled` + last-sync fields for the UI (extend existing route).
- Structured log line per org poll: issues checked / changed / skipped-404 / rate-limited.

### Nice-to-have (out of this slice)
- Per-status-name (not just category) mapping via a `JiraStatusMapping` table + CRUD editor UI.
- Jira **webhook** inbound path (real-time) for operators who *can* expose ingress.
- Backfill/one-shot reconcile on first enable (vs. waiting for the first beat).

---

## Technical Considerations

**Services changed:** `backend-api` (model + migration + client method + routes + UI-facing status),
`worker-service` (mirror model + new client + new task + beat entry), `frontend-web` (Jira settings
tile toggle/indicator/button + API client). `analysis-engine` untouched.

**Data model (Alembic migration):**
- `jira_integrations`: `+ status_sync_enabled BOOLEAN NOT NULL DEFAULT false`,
  `+ status_mapping JSON NULL`.
- `feedback_jira_issues`: `+ jira_status VARCHAR(100) NULL`, `+ jira_status_category VARCHAR(20) NULL`,
  `+ last_status_synced_at TIMESTAMP NULL`.
- Mirror the same columns in the worker-service model copies (worker does not import backend-api).

**API client:** add `get_issue(key)` and/or `search_issues(jql, fields=["status"])` to
`backend-api/src/services/jira_client.py` (GET `/rest/api/3/search` with JQL); duplicate a lean
worker-side `services/worker-service/src/clients/jira.py` (httpx Basic auth, `_handle_response`
error taxonomy incl. 429/`Retry-After` throttle), mirroring `clients/zendesk.py`. Reuse the JQL
`issue in (...)` batch; cap batch size (e.g. 50 keys/JQL) and paginate to respect Jira limits.

**Multi-tenancy:** every query filters `organization_id`; the fan-out iterates only
`is_active AND status_sync_enabled` integrations; cross-org issue keys never mix (JQL is built from
that org's own `feedback_jira_issues` rows only).

**Reuse (verbatim patterns):** Zendesk two-task fan-out + throttle
(`worker-service/src/tasks/zendesk_sync.py`, `clients/zendesk.py`), beat registration
(`celery_app.py:36-56` include + `:95-235` schedule, 15-min interval like Zendesk `900.0`), manual
trigger via `send_task` (`zendesk_integration.py:516-565`, `background/celery_client.py`),
`apply_status_change` + `dispatch_status_webhooks` (`workflow_service.py`), timeline via
`create_workflow_event`, Fernet `encrypt_api_key`/`decrypt_api_key`.

**Testing (strict TDD):** unit-test the pure reconcile core (mapping + change-gate + no-op) with no
I/O; test the worker task with a faked client for happy-path, no-change no-op, 429-retry, 401-record,
404-skip; test the route for RBAC/org-scoping/502; frontend test the toggle + indicator. Run
`pytest tests/ -v` per service and `npm run test`/`npm run lint` for frontend. (Note repo test
gotchas: alembic multi-head — ensure a single new head; scope test runs per service.)

---

## Risks & Open Questions

- **Alembic heads:** repo has had multiple heads; the migration must chain a single new head off the
  current one. *Mitigation:* check `alembic heads` before/after; down_revision = current head.
- **Jira JQL/search API variant:** Jira Cloud is migrating `/search` → `/search/jql`; confirm the
  endpoint/fields shape against the deployed `/rest/api/3` at implementation time. *Low risk, isolated
  to the client method.*
- **Large orgs:** an org with thousands of linked issues → many JQL pages. *Mitigation:* batch cap +
  pagination + per-run page cap (mirror Zendesk `PER_RUN_PAGE_CAP`); it's fine if a huge backlog takes
  several beats to fully reconcile.
- **Deleted/moved Jira issues (404):** skip that link (optionally stamp `last_sync_status`), never
  fail the org batch.
- **Mapping to `closed`:** default never targets `closed` (reserved for explicit mapping) to avoid
  surprising archival semantics — confirm this matches how `closed` is treated downstream.
- **First-enable semantics (resolved):** the first poll **seeds** the per-link baseline without
  applying any status change (see Must-have #4) — enablement is non-destructive by design; there is
  no retroactive bulk backfill. An *opt-in* "apply current Jira statuses now" backfill is a
  nice-to-have deferred to a later slice.
- **Multi-issue resolution (resolved):** most-advanced-category-wins across a feedback's links
  (Must-have #4); called out as its own acceptance test.

---

## Out of Scope
- Zendesk and Asana inbound-sync (this slice only factors a reusable core for them).
- Jira **webhook** (real-time) inbound path — poll-first only; webhook is v2.
- Per-status-**name** mapping and a mapping-editor UI (category-level default/JSON only this slice).
- Pushing Rereflect status changes **out** to Jira (Rereflect→Jira write-back) — not this direction.
- OAuth 3LO, Jira Server/Data Center, multiple Jira sites per org (all pre-existing v2 deferrals).
