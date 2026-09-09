# PRD: AI Copilot Suggested Actions

**Slug:** `copilot-suggested-actions` · **Branch:** `feat/copilot-suggested-actions` · **Date:** 2026-09-06
**Type:** feat (freeform) · **Source:** `rereflect-next` recommendation + user-confirmed scope
**Inputs:** `docs/planning/_card/card.md`, `docs/planning/_card/understanding.md`

## Problem Statement

The AI Copilot can answer any question about an org's feedback and can do nothing about the
answer. A CS lead asks "which customers mentioned billing friction this month?", gets a
correct table of three customers — and then leaves the conversation to go tag them by hand on
`/customers`. Every insight the copilot produces ends in manual re-work somewhere else in the
product.

**For whom:** the CS manager / founder personas the copilot was built for — the people who
already use `/conversations` to triage, and who own the follow-through.

**Evidence it's real:**
- The intended shape was locked as a strategic decision and never built:
  `AI-TRACKING.md:25` — *"Copilot actions | Read + suggest actions (user clicks to execute)"*.
- It was deferred by scope, not by a blocker: `docs/archive/prd/PRD-AI-COPILOT.md:33` —
  *"No action execution (read-only — no mutations, no status changes, no assignments)"*.
- The gap is still open in code: `copilot/intent_classifier.py:115` classifies only
  `data | analysis | general | report`, and `src/services/copilot/` contains no executor or
  registry module.
- Meanwhile every executor a user would want has shipped: bulk cohort actions
  (`AI-TRACKING.md:346`), playbooks (`M4.1.5`, `AI-TRACKING.md:381`), the public write scope
  (`AI-TRACKING.md:456`). The copilot is the only surface that cannot reach them.

**Honest framing of demand.** No user has asked for this. The source is a `rereflect-next`
roadmap recommendation, and the only recorded post-1.0.0 user feedback
(`DEV-TRACKING.md:714-726`) is seven comments about privacy / BYOK / no-telemetry — none about
the copilot. This is a **capability bet derived from the roadmap**, not a demand-driven
feature, and it should be judged as one. What justifies it is not evidence of ask, but that
the decision was already locked (`AI-TRACKING.md:25`), every executor it needs already exists,
and the wire format already supports it — so the cost is small and the loop it closes is the
product's stated moat.

