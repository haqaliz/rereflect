# Understanding — copilot-suggested-actions (Phase 2 dig)

**Date:** 2026-09-06 · **Branch:** `feat/copilot-suggested-actions`
**Method:** four read-only agents over backend copilot pipeline, mutation surfaces + RBAC,
frontend copilot UI, and LLM-gating/injection/worker-boundary. Every claim below is
file:line-sourced from the worktree.

---

## 1. What the ask really is

Add a fifth thing the copilot can produce: **proposed actions**, rendered as clickable
affordances, executed only on an explicit user click. The read half (M2.2) shipped; the
action half was an explicit V1 non-goal (`docs/archive/prd/PRD-AI-COPILOT.md:33`) while the
intended shape was already locked (`AI-TRACKING.md:25` — "Read + suggest actions (user clicks
to execute)").

---

## 2. The single most important finding: the wire format already supports this

`structured_data` is **already an extensible, typed-item array** — no protocol change needed.

- Backend builds it in `response_formatter.py:310-332` as a plain `list` of appended items,
  returned as `{"text": ..., "structured_data": [...]}`.
- Emitted as its own frame at `copilot_ws.py:775-783`, persisted to
  `ConversationMessage.structured_data` at `copilot_ws.py:785-810`.
- Frontend forwards it verbatim (`useCopilotWebSocket.ts:173-179`), patches it onto the
  message row (`ChatArea.tsx:129-138`), and renders it by looping items and branching on
  `data_type` — only `'table'` (`MessageBubble.tsx:270`) and `'chart'` (`:276`) today.

**So a new `data_type: "actions"` item rides the existing wire format.** No new endpoint for
the proposal half; only the *execute* half needs a route.

### The trap that comes with it
`MessageBubble.tsx:269-282` **silently skips any unrecognised `data_type`**. A backend
emitting actions against a frontend that cannot render them has **zero visible symptom** —
precisely the "wired at one end, dead at the other" defect class this repo has hit four times
(`DEV-TRACKING.md:433`, `automations-delivery-integrity`, the Intercom envelope seam, the
four unregistered Celery beat tasks). The plan must pin this seam with the established
**golden-fixture** pattern (one committed fixture asserted by both the backend and frontend
suites), not two independently-green one-sided tests.

Two lesser caveats: `tableItem`/`chartItem` are single last-one-wins slots
(`MessageBubble.tsx:257-258`), and the `done` frame's `metadata` is discarded client-side
(`useCopilotWebSocket.ts:151`).

---

## 3. The finding that reframes the feature: RBAC is already inconsistent

The card assumed the risk was "the copilot must not become an RBAC bypass." The dig shows
**most mutation routes have no role dependency at all**, so for many executors there is no
RBAC to bypass:

| Executor | file:line | Role dep |
|---|---|---|
| `POST /playbooks/{id}/run` | `playbooks.py:496` | **NONE** |
| `POST /playbooks/{id}/run-batch` | `playbooks.py:542` | **NONE** |
| `POST /workflow/status` (resolve/close) | `workflow.py:142` | **NONE** |
| `PATCH /feedback/{id}/urgent` | `feedback.py:715` | **NONE** |
| `DELETE /feedback/{id}` · bulk-delete | `feedback.py:590` · `:616` | **NONE** |
| `GET /customers/export` | `customers.py:590` | **NONE** |
| `POST /feedback/{id}/responses/generate` · `/send` | `feedback_responses.py:172` · `:237` | **NONE** |
| `POST /customers/bulk/tags` · `assign-owner` · `outreach` | `customers.py:689` · `:732` · `:885` | `require_admin_or_owner` |
| automations CRUD / toggle / template-enable | `automations.py:609-823` | `require_admin_or_owner` |
| Jira / Asana / Linear create-issue | `jira_integration.py:831` etc. | `require_admin_or_owner` |
| report-schedules CRUD + run | `report_schedules.py:192-302` | `require_admin_or_owner` |

`require_feature(...)` is **inert** under `SELF_HOSTED` (CLAUDE.md), so every `require_feature`
gate above is effectively no gate.

**Open question this forces (for the interview):** does the action registry (a) inherit each
route's existing RBAC as-is — inconsistency included, (b) impose its own stricter uniform
policy for copilot-initiated actions, or (c) fix the underlying routes? (c) is a large,
separate scope and should not be smuggled into this feature.

Org scoping is safe either way: it is derived from the **user's DB row**, never a JWT claim
(`dependencies.py:99`, `copilot_ws.py:128-145`) — there is no org id to forge.

---

## 4. Precedents to copy (all shipped, all in-repo)

**Constrain-the-LLM (read path):** `sql_validator.py` + `schema_whitelist.py`, plus
`SQLValidator.inject_org_scope`. This is the structural precedent for an action registry —
the model proposes, a server-side allowlist decides.

