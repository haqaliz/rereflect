# PRD — Copilot truthfulness (docstring, regenerate, usage, report errors)

**Slug:** `copilot-truthfulness` · **Branch:** `bug/copilot-truthfulness`
**Type:** bug · **Created:** 2026-10-21
**Card:** `docs/planning/_card/card.md` (issues #35, #36, #37, #38)

Four small defects in the copilot surface, all one theme: the code advertises
behaviour it does not deliver. Grouped into one PR because they touch the same
files (`copilot_ws.py`, `useCopilotWebSocket.ts`, copilot UI/tests).

---

## 1 — #35: docstring advertises a nonexistent endpoint

**Problem.** `services/backend-api/src/api/routes/copilot.py:5` lists
`POST /api/v1/conversations/suggestions`. No such route exists (the only copilot
REST route in the module is `GET /api/v1/copilot/usage`).

**Requirement.** The docstring lists only routes registered by the module. No
behaviour change. (Note: the frontend still calls that URL from
`conversationsAPI.getSuggestions` and swallows the 404 — out of scope here per
the issue; flagged in the PR, not fixed in this PR.)

**Acceptance.** Docstring matches registered routes.

## 2 — #36: regenerate is public but always errors

**Problem.** `useCopilotWebSocket` exposes `regenerate()`, ChatArea wires it to a
Regenerate button on every assistant message, and the backend replies
`"Regenerate not yet implemented"` every time. The regenerate button is a shipped
path that cannot succeed; removing it breaks nothing that works.

**Requirement (locked: remove, do not implement).** Remove `regenerate` from the
hook's public return type/implementation, from ChatArea, MessageBubble and
MessageActions, and from the backend protocol docstring + the dead `regenerate`
message branch (which only ever produced the error). Unknown-type suggestion
becomes `query, stop`. Tests that exercised regenerate are replaced with one
asserting the hook no longer exposes it.

**Out of scope.** Implementing regeneration; the `is_regenerated` DB column
(unused, harmless).

**Acceptance.** No hook/UI/backend public surface advertises regenerate; tests
updated; no call path that always errors.

## 3 — #37: usage counters always zero

**Problem.** `_handle_query` initialises `tokens_in/tokens_out/cost_cents` to
0/0/0.0 and never assigns them, so the final `stream{done:true}` frame always
reports zero, and `ConversationMessage.tokens_in/out` is persisted as NULL. The
AI Settings token-budget bars read `GET /api/v1/copilot/usage`, which sums those
columns — hence a constant zero, not a measurement.

**Requirement (locked: thread real usage).** The LLM stream is OpenAI-compatible.
Request `stream_options={"include_usage": True}`; the provider then sends a final
chunk carrying `usage.prompt_tokens` / `completion_tokens`. Read that chunk and
put the real counts in the frame and the persisted message. Cost: look up
`LLMModelPrice` by `(provider, model)`; when there is no price row (local models,
unlisted models) report `cost_cents: null` — unknown, not a fake zero. If the
server rejects `stream_options`, retry once without it; usage stays unknown
(`null`) rather than lying.

**Out of scope.** New pricing tables, per-user attribution changes, UI redesign.

**Acceptance.** Final frame and persisted message carry the provider-reported
counts for a normal completion; `cost_cents` is computed from the price table
when known and `null` otherwise; a test fails if the counters are hardcoded.

## 4 — #38: report branch errors bypass the manager

**Problem.** `_handle_query`'s report branch (`copilot_ws.py:471-483`) sends the
"no AI model configured" error with raw `websocket.send_json` and no
`message_id`. Every other path uses `manager.send` and includes `message_id`, so
a client correlating errors to turns loses this one (and it bypasses the
manager's connection bookkeeping).

**Requirement.** Both error sends in the report branch use `manager.send` and
include `message_id`.

**Acceptance.** One test covering the report-branch error shape (type, error
text, message_id).

---

## Cross-cutting constraints

- Minimal diffs, no new dependencies, no unrelated files.
- Backend tests: pytest in `services/backend-api`; frontend: vitest in
  `services/frontend-web`.
- Commits per logical change, conventional commits referencing the issues.

## Risks

- `stream_options` support varies across OpenAI-compatible servers. Mitigated by
  the single retry-without fallback; unknown usage is `null`, never 0.
- Removing the Regenerate button is a visible UI change. Intended: the button
  could not work.
- `cost_cents` becomes nullable in the frame. Nothing reads it today (the
  frontend hook ignores metadata; `ConversationMessage.cost_cents` is already
  nullable), so no consumer breakage.
