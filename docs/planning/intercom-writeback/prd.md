# PRD — Intercom write-back (close the loop on resolve)

**Slug:** `intercom-writeback` · **Branch:** `feat/intercom-writeback`
**Type:** feat · **Created:** 2026-08-14
**Card:** `docs/planning/_card/card.md` (freeform, no GitHub issue) · **Source:** `rereflect-next` handoff

---

## Problem Statement

`services/backend-api/src/services/intercom_service.py` — `add_note_to_conversation`,
`close_conversation`, `get_admin_id` — has **zero production callers** anywhere in the
repo. `grep` across `services/` finds only `tests/test_intercom.py` (DEV-TRACKING.md P2
`intercom-writeback-orphaned`, :589-602). It is the fourth instance of the repo's
dead-code family: green tests over code that never executes in production.

The Intercom integration is otherwise fully operable (token-paste + pull + webhook,
shipped 2026-07-31). But the feedback loop ends at "mark resolved in Rereflect": the
support conversation stays open and un-annotated, and the operator's only way to close it
is to go back into Intercom. The landing page's "Two-Way Sync" claim was removed because
it never worked (CHANGELOG.md:348-350), and DEV-TRACKING.md:514 pins the rule: **no
"Two-Way Sync" copy may return until the write-back is wired.**

This card is the P2 wire-or-delete decision. **Decision: wire it** — in the right
process (worker-service, where every outbound writeback lives), with the right error
taxonomy (the worker's `IntercomClient`, not the backend module's `bool`-swallowing).

### Evidence it's real

- Orphan confirmed by grep: only tests import `intercom_service` (backend dig, 2026-08-14).
- `docs/SELF_HOSTING.md:1752` states "**No write-back.** Rereflect does not add notes to
  or close Intercom conversations." — the operator-facing gap this feature closes.
- `docs/planning/intercom-selfhost-ingestion/prd.md:294-297` scoped write-back out with
  the same wire-or-delete pointer.

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| Resolve closes the loop | An Intercom-sourced feedback transitioning to `resolved` (with write-back enabled) produces exactly one note on the linked conversation and closes it — verified by tests |
| No dead dispatch path | A seam test asserts every status-change call site actually dispatches the write-back task (the "silently never fires" guard family) |
| No duplicate notes | Re-resolve after reopen, task retry, or crash-between-call-and-marker never appends a second note |
| Honest failure | 403 (missing scope) → recorded `missing_write_scope`, **never** auto-disables; 404 (already closed/not found) → noop; 429/5xx → bounded retry |
| Operator-visible state | `last_writeback_at/status/error` on the Intercom settings page, and an `intercom_writeback` event on the Customer 360 timeline |
| Honesty maintained | "Two-Way Sync" claim returns only in the form the shipped feature actually supports (note + close, opt-in, off by default) |

Non-goals for metrics: adoption numbers (single-tenant OSS; not collected).

## User Personas & Scenarios

- **CS operator resolving an Intercom-sourced complaint in Rereflect.** Marks it resolved
  (feedback detail action, bulk workflow status, or public API). The linked Intercom
  conversation gets a note (their resolution note, or a default) and is closed, so the
  support team sees the outcome where they work.
- **Self-hoster who enables it by accident.** The toggle is off by default, the card
  copy states exactly what it does (note + close on resolve), and a token without
  `conversation:write` scope produces a visible `missing_write_scope` status rather than
  silence or a disabled integration.
- **Operator who dislikes auto-close.** `action: note_only` keeps the note and leaves
  closing to the support team.

## Requirements

### Must-have

**R1 — Per-org opt-in config, off by default.** New columns on `IntercomIntegration`
(backend + worker mirror, parity-tested): `writeback_enabled` (Bool, default `false`),
`writeback_action` (String, default `"note_and_close"`; allowed `"note_only"` |
`"note_and_close"`), `last_writeback_at`, `last_writeback_status`,
`last_writeback_error`. Mirrors the CRM writeback column set
(`hubspot_integration.py:39-44`, `salesforce_integration.py:41-45`).

**R2 — Trigger = transition INTO `resolved`, only for Intercom-sourced items.**
Fire only when a feedback with `source == "intercom"` transitions `→ resolved`
(observable from the changed pairs of `apply_status_change`, or the caller-known old/new
status at worker writers). No-ops, same-value re-saves, and non-Intercom items never
dispatch. Target status is **fixed to `resolved` in v1** (OQ1).

**R3 — Worker task `src/tasks/intercom_writeback.py`** with the extracted-`_body`
pattern (hubspot/salesforce writeback precedent). Per feedback id:
1. Guard chain (each → `noop`, nothing sent): no Intercom connection for the org (both
   credential paths checked), `writeback_enabled` false, item not Intercom or no
   `conversation_id` in `source_metadata`, marker already set (`intercom_writeback_at`).
