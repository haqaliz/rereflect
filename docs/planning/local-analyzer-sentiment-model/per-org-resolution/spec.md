# Aspect Spec — per-org-resolution

**Parent PRD:** `../prd.md` · **Sequencing:** depends on `sentiment-provider-core` (FOUNDATION,
must land first — needs its `SentimentAnalyzer(provider=...)` constructor shape and
`SentimentProviderFactory`). Can be built in parallel with `model-packaging` and
`eval-harness-and-card` (no shared files).

## Problem slice & user outcome

Today both sentiment call sites — the worker's async pipeline
(`worker-service/src/tasks/analysis.py:479`, inside `_apply_keyword_analysis`) and the backend's
synchronous create/re-analyze path (`backend-api/src/api/routes/feedback.py:47`, inside
`analyze_single_feedback`) — construct `SentimentAnalyzer()` with zero args, hardwiring VADER.
`sentiment-provider-core` makes the analyzer's `provider` argument pluggable but does **not** wire
anything per-org (out of scope there by design). This aspect is the "last mile": an operator flips
**Sentiment engine** to `transformer` in Settings → AI, and from that point every new feedback item
for their org is scored by the resolved provider — while every org that never touches the setting
(the overwhelming default) keeps producing byte-identical VADER output, and any resolution/
construction failure silently degrades to VADER instead of erroring the analysis task.

## In scope

- **Schema.** `OrgAIConfig.sentiment_provider` — new nullable `VARCHAR(20)` column, default
  `'vader'`, values `'vader' | 'transformer'`. Added to **both** the backend-api model
  (`src/models/org_ai_config.py`) and the worker's ORM mirror
  (`src/models/__init__.py::OrgAIConfig`), consistent with the existing mirror pattern (see
  `health_weight_crm`/`health_weight_usage` precedent). One Alembic migration in `backend-api`
  only (the worker has no migrations; it reads the same physical table).
- **Backend resolver.** `resolve_sentiment_provider(org_id: int, db) -> Optional[ResolvedSentiment]`
  in `backend-api/src/services/sentiment_resolver.py` — mirrors
  `resolve_embedding_provider`'s never-raise/`None`-on-any-failure contract, but simpler: no BYOK,
  no heavy construction. It reads `OrgAIConfig.sentiment_provider`, validates against
  `{'vader', 'transformer'}`, and returns a plain `ResolvedSentiment(provider: str)` or `None`.
  It does **not** import `analysis-engine` or construct a `SentimentProvider` — that stays pure/
  DB-free per the architecture split; resolution only ever produces a validated **name string**.
- **Worker resolver.** `worker-service/src/services/sentiment_resolver.py` — an independent mirror
  of the same function reading the worker's own `OrgAIConfig` model (no cross-service import,
  consistent with `worker-service/src/llm/org_resolver.py` and the existing `OrgAIConfig`/
  `OrgApiKey` model mirrors).
- **AI-settings schema/route.** Extend `AISettingsResponse` (add `sentiment_provider: str`, always
  populated, defaults to `"vader"`) and `AISettingsUpdate` (add
  `sentiment_provider: Optional[str] = None`) in `ai_settings.py`. `PATCH /api/v1/settings/ai`
  validates the value against `{'vader', 'transformer'}` using the same `model_fields_set`
  explicit-null-vs-omitted pattern already used for `base_url`/`model_embeddings`. Should-have:
  when the effective value is `'transformer'`, validate the deps are importable
  (`importlib.util.find_spec("torch")` / `"transformers"`, no actual import) and return 422 with an
  actionable message if not — mirrors the `LOCAL_PROVIDERS`-needs-`base_url` check pattern at
  `ai_settings.py:412-431`.
- **Status endpoint.** `GET /api/v1/settings/ai/sentiment/status` → `{ provider, available, model }`,
  never raises, mirrors `GET /embeddings/status` (`ai_settings.py:819-866`). `provider` is the
  org's effective setting (defaults to `"vader"`); `available` is `True` for `"vader"` always, and
  for `"transformer"` reflects whether `torch`/`transformers` are importable (dep-availability, not
  "model successfully loaded" — loading is deferred/lazy per `sentiment-provider-core`); `model` is
  the pinned model id (`cardiffnlp/twitter-roberta-base-sentiment-latest`) when `transformer`,
  else `null`.
