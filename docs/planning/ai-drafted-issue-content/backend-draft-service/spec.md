# Aspect Spec — backend-draft-service

**Feature:** ai-drafted-issue-content · **Aspect:** backend-draft-service

## Problem slice & outcome
A single shared backend service + endpoint that turns a feedback item into a `{title, body}` draft for a
target work tracker (Jira/Asana), reusing the existing LLM resolution/call path. Graceful 409 when no LLM.

## In scope
- `POST /api/v1/feedback/{feedback_id}/issue-draft` (JWT, `require_admin_or_owner`) → `{title, body}`.
- New service `src/services/issue_drafter.py`: gate via `resolve_generation_llm`, build prompt from feedback +
  org context, call the LLM (mirror `copilot_ws.call_llm_stream` non-streaming), parse `{title, body}`, log usage.
- `LLMUsageLog` row with `task_type="issue_draft"` (no migration — column is String(30)).
- Prompt hardening for untrusted feedback text (E1).

## Out of scope
- Frontend wiring (separate aspect). Auto-create. New providers. ADF conversion (stays in the create route).

## Acceptance criteria (testable)
1. Configured org + valid feedback + `target=jira` → 200 `{title, body}` (both non-empty).
2. `resolve_generation_llm(...).is_configured == False` → **409**, honest message, **no** provider call.
3. Feedback id not in caller's org → 404.
4. `target` not in {jira, asana} → 422.
5. Non-admin/owner member → 403 (mirror create-route auth).
6. Malformed/empty model output → clean 502 (not 500), no partial write.
7. On success, exactly one `LLMUsageLog(task_type="issue_draft")` row written for the org.
8. Injection-style feedback text is treated as data (test asserts the system prompt delimits/labels it).

## Dependencies & sequencing
- Depends on: `resolve_generation_llm` (exists), `openai` SDK (exists), `LLMUsageLog` (exists), `FeedbackItem`.
- Blocks: frontend-draft-button (needs the endpoint contract), docs-and-tracking.

## Open questions / risks
- **T2** (frontend gate) is a frontend concern; backend just returns 409 honestly.
- `estimated_cost_cents` is NOT NULL on `LLMUsageLog` — use existing pricing lookup (`llm_model_price`) if
  trivially available, else `0.0` (local/unknown models legitimately cost 0). Confirm in plan.
