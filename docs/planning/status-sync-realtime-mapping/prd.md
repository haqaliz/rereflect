# PRD — Real-time, Operator-mapped Integration Status-Sync (v2)

**Slug:** `status-sync-realtime-mapping`
**Branch:** `feat/status-sync-realtime-mapping`
**Type:** feat (freeform; no GitHub issue)
**Status:** Draft for review gate
**Author:** Rereflect (via `rereflect-begin-fast`)

---

## Problem Statement

Rereflect closes the feedback→ticket loop for three issue trackers (Jira, Asana,
Zendesk): a feedback item can spawn an issue/ticket, and inbound **status-sync**
flows the ticket's resolution back onto the feedback item's `workflow_status`.
Today that back-flow has two gaps:

1. **Not real-time for Jira/Asana.** Both are **poll-only** on a 15-minute
   Celery Beat schedule. An engineer resolving a Jira issue isn't reflected in
   Rereflect for up to 15 minutes. Zendesk already has a real-time webhook;
   Jira/Asana do not.
2. **The status mapping is invisible to operators.** The foreign-status →
   Rereflect-state mapping is already stored per-org (`status_mapping` JSON) and
   editable via `PATCH /status-sync`, and the frontend API clients already
   serialize it — **but no UI exposes it**. Operators can't see or change how
   "solved"/"done"/"in progress" map to Rereflect's `new/in_review/resolved/
   closed`. Only Linear has a mapping editor today.

**Who has this problem:** self-hosting operators (OSS, single-tenant) running
the Jira/Asana/Zendesk integrations who want the feedback board to reflect their
team's ticket workflow accurately and promptly.

**Evidence it's real:** the gaps are documented deferred-v2 items across all
three providers (`AI-TRACKING.md` lines 59–61; `DEV-TRACKING.md` M3.2/M3.3/M3.4
deferred lists). The mapping override column, PATCH endpoint, and frontend
serialization already exist but are dead-ended without UI.

**Cost of status quo:** up to 15-minute staleness on Jira/Asana; a hidden,
un-inspectable mapping that operators must reverse-engineer or edit via raw API
calls. Both undercut trust in the integration layer — a core Rereflect moat.

---

## Goals & Success Metrics

- **G1 — Real-time reflection.** A Jira issue or Asana task status change is
  reflected on the linked feedback item's `workflow_status` in **seconds**
  (webhook path), with the 15-min poll retained as a guaranteed fallback.
  - *Metric:* webhook receipt → `workflow_status` write measured in tests to
    happen within one request; poll fallback still applies changes missed by a
    webhook outage.
- **G2 — Visible, editable mapping.** For all three providers, an operator can
  view the current foreign-status→Rereflect-state mapping in-app and save an
  override, with values validated against the canonical states.
  - *Metric:* editor renders current mapping (hydrated from GET `/status`), saves
    via existing `patch*StatusSync`, and a round-trip test confirms persistence.
- **G3 — No regressions / no double-writes.** Concurrent poll + webhook applies
  never produce duplicate `FeedbackWorkflowEvent` rows or lost updates.
  - *Metric:* race-guard tests (conditional UPDATE) pass for all providers; a
    no-op apply writes zero events.
- **G4 — Honest UX.** The editor is explicit that Jira/Asana map **status
  categories** (not raw status names) while Zendesk maps raw statuses.

**Non-goals as metrics:** no new provider onboarding, no outbound webhooks, no
per-raw-status-name mapping for Jira/Asana.

---

## User Personas & Scenarios

- **Operator / Admin (self-hoster).** Connects Jira, wants "In Progress" issues
  to show as `in_review` and "Done" as `resolved`. Opens Settings → Integrations
  → Jira → sees the Status Mapping editor, adjusts the `indeterminate`→`in_review`
  row, saves. Later an engineer moves an issue to Done; within seconds the linked
  feedback flips to `resolved` (webhook), and the timeline shows one
  status-changed event sourced from Jira.
- **Member (read-only for config).** Sees the mapping (informational) but cannot
  edit (mutations gated `require_admin_or_owner`, matching existing cards).

---

## Requirements

### Must-have (M)
- **M1** Shared `StatusMappingEditor` React component (generalized from
  `LinearSettings.tsx`), parameterized by (foreign-key list + labels, current
  mapping, `REREFLECT_STATUSES`, onSave), reused by all three provider cards.
- **M2** Wire the editor into `JiraStatusSyncCard`, `AsanaStatusSyncCard`,
  `ZendeskStatusSyncCard`. Save via the existing
  `patch{Jira,Asana,Zendesk}StatusSync(enabled, statusMapping)` clients.
- **M3** Backend: add `status_mapping` to Jira and Asana **GET `/status`**
  responses (`JiraStatusResponse`, `AsanaStatusResponse`) so the editor hydrates
  current values. Zendesk already returns it.
- **M4** Frontend: add `status_mapping` field to `JiraConnectionStatus` and
  `AsanaConnectionStatus` types; relocate/share `REREFLECT_STATUSES` (currently
  Linear-scoped) into a shared module.
- **M5** Jira **real-time inbound webhook** receiver: new
  `routes/jira_webhook.py`, registered in `main.py`, fail-closed authenticity
  check, org resolution, event discriminator, routed through the **same**
  `status_sync_core` + apply path the poller uses. Poll retained as fallback.
- **M6** Asana **real-time inbound webhook** receiver: analogous new route,
  honoring Asana's webhook **handshake** (`X-Hook-Secret` echo) and
  `X-Hook-Signature` HMAC.
- **M7** Race-guard parity: `worker-service/src/services/status_writer.py`
  `apply_status_change_worker` uses the conditional `UPDATE ... WHERE
  workflow_status=:old` guard + exactly-one-event pattern (as Zendesk's
  `_apply_zendesk_status`). Verify first; fix if missing. The webhook apply path
  must use the same guard.
- **M8** Category-level mapping for Jira (`new/indeterminate/done`) and Asana
  (`new/done`); Zendesk raw statuses (`new/open/pending/hold/solved/closed`).
  Editor labels these honestly.

### Should-have (S)
- **S1** Webhook enable/disable surfaced in each provider's status-sync card
  (mirroring Zendesk's webhook-secret reveal card where a secret is generated).
- **S2** Observability: reuse `last_status_synced_at` / `last_status_sync_error`
  (Zendesk) — add equivalents for Jira/Asana if absent, so webhook failures are
  visible.
- **S3** Validation parity: `_validate_status_mapping` returns 422 on bad
  keys/values for all three (Jira/Asana already have it; keep consistent).

### Nice-to-have (N)
- **N1** A "reset to defaults" button in the editor (clears the override →
  server default applies).
- **N2** Inline preview of the effective merged mapping (default + override).

---

## Technical Considerations

### Services changed
- **backend-api**
  - `api/routes/jira_integration.py`, `asana_integration.py` — add
    `status_mapping` to GET status responses (M3).
  - New `api/routes/jira_webhook.py`, `api/routes/asana_webhook.py` (M5/M6);
    register in `api/main.py`. Model on `routes/linear_webhook.py` +
    `source_webhooks.py` Zendesk receiver.
  - `services/status_sync_core.py` — unchanged mapping semantics (category
    default + override merge); reused by webhook path.
  - `services/status_writer.py`-equivalent apply for the webhook path (a
    backend-api reconcile port mirroring `zendesk_status_reconcile.py`), OR route
    webhook → enqueue a Celery apply. **Decision:** apply synchronously in the
    request via a backend-api reconcile port (matches Zendesk), keeping webhook
    latency low and consistent with the existing pattern.
  - Models: add webhook secret/enabled columns to `JiraIntegration` /
    `AsanaIntegration` if adopting a per-org secret like Zendesk
    (`webhook_secret`). Alembic migration(s) required — single-head (confirm via
    live `alembic heads`).
- **worker-service**
  - `services/status_writer.py` — race-guard parity fix (M7).
  - `services/status_sync_core.py` — **verbatim copy** kept in sync with the
    backend-api copy (worker cannot import backend-api).
  - `tasks/{jira,asana}_sync.py` — unchanged behavior; retained as fallback.
  - `celery_app.py` — schedules unchanged.
- **frontend-web**
  - New `components/settings/StatusMappingEditor.tsx` (M1).
  - `components/settings/{Jira,Asana,Zendesk}StatusSyncCard.tsx` — mount editor
    (M2).
  - `lib/api/{jira,asana}.ts` — add `status_mapping` to status types (M4);
    shared `REREFLECT_STATUSES`.

### Architecture fit / constraints
- **Multi-tenancy:** every path scoped by `organization_id`; webhook resolves org
  by connection identity (Jira site_url / Asana workspace or resource gid),
  fail-closed on unknown.
- **Duplicated pure core:** any change to `status_sync_core.py` must be applied to
  **both** backend-api and worker-service copies (enforced by a test asserting
  byte/ís-equality, as Zendesk does).
- **Webhook authenticity (provider-specific):**
  - *Jira Cloud:* webhooks don't sign per-event by default; use a **secret path
    token** (unguessable URL segment) and/or JWT if registered as a Connect app.
    v1: per-org secret token in the URL/header, fail-closed. (Confirm mechanism
    in tech-plan.)
  - *Asana:* mandatory **handshake** — first request sends `X-Hook-Secret`, we
    must echo it back in the response header and store it; subsequent events are
    signed `X-Hook-Signature` = HMAC-SHA256(secret, raw_body). Fail-closed.
- **BYOK / OSS fit:** pure workflow/config; no vendor-model dependency, no SaaS
  tier gating. `require_admin_or_owner` for all mutations.
- **Consistency:** webhook and poll both funnel through `resolve_target_status`
  + the race-safe apply so they can't diverge or double-write.

### Data Model (Alembic)
- Possible new columns on `jira_integrations` / `asana_integrations`:
  `webhook_secret` (Text, Fernet-encrypted, nullable), and for Asana a stored
  handshake secret + resource/webhook gid. `status_sync_enabled` already exists.
  Migration is single-head; verify with live `alembic heads` (per repo gotcha —
  don't trust static parse).

---

## Risks & Open Questions

- **R1 — Jira webhook authenticity.** Jira Cloud's webhook auth story is weaker
  than Zendesk's per-event HMAC. Mitigation: unguessable per-org secret path
  token + fail-closed; document the trust model honestly in SELF_HOSTING. *Resolve
  exact mechanism in tech-plan.*
- **R2 — Asana handshake correctness.** The `X-Hook-Secret` echo must happen on
  the very first request or Asana won't activate the webhook. Needs a dedicated
  handshake branch + test.
- **R3 — Category vs raw-status honesty.** Editor must not imply per-status-name
  control for Jira/Asana. Mitigation: explicit labels + copy (M8/G4).
- **R4 — Core duplication drift.** Mitigation: equality test across the two
  `status_sync_core.py` copies.
- **R5 — Race guard scope.** Verify `status_writer.py` actually lacks the guard
  before "fixing"; if it already has it, M7 reduces to adding a regression test
  and using the same path in the webhook receiver.
- **R6 — Encryption key.** Webhook secrets use the existing `LLM_ENCRYPTION_KEY`
  Fernet pattern; missing key must fail-closed (no silent plaintext), matching
  Zendesk's R6 behavior.

---

## Out of Scope

- Outbound webhook-on-change (notifying external systems when Rereflect status
  changes).
- OAuth 3LO, Jira Server/Data Center, multiple sites/workspaces per org.
- Per-raw-status-name mapping for Jira; Asana section-name / custom-field →
  `indeterminate` granularity (stays category/`completed`-based).
- New provider integrations; changes to outbound issue/task creation.
- Not related: M5.3 churn ML (blocker-deferred), M4.3 benchmarks (dropped),
  M5.4 local embeddings (parked).

---

## Proposed Aspects (for decomposition → tech-plan)

1. **`mapping-editor`** (frontend + M3 backend round-trip) — shared editor, wire
   into 3 cards, `status_mapping` in Jira/Asana GET status + client types.
   *Independently shippable; no webhooks.*
2. **`status-writer-race-guard`** (worker) — verify + parity fix + regression
   tests. *Prereq for webhook aspects' apply path.*
3. **`jira-webhook`** (backend + migration) — real-time inbound receiver, secret
   token auth, reconcile via shared core, poll retained.
4. **`asana-webhook`** (backend + migration) — real-time inbound receiver,
   handshake + HMAC, reconcile via shared core, poll retained.

Sequencing: aspect 1 and aspect 2 are independent and can run in parallel;
aspects 3 and 4 depend on aspect 2 (shared race-safe apply) and can then run in
parallel with each other.