- **Backend call-site injection** (`feedback.py:25-31, 47`). `get_sentiment_analyzer()` gains an
  optional `provider_name: str = "vader"` param, resolves via a process-level cache (single load
  per provider per process — PRD must-have #9's call-site half), and constructs
  `SentimentAnalyzer(provider=provider_name)` inside a `try/except` that falls back to
  `SentimentAnalyzer()` (VADER) on **any** construction failure (unknown name, missing deps, model
  load error), logging a warning. `analyze_single_feedback(feedback, db)` resolves the org's
  provider via `resolve_sentiment_provider` before calling `get_sentiment_analyzer(...)`.
- **Worker call-site injection** (`analysis.py:55-58, 472-479`). Identical shape: `_apply_keyword_
  analysis(feedback, db=None)` resolves via the worker's `resolve_sentiment_provider`
  (guarded — `db` is already optional at this call site) and passes the name into
  `get_sentiment_analyzer(provider_name)`, which gets the same process-level cache + fallback
  wrapper as the backend.
- **Consistency guarantee.** Both resolvers read the same DB column with the same validation logic
  (mirror, not shared code, per the existing worker/backend split) so a given org resolves to the
  same provider name regardless of which service processes the feedback.

## Out of scope (owned by sibling aspects / explicitly deferred)

- `SentimentProvider` ABC, `VaderSentimentProvider`, `TransformerSentimentProvider`, the softmax→
  contract score mapping, the analyzer-internal per-item runtime fallback (`analyze()` catching a
  `provider.score()` failure), the per-process transformer model/tokenizer singleton, and
  `SentimentProviderFactory` — all `sentiment-provider-core`. I only **call** the resulting
  `SentimentAnalyzer(provider=...)` constructor and catch its failures at my two call sites.
- `torch`/`transformers` in `worker-service/requirements.txt` / `backend-api/requirements.txt`,
  Dockerfile `HF_HOME`/pre-bake wiring, `HF_HUB_OFFLINE` docs, the backend's broken `sys.path`
  import fix — `model-packaging`.
- Eval harness, labeled sets, precision/recall/F1, `GET /sentiment/accuracy`, the frontend accuracy
  card — `eval-harness-and-card`.
- M5.0 AI training-readiness report — separate must-have, different aspect dir.
- Frontend Settings → AI toggle UI (the `sentiment_provider` select control, wiring to the PATCH/
  status endpoints) — not listed in this aspect's file boundary (`services/backend-api` +
  `services/worker-service` only); flagged as an open question below.