**What makes it more than a shortcut.** A user who wants three customers tagged can already do
it on `/customers` in two clicks: filter, select, bulk-tag. The action only earns its place
because it operates on **the result set of the question just asked** — an arbitrary set that
no `/customers` filter can express (e.g. "customers whose feedback mentioned billing friction
*and* whose sentiment dropped this month"). That is the design constraint driving M9 below.

## Goals & Success Metrics

**Goal:** close the loop between what the copilot *knows* and what the product can *do*, with
one action type proven end-to-end and a registry the remaining actions can be added to.

| # | Success criterion | How it is measured |
|---|---|---|
| S1 | A data/analysis query whose result is a customer list offers a tag action | Test: query returning ≥1 customer-email column emits an `actions` item |
| S2 | Clicking it applies the tags and reports what changed | Test: execute → `BulkActionSummary{matched, updated, skipped, errors}` surfaced to the user |
| S3 | A `member` is refused **server-side** | Test: member JWT → 403 from the execute route, even though some sibling routes would allow them |
| S4 | Every execution is auditable | Test: one `AuditLog` row per execution, with action, target and params in `details` |
| S5 | The cross-end seam cannot ship dead | One committed golden fixture asserted by **both** the backend and frontend suites |
| S6 | No regression in existing rendering | Existing table/chart tests stay green; queries that emit no actions behave exactly as today |

**Non-goal metrics:** no adoption or usage targets. This is a capability slice; success is a
working, honest, reversible first action.

## User Personas & Scenarios

- **CS manager (primary).** Asks "which customers mentioned billing friction this month?",
  sees the three-row table, clicks **Tag these 3 customers…**, types `billing-friction`,
  confirms. The tags are applied and the copilot reports `3 matched, 3 updated`.
- **Member (read-only-ish role).** Asks the same question, gets the same answer and table. The
  action is not offered; if they reach the endpoint directly they get a 403.
- **Self-hoster on a local model.** Runs Ollama with no API key. The proposal is computed
  server-side from the result shape, so the action appears identically — it does not depend on
  the model being strong enough to emit a tool call.

## Requirements

### Must-have

- **M1 — Action registry.** A server-side registry of permitted actions. Each entry declares:
  a stable `action` id, a `min_role`, a params schema, and the executor it calls. The registry
  is the only thing that can be executed; an unknown `action` id is rejected. The model never
  names an executor. This mirrors the read path's constrain-the-LLM precedent
  (`sql_validator.py` + `schema_whitelist.py`).
- **M2 — Deterministic proposer.** After a `data`/`analysis` query returns rows, the server
  inspects the **result shape** (columns/types) and appends matching registry actions. No LLM
  is involved in producing a proposal. Slice-1 rule: a result carrying a customer-email column
  offers `tag_customers`.
- **M3 — `actions` item on the existing wire format.** Proposals ride the existing
  `structured_data` array as `{"data_type": "actions", "data": {...}}` — matching the envelope
  `format_table`/`format_chart` already produce (`response_formatter.py:58-61`, `:171-174`).
  No new frame type, no protocol change, no migration.
- **M4 — Execute endpoint.** A new authenticated route that takes an action id + params,
  validates against the registry, enforces `min_role`, resolves the org from the user row,
  calls the existing executor, and returns its result. It is a normal REST route — **not** a
  WebSocket message — so it gets ordinary FastAPI auth, RBAC and testing.
- **M5 — Uniform registry RBAC.** `min_role` is enforced at execute time by the registry,
  independent of what the underlying route permits. For slice 1 this matches the executor
  (`bulk/tags` is already `require_admin_or_owner`, `customers.py:692`), so there is no
  asymmetry in this slice — but the policy is set here for the actions that follow.
- **M6 — User supplies the payload.** The tag value comes from the user in a confirm dialog,
  never from the model or from a server guess. The proposal offers *which customers*; the user
  provides *which tag*.
- **M7 — Audit.** Every execution writes an `AuditLog` row via the existing generic
  `audit_service.log_action` (`action`, `target_type`, `target_id`, `details`, IP/UA from the
  `Request`). No new table, no migration.
- **M8 — Golden fixture.** One committed fixture of the `actions` item, asserted by the
  backend suite ("this is what I emit") and the frontend suite ("given this, I render N
  buttons"), following the established cross-seam pattern
  (`services/worker-service/tests/fixtures/intercom_webhook_envelope.json`).
- **M9 — The proposal is a frozen, one-shot artifact.** A proposal is written into
  `ConversationMessage.structured_data` and lives in the conversation indefinitely, so it must
  be safe to encounter later:
  - **Frozen cohort.** The item embeds the **resolved customer emails** from the result the
    user actually saw — not a re-runnable filter. Acting on a different set than the one on
    screen would be worse than acting on a stale one. Emails that no longer belong to the org
    are absorbed by `resolve_cohort` as `skipped`, not errors (`cohort_service.py:47-48`), and
    that count is reported back.
  - **One-shot.** Each proposal carries a stable `proposal_id`. The execute route refuses a
    second successful execution of the same `proposal_id` and returns the prior outcome
    instead. Enforced **server-side**; the frontend disabling the button is cosmetic.
  - **Bounded.** The embedded email list is capped, and a result larger than the cap offers no
    action rather than a silently truncated one.

### Should-have

- **S1 — Honest empty state.** When a result shape matches no registry action, nothing is
  emitted and the message renders exactly as it does today.
- **S2 — Report the outcome.** After execution the user sees the `BulkActionSummary` counts,
  including `errors[]` (e.g. the 20-tag cap message), not just a success toast.
- **S3 — Idempotence is visible.** `bulk/tags` uses set-union, so re-adding an existing tag
  counts toward `updated`. The UI copy must not over-claim ("3 updated" when nothing changed).

### Nice-to-have

- **N1 — Frontend hiding by role.** Hide the action for non-admins client-side as a courtesy.
  Explicitly **cosmetic** — enforcement is M5, server-side. No copilot component reads `role`
  today.

## Technical Considerations

**Services changed:** `services/backend-api` and `services/frontend-web` only. **The worker is
not involved** — the tagging executor is synchronous and in-process, so this feature does not
cross the backend/worker boundary and is not exposed to the duplication trap documented in
`docs/planning/automations-delivery-integrity/`.

**Multi-tenancy:** org identity comes from the user's DB row, never a JWT claim
(`dependencies.py:99`, `copilot_ws.py:128-145`), and `resolve_cohort` scopes to the org
internally (`cohort_service.py`), skipping unknown/foreign emails rather than erroring. There
is no org id to forge.

**No migration.** `ConversationMessage.structured_data` is `Column(JSON)`; `AuditLog` is
already generic.

**Insertion point.** The proposer hooks into `_handle_query` between the structured-data build
(`copilot_ws.py:622-638`) and the emit (`:775-783`). Note the `general` intent branch never
enters that section at all, so actions are inherently scoped to `data`/`analysis`.

**Behavioural change to watch.** `structured_data_payload` is truthiness-gated at `:775` and
`:785`. Queries that today produce an empty list and skip the frame will begin emitting a
frame once an actions item is appended. Intended, but it needs an explicit test.

**Executor contract (slice 1).** `POST /api/v1/customers/bulk/tags` (`customers.py:689`):
`BulkTagRequest{cohort: Cohort, tags: List[str], mode: Literal["add","remove"]}` →
`BulkActionSummary{matched, updated, skipped, errors}`. Tags are trimmed, de-duped and capped
at 50 chars (422 on violation); 20 tags per customer enforced per-row at apply time.
**Tags are case-sensitive** — `"Churn"` and `"churn"` are distinct.

**Sanitisation gap to respect.** `sanitize_markdown` runs only on `text`
(`response_formatter.py:305`); nothing sanitises `structured_data` at any layer. Customer
emails flow into the actions item and become button labels — the frontend must render them as
text, never as markup.

**Silent-skip hazard.** `MessageBubble.tsx:269-282` skips unrecognised `data_type` values with
no error. This is the reason M8 is a must-have rather than a nice-to-have.

## Data Model

None. No new tables, no new columns, no Alembic revision. `alembic heads` must still print
exactly one head.

## API Contracts

- **New:** one execute route under the copilot/conversations namespace — action id + params in,
  executor result out. Registry-validated, `min_role`-enforced, org-scoped, audited.
- **Unchanged:** `POST /api/v1/customers/bulk/tags` is called as the executor. Its contract is
  not modified.
- **Unchanged:** the `/ws/copilot` frame types. The `actions` item is a new `data_type` inside
  the existing `structured_data` payload.

## Risks & Open Questions

| Risk | Severity | Mitigation |
|---|---|---|
| Ships dead — backend emits, frontend silently skips | **High** | M8 golden fixture asserted by both suites. This exact class has shipped 4× in this repo (`DEV-TRACKING.md:433`) |
| Registry `min_role` diverges from the executor's own gate as more actions are added | Medium | Registry declares `min_role` explicitly per entry; a test asserts every entry's `min_role` is ≥ its executor route's dependency |
| Users read a proposal as a recommendation ("the AI thinks I should tag these") | Medium | Copy states it plainly as an action on the current result set, not advice |
| `structured_data` is unsanitised and untyped end-to-end | Medium | Render all item values as text; keep the item's `data` to server-derived values only |
| Case-sensitive tags produce confusing no-op removes | Low | Slice 1 is `mode="add"` only; removal is out of scope |
| A proposal is clicked days later, against a changed world | Medium | M9: frozen email cohort, departed customers absorbed as `skipped` and reported |
| The same proposal is clicked twice (double-click, or on revisit) | Medium | M9 one-shot guard, enforced server-side; second attempt returns the prior outcome |
| The feature demos well and is never used | Medium | Accepted and stated: this is a roadmap capability bet, not demand-driven. The result-set cohort is what gives it a reason to exist over the existing `/customers` path |

**Open questions:**
1. Should the execute route live under `/api/v1/copilot/...` or `/api/v1/conversations/...`?
   (Leaning copilot; `copilot.py` currently holds only `GET /usage`.)
2. **How is M9's one-shot guard stored — and which `message_id` is it keyed on?** The WS
   `message_id` (`copilot_ws.py:913`, `message.get("message_id", str(uuid.uuid4()))`) is a
   **client-supplied streaming-turn id**, not `ConversationMessage.id`: the row id is assigned
   at commit in step 12 (`:785-810`), *after* the structured-data frame carrying that
   `message_id` is already emitted in step 11 (`:775-783`). It is caller-controllable — a
   client can send any string, or omit it and get a fresh UUID every time. The golden fixture's
   `proposal_id` (`"msg-42:tag_customers:4a72f4"`) bakes in exactly this ambiguous id, though
   the contract itself is unaffected since `proposal_id` is opaque there.
   Two migration-free storage options: (a) derive the guard from `AuditLog` — write
   `target_type="copilot_action"`, `target_id=<?>`, `details.proposal_id`, and check for a
   prior successful row before executing; or (b) write an `executed` flag back into the item's
   JSON, which makes `structured_data` mutable and racy under concurrent clicks. **Leaning
   (a)**, but option (a) must NOT set `target_id` to the WS `message_id` — it references no
   `ConversationMessage` row and is chosen by the caller, which would let a client mint a fresh
   one-shot slot at will by resending a different `message_id`. Key the guard on
   `proposal_id` alone (already embeds the server-derived cohort hash) or on the persisted
   `ConversationMessage.id` looked up after commit, never on the raw wire `message_id`.
   `action-registry` must not inherit this ambiguity silently.
3. Does the proposer offer the action when the result has a customer-email column but only one
   row, or require ≥2? (`include_table` already gates at `row_count >= 2`.)
4. What is M9's email cap — the 50-row `MAX_TABLE_ROWS` the table formatter already uses, or a
   lower number specific to actions?

## Rollout & Documentation

No feature flag and no migration, so rollout is the merge itself. Closing the branch follows
the house convention used by `teams-notifications`, `playbook-action-types` and
`scheduled-ai-reports`:

- **`CHANGELOG.md`** — a behaviour entry describing the new `actions` item and the execute
  route, including the honest limits (one action type; `data`/`analysis` queries only;
  admin/owner only; one-shot).
- **`AI-TRACKING.md`** — a Current AI Capabilities row, and an M2.2 follow-on marker recording
  that `PRD-AI-COPILOT.md:33`'s "no action execution" non-goal is now partially closed. The
  strategic-decision row at `:25` should be annotated as *partially delivered* — read +
  suggest is live, but only for one action type and only from a deterministic proposer.
- **`README.md` / `docs/SELF_HOSTING.md`** — what the copilot can now do and what it cannot,
  stated plainly. In particular: proposals are computed server-side from the result shape, not
  authored by the model, so they behave identically on a local keyless model.

## Out of Scope

- **LLM-proposed actions.** Slice 2, behind the same registry interface. The registry and
  execute half are built once here so the proposer can be swapped later.
- **Every action type other than `tag_customers`** — status changes, playbooks, assign-owner,
  outreach, Jira/Asana issue creation, notifications.
- **Cmd+K rendering.** The command bar renders no results today (`CommandBar.tsx:57-65`); it
  only routes to `/conversations`.
- **Fixing the repo-wide RBAC inconsistency.** The dig found most mutation routes carry no role
  dependency (`playbooks.py:496`, `workflow.py:142`, `feedback.py:715`). Real, and a separate
  branch — this feature neither depends on nor worsens it.
- **The P7 provider-abstraction refactor** (`DEV-TRACKING.md:237`).
- **Surfacing `LLMConfig.is_configured` over HTTP** to retire the duplicated client-side probe
  (`create-issue/page.tsx:236-255`, `BulkOutreachDialog.tsx:71-92`). Adjacent, additive,
  unnecessary here — the copilot already hard-requires an LLM (`copilot_ws.py:517-531`).
- **`mode="remove"`** and multi-tag payloads beyond what the dialog collects.

## Adjacent defects found during the dig (recorded, not fixed here)

Not in scope; recorded so they are not re-discovered:

1. `copilot.py:5` advertises `POST /api/v1/conversations/suggestions`, which does not exist.
2. `copilot_ws.py:991` — `regenerate` returns a hardcoded "not yet implemented" error, but the
   frontend exposes `regenerate()` in its public hook API (`useCopilotWebSocket.ts:35`).
3. `copilot_ws.py:715-717` — `tokens_in`/`tokens_out`/`cost_cents` are initialised to `0/0/0.0`
   and never assigned, so the final frame always reports zero usage.
4. `RunPlaybookDropdown.tsx:26,47` gates on `user?.plan === 'business'` — stale under
   `SELF_HOSTED`, currently harmless.
5. The report-branch error at `copilot_ws.py:471-478` is sent via raw `websocket.send_json`
   with no `message_id`, unlike every other error which goes through `manager.send`.
6. `AISettings.has_custom_key` is dead on the wire — zero backend hits.