2. Resolve credential: token-paste `IntercomIntegration` row first, else legacy
   `Integration(type="intercom")` OAuth row (the source_events.py OR-clause precedent,
   :190-227). Decrypt via the worker's `_decrypt` mirror; missing
   `LLM_ENCRYPTION_KEY` → `error/missing_encryption_key`, no retry (R6 contract from the
   writeback precedents).
3. Admin id: stored `admin_id` (token-paste row or OAuth `config["admin_id"]`); if
   absent, `fetch_admin_id` fallback via `GET /me`.
4. Act per `writeback_action`: **note first** (body = `resolution_note` from the
   transition, else default `"Marked resolved in Rereflect."`), **then close** (when
   `note_and_close`).
5. Error semantics: 401/403 → record `missing_write_scope` (or `auth_error`) on
   `last_writeback_status`, **never** flip `is_active` (soft-pause precedent); 404 on
   note/close → `noop/already_closed` (close is idempotent-by-404); 429/5xx → retry
   (max 3, delay 30 — the writeback precedents' `task_self.retry` shape).
6. On success: set `feedback_items.intercom_writeback_at` (the durable marker — see
   R4), update `last_writeback_at/status/error` on the integration row, write one
   `intercom_writeback` `FeedbackWorkflowEvent` (R5).
7. **Never raises.** The task body contract is best-effort with recorded failure
   (CRM writeback precedent).

**R4 — Durable per-feedback idempotency marker.** New nullable
`feedback_items.intercom_writeback_at` (timestamptz), backend + worker model, one
migration chained off current head `3cb9a0d1456b`. Set after the action completes;
checked before acting (skip → `noop/already_written`). This is what makes a re-resolve
after reopen a no-op (the conversation is already closed; a second note would be noise)
and bounds crash-window duplicates (see Honest limits).

**R5 — Timeline event.** `FeedbackWorkflowEvent(event_type="intercom_writeback")` with
`metadata={source: "intercom", action, note_sent: bool, closed: bool, reason?}` written
by the worker task; `customer_timeline_service` gains a fetcher mirroring
`_fetch_status_changed` (:256-260) so it renders on Customer 360.

**R6 — Dispatch at every writer that can resolve an Intercom-sourced item.**
- Backend (post-commit, fire-and-forget, never raise — the `dispatch_status_webhooks`
  shape, workflow_service.py:53-78): a shared `dispatch_intercom_writeback(db, org_id,
  changed_pairs)` helper called from **all three** `apply_status_change` call sites —
  `workflow.py change_status` (:160), `public_api.py` bulk (:533) and single (:710).
  Payload: `[{"id": int, "resolution_note": str|None}, ...]` per changed Intercom item.
- Worker (direct `delay()` on the task): `playbook_engine._handle_change_status`
  (:259-279) and `automation_feedback_trigger._execute_change_status` (:601-614) —
  when the new status is `resolved` and the item is Intercom-sourced. These two writers
  currently emit no `status_changed` event; the write-back dispatch is additive.
- Seam tests mirroring `test_usage_trend_trigger_seam.py` assert **each** of the five
  call sites actually dispatches.

**R7 — Config API.** `PATCH /api/v1/integrations/intercom/writeback`
(`require_admin_or_owner`, 404 when no connection) body
`{enabled: bool, action?: "note_only"|"note_and_close"}` — 422 on invalid action,
`extra="forbid"`. `GET /status` extended with the five writeback fields. **No
backfill-on-enable** (see OQ2).

**R8 — Worker client methods.** `IntercomClient` (`src/clients/intercom.py`) gains
`add_note(conversation_id, admin_id, body)` (POST `/conversations/{id}/reply`,
`message_type=note`) and `close_conversation(conversation_id, admin_id)` (POST
`/conversations/{id}/parts`, `message_type=close`), plus `fetch_admin_id()`, using the
existing error taxonomy (IntercomAuthError / IntercomTransientError; 404 distinguished
as "not found / already closed"). **Delete** the orphaned backend
`intercom_service.py` and its tests (`test_intercom.py:590-684`) — behavior ports into
the client with the taxonomy the backend module lacked.

**R9 — Frontend card.** `IntercomWritebackCard` on
`settings/integrations/intercom/page.tsx`, mounted between the Connection card (:167-235)
and the webhook card (:237-286), gated `status?.connected && isAdminOrOwner`
(HubSpotWritebackCard precedent: never-optimistic PATCH → refetch → `onStatusChange`;
Switch + action selector + status grid + destructive error line). Honest copy: what it
does (note + close on resolve), the scope requirement (`conversation:write`), and that
it is off by default. `lib/api/intercom.ts` gains `updateWriteback` +
`writeback_*` status fields (hubspot.ts:166-183 precedent).

**R10 — Docs & tracking (part of "done").** `SELF_HOSTING.md:1752` "No write-back" line
→ new subsection (enable, scope, honest limits); CHANGELOG entry; DEV-TRACKING P2 →
FIXED with shipped summary + the `intercom-writeback` deferred-v2 entry → SHIPPED.
No landing-page copy change (OQ3).

### Should-have

- **S1 — `POST /writeback/test`**: on-demand token + scope probe (mirror the CRM
  `/writeback/test`) returning `{ok, reason}` so an operator can verify scope before
  enabling. Cheap; include if it doesn't bloat the slice.

### Nice-to-have (explicitly deferrable)

- **N1 — Configurable target status** (allow `closed` alongside `resolved`).
- **N2 — Configurable note template** (org-level footer/branding).
- **N3 — Comment reply channel** via the existing `response_sender.send_via_intercom`
  (separate surface; see Out of scope).

## Technical Considerations

- **Services:** worker-service (task + client + model mirror + dispatch in two worker
  writers), backend-api (columns, migration, routes, dispatch helper + 3 call sites,
  timeline fetcher), frontend-web (card + api client). Analysis-engine untouched.
- **Migration:** one new head chained off `3cb9a0d1456b` (current single head — CI
  asserts `alembic heads` prints exactly one): `feedback_items.intercom_writeback_at` +
  the five `IntercomIntegration` columns. Worker model mirrors both (parity test in
  `test_intercom_tenancy_discriminator.py`).
- **Two credential paths** (D4): token-paste `IntercomIntegration` (per-org, unique
  constraint) or legacy OAuth `Integration(type="intercom")` row (write-only, slated for
  retirement). Both tokens are Fernet-encrypted (P1 FIXED, merged `737bbd5`); the stale
  "plaintext" comment at `models/integration.py:19-25` is wrong — treat as encrypted.
- **Why the task lives in worker-service:** the worker image copies only
  `worker-service/src` + `analysis-engine/src/analyzer` (Dockerfile:47-54); all
  outbound writebacks (`hubspot_writeback.py`, `salesforce_writeback.py`,
  `outreach_sender.py`) run there. Backend routes only **dispatch** via `send_task`.
- **Idempotency model:** transition-only firing + durable marker (R4) + close-is-404-idempotent.
  No Redis key needed (Redis is best-effort by convention; a note that must not duplicate
  needs DB truth — CRM `last_written_health_score` precedent).
- **`conversation_id` availability:** present in `source_metadata` for both pull and
  webhook items (`adapters/intercom.py:124-129,139,157`); `source_external_id` is the
  conversation id (or `conv:part`) — the marker column is the cleaner anchor, no lookup
  needed.
- **RBAC:** all new routes `require_admin_or_owner` (the existing Intercom router
  precedent); no plan gate (`SELF_HOSTED=true`).

### API Contracts (summary)

| Method | Path | Auth | Notes |
|---|---|---|---|
| PATCH | `/api/v1/integrations/intercom/writeback` | admin/owner | `{enabled, action?}`; 422 invalid action; 404 no connection |
| POST | `/api/v1/integrations/intercom/writeback/test` (S1) | admin/owner | `{ok, reason}` scope probe |
| GET | `/api/v1/integrations/intercom/status` (extended) | admin/owner | + 5 writeback fields |

## Risks & Open Questions

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Worker-side automation/playbook writers emit no `status_changed` event today** — a future refactor of those writers could silently drop the dispatch | Seam tests pin all five call sites; the dispatch is a one-line additive call at each |
| R2 | **Token lacks `conversation:write` scope** — every resolve errors | `missing_write_scope` recorded on the row and shown in the UI; never auto-disable; S1 test endpoint lets operators verify before enabling |
| R3 | **Auto-close surprises a support team** ("who closed this?") | Off by default; explicit card copy; `note_only` escape hatch; the note itself names Rereflect as the source |
| R4 | **Reopen → re-resolve cycle** | Marker makes the second resolve a `noop/already_written` — conversation already closed, a second note would be noise |
| R5 | **Crash between call and marker write** duplicates a note on retry | Seconds-wide window, documented in Honest limits; close is 404-idempotent so the retry's close is a noop; the note is the only (cosmetic) duplicate risk |
| R6 | **Legacy OAuth row decrypt failure / stale token** | Recorded as `auth_error` on the row; soft-pause; no cascade |

**Open questions**
- **OQ1 — Target status fixed to `resolved`?** The card said "(or configured target
  status)". `closed` is a rare manual terminal in Rereflect's workflow and adds a
  validation surface. *Leaning: v1 fixed to `resolved`; `closed` as N1.*