- `AI-TRACKING.md`/`README`/`SELF_HOSTING.md` docs updates (must-have #10) — a different aspect's
  job per the PRD's Definition-of-Done split.

## Acceptance criteria (testable)

- **AC1 — unset defaults to VADER.** An org with no `OrgAIConfig` row, or a row with
  `sentiment_provider IS NULL`, resolves to `None` from `resolve_sentiment_provider` (both
  backend and worker), and the corresponding call site's `get_sentiment_analyzer("vader")` produces
  output byte-identical to `get_sentiment_analyzer()` (no-args) — characterization-tested.
- **AC2 — explicit `'transformer'` resolves and injects.** An org with `sentiment_provider =
  'transformer'` resolves to `ResolvedSentiment(provider="transformer")`; the call site constructs
  `SentimentAnalyzer(provider="transformer")` (mocked at the unit-test boundary — no real model
  download in this aspect's tests).
- **AC3 — unknown/invalid column value degrades to VADER.** A row with
  `sentiment_provider = 'nonsense'` (e.g. written by a future incompatible version) resolves to
  `None`, never raises, and the call site falls back to VADER.
- **AC4 — resolver never raises.** Simulated DB errors (session raising on `.query()`) are caught
  inside `resolve_sentiment_provider` and produce `None`, not a propagated exception, at both
  backend and worker resolvers.
- **AC5 — cross-org isolation.** With two `OrgAIConfig` rows in the same DB session (org A =
  `'transformer'`, org B = unset/`'vader'`), resolving org A returns `transformer` and resolving
  org B returns `None`/`vader` — no leakage either direction, tested against both resolvers.
- **AC6 — construction-failure fallback at the call site.** If `SentimentAnalyzer(provider=
  "transformer")` raises (simulated `ImportError`/`ValueError`/generic `Exception`) inside
  `get_sentiment_analyzer`, the returned analyzer is the VADER default, a warning is logged, and no
  exception propagates to the caller — tested at both call sites.
- **AC7 — single load per process.** Calling `get_sentiment_analyzer("transformer")` (or any name)
  twice in the same process constructs `SentimentAnalyzer` **once** (module-level cache
  hit on the second call) — tested via a construction-call-count spy at both call sites.
- **AC8 — PATCH validation.** `PATCH /api/v1/settings/ai` with `sentiment_provider: "transformer"`
  succeeds (200) when deps are importable, and returns 422 with an actionable message when they are
  not (mocked `find_spec` → `None`); `sentiment_provider: "bogus"` always returns 422;
  `sentiment_provider` omitted from the body leaves the existing value untouched (`model_fields_set`
  pattern, mirrors `base_url`).
- **AC9 — GET returns the field; status endpoint never raises.** `GET /api/v1/settings/ai` includes
  `sentiment_provider` (defaults `"vader"` when unset). `GET /sentiment/status` returns 200 with
  `{provider, available, model}` for every state (no config row, `vader`, `transformer` with deps
  present, `transformer` with deps absent) — never a 500.
- **AC10 — characterization: analysis output unchanged for `'vader'`.** For a fixed set of sample
  feedback texts, running the full `_apply_keyword_analysis` (worker) / `analyze_single_feedback`
  (backend) pipeline with an org resolved to `vader` (explicit or unset) produces identical
  `sentiment_label`/`sentiment_score`/`is_urgent` values to the pre-aspect code path — the
  regression guard for the entire PRD's "zero regression" goal, scoped to the injection wiring
  (not the provider internals, which `sentiment-provider-core` already characterization-tests).

## Dependencies & sequencing

- **Hard dependency: `sentiment-provider-core` must merge/land first.** This aspect calls
  `SentimentAnalyzer(provider: str | SentimentProvider)` and (indirectly, via that constructor)
  `SentimentProviderFactory.create(...)`; both are defined there. Development can proceed against
  a **stub** matching the documented signature (`sentiment-provider-core/spec.md` §"Outcome") if
  the two aspects run in parallel, but integration tests must be re-run once the real module lands.
- **No dependency on `model-packaging`.** `torch`/`transformers` need not be installed for this
  aspect's own tests — all provider-construction points are mocked/stubbed at the boundary
  (`SentimentAnalyzer` itself, not its internals). The dep-availability check in the status/PATCH
  endpoints uses `importlib.util.find_spec`, which works whether or not the packages are actually
  installed (returns `None` cleanly either way) and needs no real `model-packaging` work to test.
- **No dependency on `eval-harness-and-card`.** That aspect *reads* which provider produced a
  result (future: run eval against whatever `resolve_sentiment_provider` would pick) but does not
  block this one.
- **Alembic multi-heads gotcha (memory: `rereflect-repo-test-gotchas`).** The repo has previously
  had multiple Alembic heads from parallel feature branches. Current head on this worktree at
  spec time: `a6b703d7a303` (verified via `alembic heads`, single head). **Before creating the
  migration at implementation time, re-run `alembic heads` — do not trust this recorded value** if
  other aspects/branches have landed migrations in the interim; merge heads first if more than one
  is reported.

## Open questions / risks

- **Frontend toggle is out of this aspect's file boundary** (`services/backend-api` +
  `services/worker-service` only per the task boundary), but the PATCH/status endpoints exist
  *for* a frontend toggle. Flag for the tech-plan/PRD owner: confirm which aspect (or a follow-up)
  wires `settings/ai/page.tsx`'s UI control — otherwise the endpoints ship with no consumer.
- **`SentimentAnalyzer(provider=...)` construction-failure semantics are not fully pinned by
  `sentiment-provider-core`'s spec** — it documents the constructor accepts `str | SentimentProvider`
  but does not state whether `__init__("bogus")` raises `ValueError` immediately or defers to first
  `.score()` call. This aspect's call-site `try/except` is written broad (`except Exception`)
  specifically so it is correct under either behavior — confirm no behavior actually needs the
  narrower type once the real module lands, and narrow the `except` clause in a follow-up if so.
- **Availability check depth for `GET /sentiment/status` and the PATCH validation is intentionally
  shallow** (`find_spec` only — "are the packages importable", not "does the model download
  succeed" or "is there enough RAM"). This is a deliberate scope line: verifying the full transformer
  path (real weights, real inference) is `model-packaging`'s/`eval-harness-and-card`'s concern. If
  a reviewer wants a deeper check, it changes this aspect's runtime characteristics (an import can
  be slow); flag before widening it.
- **`sentiment_provider` is not currently gated by plan tier** in the PRD or this spec — it is
  available to any org that can reach `PATCH /api/v1/settings/ai` (admin/owner, per existing
  `require_admin_or_owner`). Confirm this is intentional (matches the OSS/self-hosted framing —
  no billing tier for a local/offline feature) before implementation, since every other AI-settings
  toggle in this file has no plan gate either (precedent: `default_provider`, `base_url`).
- **Column nullability double-default.** The column is `nullable=True` with a DB `server_default`
  of `'vader'` (covers raw/backfilled rows) **and** the resolver additionally treats `NULL`/unknown
  as "return `None`" (covered again by the call site's own `"vader"` fallback). This is deliberate
  belt-and-suspenders (mirrors `getattr(config, "model_embeddings", None)` defensiveness for
  pre-migration schemas) but means the column's Python-side ORM `default=` is somewhat redundant
  with the resolver's own normalization — documented, not a bug.
