# Aspect Spec — copilot-llm-local

**Parent PRD:** `../prd.md` · **Sequencing:** depends on `embedding-provider-layer`. Independent of `template-matching-local`.

## Problem slice & outcome
A keyless local-LLM org can open the Copilot and get end-to-end answers. The Copilot's
answer-generation (NL→SQL, analysis, reports) routes through the local-capable provider
selection instead of the current "BYOK key required → error" gate, with the existing SQL
safety guarantees enforced for any provider and an honest weak-model UX.

## In scope
- **Remove the hard BYOK gate** in `copilot_ws.py` (~L521-541): replace
  `resolve_org_byok_key → error if None` with local-capable provider resolution that mirrors
  the analysis pipeline (local/keyless via `OrgAIConfig.base_url` + `_LOCAL_PROVIDERS`, else
  cloud BYOK). A configured local org proceeds; a fully unconfigured org gets an honest
  "configure a model" message, not a crash.
- **Route generation** (NL→SQL, analysis, report intents, WS streaming) through the resolved
  provider. Reuse the worker's selection *pattern*; do not couple cross-service.
- **Provider-agnostic SQL safety (S0):** ensure the existing validator (read-only,
  org-scoped, ≤3 joins, schema whitelist, 5s timeout, row limits) runs **unconditionally**
  on every generated SQL regardless of provider.
- **Weak-model UX:** SQL that fails validation or empty/invalid generation → honest
  "couldn't turn that into a safe query with the current model" message (hint: stronger
  model improves results). Never a stack trace or a wrong-but-confident answer.
- **Streaming compatibility:** confirm token/stream shape works for OpenAI-compatible/local
  endpoints (or buffer + emit) so the WS contract holds.

## Out of scope
- Embedding/template-matching changes (→ `template-matching-local`).
- Improving local-model answer *quality* (explicit PRD non-goal) — only safety + legibility.
- New Copilot UI beyond the degraded-state message + minimal AI-Settings surfacing (S3).

## Acceptance criteria (testable)
- AC1: keyless org with a configured local provider runs a **data** query and an
  **analysis** query via the Copilot → both return answers, no error (mocked local provider).
- AC2: the SQL safety validator rejects a malicious/unsafe SQL string produced by a
  (simulated) local model — proving safety is provider-agnostic and unconditional.
- AC3: generation that yields invalid/unsafe SQL surfaces the honest weak-model message, not
  an unhandled exception.
- AC4: fully-unconfigured org (no BYOK key, no local base_url) gets an honest "configure a
  model" response — no 500.
- AC5: existing OpenAI-BYOK Copilot flows unchanged (regression).
- AC6: quality guardrail — on ~10 canned questions against a reference/mocked local model,
  ≥70% produce valid, org-scoped, safety-passing SQL; the rest hit the graceful path.

## Dependencies & sequencing
- After `embedding-provider-layer` (shares the provider-resolution pattern/config reads).
- Can build in parallel with `template-matching-local`.

## Open questions / risks
- R2: NL→SQL/report prompts may rely on OpenAI-only features (JSON mode, function calling) —
  plan must check and provide a plain-prompt fallback for local models.
- R3: streaming shape differences across endpoints.