- **OQ2 — No backfill-on-enable?** Enabling write-back must NOT mass-close
  already-resolved conversations (a stampede + surprise). The CRM writebacks backfill
  because health scores are continuous; a conversation close is one-shot. *Leaning:
  explicitly no backfill; state it in the card copy.*
- **OQ3 — Landing page copy?** The Intercom entry in
  `services/landing-web/lib/integrations.ts:136-171` is OAuth-era stale (claims OAuth-only
  setup + webhook-only ingestion — false since token-paste + pull shipped). Refreshing it
  is a separate chore (the "Two-Way Sync" discipline applies: claim only what shipped).
  *Leaning: separate chore, not this card.*

## Out of Scope

- **Backfill-on-enable** (OQ2 — one-shot closes must not be mass-applied).
- **Configurable target status (`closed`)** and **note templates** (N1/N2).
- **Comment reply channel** (the `response_sender.send_via_intercom` comment path is a
  separate surface with its own issues — `_get_integration_token` is broken for
  Intercom; not this card).
- **Intercom pull-replies-and-ratings, backlog-drain visibility, OAuth-path
  retirement** — the other three Intercom v2 deferrals, separate slices.
- **Landing-page copy refresh** (OQ3) and the stale `models/integration.py:19-25`
  comment fix (separate chore).
