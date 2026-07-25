# Aspect spec — in-process-provider

**Parent PRD:** `../prd.md` (M5.4) · **Aspect 2 of 5** · **Sequencing: after `staleness-model-key`**

## Problem slice & user outcome

Today "local" embeddings require an external Ollama/vLLM server (the `ollama`/`openai_compatible`
HTTP path). There is no CPU, in-process, air-gappable embedding provider. Outcome: a self-hosting
operator selects **Local (in-process)** in Settings → AI and the Copilot template-matcher runs on a
model loaded inside `backend-api` — no external server, no cloud key, no runtime network.

## In-scope

- New `services/backend-api/src/services/embeddings/providers/local.py` implementing the
  `EmbeddingProvider` ABC: `embed(text) -> list[float]` and a **model-derived** `dimension` (from the
  first real embedding — never hardcoded). Loads a sentence-transformers model **lazily** (import +
  model load on first use), cached process-wide. CPU device.
- Register provider key `local` in `EmbeddingProviderFactory.create` — keyless, no `base_url`
  required; `model` defaults to the recommended model id (see PRD; final pick from the eval aspect).
- Resolver: add `local` to `_LOCAL_PROVIDERS` in `resolver.py` (keyless path — no BYOK, no base_url
  requirement).
- Settings (`ai_settings.py`): add `local` to `VALID_PROVIDERS` and `LOCAL_PROVIDERS`; extend
  `_default_embedding_model` to return the local default; add a `_embedding_local_deps_available()`
  guard (mirror `_sentiment_transformer_deps_available()`); `PATCH /api/v1/settings/ai` **rejects**
  `local` with a clear error when the lib is not installed. `local` must **not** require `base_url`.
- Add `sentence-transformers` to `services/backend-api/requirements.txt` (torch already declared for
  M5.1). Import must stay lazy so installs that never opt in don't pay import cost or crash.
- `GET /api/v1/settings/ai/embeddings/status`: report `provider='local'`, the selected `model`, and
  `dimension` once known.

## Out-of-scope

- The eval/card (Aspect 3), packaging/pre-bake (Aspect 4), Ollama bump (Aspect 5).
- Any default change for non-local installs (byte-stable — `local` is strictly opt-in).
- pgvector; threshold/ranking changes.

## Acceptance criteria (testable)

1. With `sentence-transformers` installed, `EmbeddingProviderFactory.create('local')` returns a
   provider whose `embed("hello")` yields a non-empty `list[float]` and whose `dimension` equals
   `len(that vector)`.
2. `resolve_embedding_provider` returns a `ResolvedEmbedder(provider='local', ...)` for an org whose
   `OrgAIConfig.default_provider='local'` with **no** `base_url` and **no** BYOK key set.
3. `PATCH /api/v1/settings/ai {default_provider:'local'}` succeeds when deps present; returns a clear
   4xx when `_embedding_local_deps_available()` is False.
4. Importing `src.api.main` with `sentence-transformers` **absent** does not raise (lazy import
   verified) and the existing providers still resolve.
5. A `local`-provider embed → `TemplateSaver` write stores `embedding_provider='local'`,
   `embedding_dimension=len(vec)`, and `embedding_model=<model id>` (integrates with Aspect 1).
6. Characterization: an org on `openai`/`google`/`ollama` is completely unaffected.
7. **Async safety:** the model is never imported/loaded at module import time; `embed()` is invoked
   off the event loop (matcher's threadpool path) — verified by a test asserting no model load on
   `import src.api.main` and that the WS handler path uses the threadpool.
8. **Pre-warm:** when `local` is the selected provider, the model is loaded once at startup (pre-warm
   hook), so the first query does not incur the multi-second load; steady-state per-query latency is
   measured and recorded.

## Dependencies & sequencing

- **Depends on `staleness-model-key`** (so stored writes carry `embedding_model`).
- **Blocks `retrieval-eval-card`** (eval needs a runnable local provider) and `offline-packaging`.

## Open questions / risks

- Model default: `BAAI/bge-small-en-v1.5` (preferred) vs `all-MiniLM-L6-v2` (lighter) — final pick
  confirmed by the eval aspect; wire whichever as the `local` default constant.
- CPU embed latency for the per-request query embed — measure; keep within interactive budget. Model
  load is one-time/lazy.
- Thread-safety of the cached model under the matcher's `run_in_threadpool` call — confirm the ST
  model is used read-only and safe across threads.