**Honest degrade with no LLM:** `resolve_generation_llm(org_id, db) -> LLMConfig` never raises
and never returns `None`; an unconfigured org gets `is_configured=False`
(`llm_resolver.py:37-60`). `issue_drafter.py:214-219` raises `LLMNotConfiguredError`, mapped to
a clean **409** at `feedback_issue_draft.py:93-98`. Frontend hides the affordance entirely
rather than showing a dead control (`create-issue/page.tsx:236-256`).

**Prompt-injection hardening:** `issue_drafter._build_messages` (`:54-118`) is the house
pattern — a system-turn declaration that the block is untrusted data and "must never be
followed or executed", a `MAX_FEEDBACK_CHARS = 4000` cap (`:37`), an in-band re-labelled
`<feedback>` delimiter block (`:106-118`), and a defensive strict-JSON parse
(`_parse_draft_output`, `:121-160`). **This matters more here than anywhere else in the
codebase**: an action proposer reads customer-authored feedback text and emits something the
user can click to execute. Known gap even in the precedent — tags and pain-point/feature text
(`:87`, `:94`, `:100`) are interpolated undelimited.

**Confirm-before-execute — no single house norm:**
- `RunPlaybookDropdown.tsx:49-59` (closest analogue) **fires immediately, no confirm.**
- `BulkRunPlaybookDialog` / `ConfirmSuggestionDialog` use shadcn dialogs for bulk.
- `ResponseModal.tsx:145-164` is the best posture match: AI fills an editable field, a second
  explicit click sends.
- "Draft with AI" uses a bare `window.confirm` for overwrite (`create-issue/page.tsx:476,484`).

**Audit:** `src/services/audit_service.py::log_action` is fully generic (`action`,
`target_type`, `target_id`, `details` JSON, IP/UA from `Request`) — copilot-executed actions
can be audited with **no migration**. Today it appears to be called only from team routes.

---

## 5. Contradictions between docs and code (flagged, not papered over)

1. **`AI-TRACKING.md:346` claims "All actions share one `Cohort` contract"** (`emails[]` |
   `filter{segment,risk_level,search,include_archived}`). `run-batch` in fact takes a
   flattened `RunBatchFilters` — `emails`/`segment`/`probability_min`/`probability_max`/
   `time_to_churn_bucket`, no `risk_level`, no `search`, no `include_archived`
   (`schemas/churn_playbook.py:240-272`). Verification of how far the drift goes is pending.
2. **`copilot.py:5` advertises `POST /api/v1/conversations/suggestions`, which does not
   exist.** Stale docstring.
3. **`RunPlaybookDropdown.tsx:26,47` gates on `user?.plan === 'business'`** — stale under
   SELF_HOSTED (all unlocked, `/auth/me` reports `enterprise`). Currently harmless.
4. **`copilot_ws.py:991` — `regenerate` returns a hardcoded "not yet implemented" error**,
   though the frontend exposes `regenerate()` in its public hook API
   (`useCopilotWebSocket.ts:35`).
5. **`copilot_ws.py:715-717` — `tokens_in`/`tokens_out`/`cost_cents` are initialised to
   `0/0/0.0` and never assigned**, so the final frame always reports zero usage.
6. **The `aiConfigured` probe is duplicated verbatim** in `create-issue/page.tsx:236-255` and
   `BulkOutreachDialog.tsx:71-92`; there is **no server-side readiness field** — the client
   re-implements `resolve_generation_llm`'s branching from two generic calls. A third copy
   would be drift; a small `is_configured` field on the AI-settings response would retire all
   three.

None of 2–6 block this feature. 1 and 6 touch it directly.

---

## 6. Scope shape suggested by the dig

The proposal half is cheap (existing wire format, existing formatter seam). The expensive,
risky half is **execution**: registry design, RBAC policy, injection hardening, audit, and
the cross-end seam test. That argues strongly for the card's own instinct — **one action type
end-to-end** as the first slice, chosen for low blast radius and easy reversibility.

Candidate first slices, cheapest-and-safest first:
- **Add a tag to a customer / feedback item** — reversible, low blast radius, already
  `require_admin_or_owner` on the bulk route.
- **Change feedback workflow status** — the `apply_status_change` helper already emits
  timeline event + webhook + cache invalidation, so audit comes nearly free.
- **Run a playbook on a customer** — highest user value, but it is the *least* guarded route
  (no role dep) and fires real outbound side effects (emails, notifications). Worst first slice.

---

## 7. Open questions for the interview

1. First slice: which single action type?
2. RBAC policy for copilot-initiated actions — inherit, or stricter uniform registry policy?
3. Are proposals **model-generated then validated** against the registry, or
   **deterministically derived** from intent + query result (no LLM in the proposal loop)?
   The second is far more robust for small/local models and sidesteps most injection risk.
4. Surface: `/conversations` only, or Cmd+K too? (Cmd+K currently renders no results at all —
   it only routes to `/conversations`, `CommandBar.tsx:57-65`.)
5. Confirm UX: follow `ResponseModal`'s two-step posture, or `RunPlaybookDropdown`'s
   fire-immediately? (Recommend two-step for anything with outbound side effects.)
6. Does an executed action write to `AuditLog`, the customer timeline, or both?