- **Zendesk/Jira/Asana write-backs** — this card is Intercom-only; the shared shapes
  (marker column, dispatch helper) make those natural follow-ons.
- **No plan gate** (`SELF_HOSTED=true`), no new scopes, no Redis-cooldown scheme changes.

## Honest limits (state in docs + card copy)

- The write-back fires on **transitions after enable** — conversations already resolved
  before enable are never touched.
- `resolved` is the only trigger in v1.
- A crash in the seconds between the Intercom call succeeding and the marker write can
  duplicate a note on retry (close remains a noop). Cosmetic, bounded, documented.
- Scope (`conversation:write`) is a property of the operator's Intercom app; Rereflect
  reports its absence, it cannot grant it.
- No claim about response time: the dispatch is post-commit fire-and-forget; the note
  lands when the worker picks up the task.

## Self-critique (Phase 4)

- 🔴 **No real-org usage evidence.** Firing rate, note-content usefulness, and whether
  `note_only` is ever chosen are reasoned, not measured — the defaults (`note_and_close`,
  resolution-note-or-default) are a starting point the operator can change. Off-by-default
  is the mitigation; the card must not pretend the defaults are calibrated.
- 🟡 **Five dispatch points is the risky surface.** The whole feature fails silently if
  any one site drifts. The seam-test family mitigates, but the write-back's "done" must
  explicitly include the seam tests for all five — otherwise this card ships the exact
  defect class it exists to fix.
- 🟢 Credential resolution, idempotency, soft-pause, and UI all mirror shipped
  precedents with tests to copy.

**The question I'd want answered before greenlighting:** the user-facing value of the
note depends on the resolution note being present — how often does anyone actually fill
the resolution note in Rereflect today, and is "Marked resolved in Rereflect." enough
when they don't?

---

## Decision Record (close-out, 2026-08-16)

- **P2 `intercom-writeback-orphaned` — decision executed: wire it.** The orphaned
  `intercom_service.py` is deleted; its behavior is ported into the worker's
  `IntercomClient` (`add_note`, `close_conversation`, `fetch_admin_id`, 404 →
  `IntercomNotFoundError`). See the FIXED P2 in DEV-TRACKING.md (merge
  (merge-sha pending), PR # pending).
- **OQ1 — target status fixed to `resolved`: shipped.** `closed` stays a manual
  terminal; configurable target status remains N1.
- **OQ2 — no backfill-on-enable: shipped.** Only transitions after enable fire;
  stated in the card copy, SELF_HOSTING.md and the CHANGELOG entry.
- **OQ3 — landing page: flagged, not shipped.** The stale OAuth-era Intercom entry
  (`services/landing-web/lib/integrations.ts:136-171`) is a follow-up chore
  (`landing-intercom-entry-refresh`), respecting "claim only what shipped".
- **Aspects (all shipped 2026-08-16; merge pending):** `db-config-model`,
  `config-api-routes`, `dispatch-seams`, `worker-write-client`,
  `worker-writeback-task`, `frontend-writeback-card`, `docs-tracking-changelog` —
  each with its spec and plan under `docs/planning/intercom-writeback/`.
- **Honest limits as shipped:** transitions after enable only; `resolved` the only
  trigger; fire-and-forget dispatch (no response-time claim); a crash between the
  Intercom call and the marker write can duplicate a note on retry (close stays a
  no-op); `conversation:write` is the operator's to grant — Rereflect reports its
  absence and never auto-disables the integration.
