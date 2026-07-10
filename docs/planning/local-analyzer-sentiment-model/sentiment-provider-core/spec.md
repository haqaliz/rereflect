# Aspect Spec — sentiment-provider-core

**Parent PRD:** `../prd.md` · **Sequencing:** FOUNDATION — this aspect is **FIRST**; it blocks
`per-org-resolution`, `model-packaging`, and `eval-harness-and-card`.

## Problem slice & outcome

Today `analysis-engine/src/analyzer/sentiment.py` hardwires VADER: `SentimentAnalyzer.__init__`
constructs a `SentimentIntensityAnalyzer` directly and `analyze()` calls it inline. There is no
seam to plug in a second scoring backend, which blocks the entire Local Model Layer (M5) — M5.2
(per-org classifiers) and M5.3 (churn ML) are documented to plug into "the spine" this aspect
builds.

This aspect extracts VADER scoring behind a **pure, DB-free** `SentimentProvider` abstraction
(mirroring `backend-api/src/services/embeddings/{base,factory}.py`) inside `analysis-engine`, adds
a second `TransformerSentimentProvider` (`cardiffnlp/twitter-roberta-base-sentiment-latest`), and
keeps the outer `SentimentAnalyzer.analyze(text)` **byte-identical** for the default (unset/`vader`)
path. The label-threshold and `is_extreme`/`churn_risk` logic stay provider-independent and shared
by both providers, so only `compound`/`pos`/`neu`/`neg` vary by provider.

**Outcome:** `analyzer.sentiment.SentimentAnalyzer` gains an optional `provider` argument (name
string or pre-built `SentimentProvider` instance) with zero behavior change when omitted, plus a
factory (`SentimentProviderFactory.create("vader" | "transformer")`) that later aspects (the
backend per-org resolver) can call to build a provider and inject it in. Constructing/importing
this module never requires `torch`/`transformers` unless the transformer provider is actually
requested.

## In scope

- `analysis-engine/src/analyzer/sentiment_providers/` — new pure sub-package:
  - `base.py` — abstract `SentimentProvider` with `score(text: str) -> SentimentScore` returning
    exactly 4 keys: `compound, pos, neu, neg` (no `label`/`is_extreme`/`churn_risk` — those are
    provider-independent and computed by `SentimentAnalyzer`, not the provider).
  - `providers/vader.py` — `VaderSentimentProvider`, wrapping the exact current
    `SentimentIntensityAnalyzer().polarity_scores(text)` call, unmodified logic.
  - `providers/transformer.py` — `TransformerSentimentProvider` for
    `cardiffnlp/twitter-roberta-base-sentiment-latest`: CPU, lazy `torch`/`transformers` import
    (deferred past module import time, to inside the lazy model-load function), lazy **per-process**
    singleton model/tokenizer load, `model.eval()` + `torch.no_grad()` (deterministic, no dropout/
    sampling). Score mapping: softmax `[p_neg, p_neu, p_pos]` → `pos=p_pos, neu=p_neu, neg=p_neg`,
    `compound = p_pos − p_neg`.
  - `factory.py` — `SentimentProviderFactory.create(provider: str) -> SentimentProvider`, lazy
    per-branch imports (`"vader"` and `"transformer"` only); unknown/empty raises `ValueError`.
- Refactor `analysis-engine/src/analyzer/sentiment.py` (`SentimentAnalyzer`) to:
  - Accept `provider: str | SentimentProvider = "vader"` in `__init__` (name → factory, or an
    already-built instance for future injection).
  - Compose `provider.score(text)` with the **existing, unmodified** `_is_extreme_negative`,
    `_has_churn_indicators` methods and a shared label-threshold function (`±0.05` on `compound`,
    same for every provider) to assemble the 7-key `analyze()` return dict, same order as today.
  - **Runtime fallback (analyzer-side of PRD #9):** if `provider.score(text)` raises for any reason
    (model load failure, inference error), catch it, log a warning, and score that single item with
    a VADER fallback instance instead — `analyze()` itself must never raise.
  - Keep `classify_intensity()` unchanged (provider-independent, operates on `compound` only).
- A **characterization test** (written and passing against today's code, BEFORE the refactor
  touches `sentiment.py`) that pins `analyze()`'s output byte-for-byte for a fixed set of inputs —
  the seam extraction must not move this test.
- `analysis-engine/requirements.txt` — confirm `torch`/`transformers` are present at the versions
  the transformer provider needs (already declared per PRD; no worker/backend dep changes here).

## Out of scope

- `OrgAIConfig.sentiment_provider` column, migration, and `resolve_sentiment_provider(org_id, db)`
  — DB-aware per-org resolution lives in the sibling **per-org-resolution** aspect.
- Injecting the resolved provider at the two runtime call sites (`worker-service/src/tasks/
  analysis.py:479`, `backend-api/src/api/routes/feedback.py:47`) — those call sites construct
  `SentimentAnalyzer()` with zero args today; wiring a resolved provider into them is
  **per-org-resolution**'s job. This aspect only makes the constructor *able* to accept one.
- `worker-service/requirements.txt`, `backend-api/requirements.txt`, Dockerfile `HF_HOME` wiring,
  build-time pre-bake, `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` docs — **model-packaging** aspect.
- Eval harness script, labeled eval sets, precision/recall/F1 computation, accuracy card endpoint
  and frontend — **eval-harness-and-card** aspect.
- M5.0 AI training-readiness report — separate PRD must-have, not part of this slice.
- Settings validation / `GET /sentiment/status` — backend-api, later aspect.
- Any change to `analyzer/core.py`'s public shape beyond what's needed for the provider seam (no
  change to `FeedbackAnalyzer.__init__` signature; it keeps constructing `SentimentAnalyzer()` with
  defaults in this aspect).

## Testable acceptance criteria

- **AC1 (characterization, pre-refactor):** A test file locks today's `SentimentAnalyzer().analyze(text)`
  output for ≥5 representative inputs (positive, negative, neutral, extreme-negative, churn-risk),
  asserting the exact 7 keys **in order** (`compound, pos, neu, neg, label, is_extreme, churn_risk`)
  and exact float/bool/str values. This test is written and green against the **unrefactored** code
  first.
- **AC2 (byte-stability post-refactor):** After extracting `VaderSentimentProvider` and rewiring
  `SentimentAnalyzer`, the AC1 characterization test **still passes unmodified** — proving the
  refactor changed nothing observable for the default path. `SentimentAnalyzer()` (no args) and
  `SentimentAnalyzer("vader")` produce identical output to each other and to pre-refactor.
- **AC3 (provider ABC contract):** `SentimentProvider` is abstract; a subclass missing `score()`
  cannot be instantiated; `VaderSentimentProvider().score("some text")` returns exactly the 4 keys
  `compound, pos, neu, neg` (no `label`/`is_extreme`/`churn_risk`).
- **AC4 (transformer mapping, mocked model):** With the HF model/tokenizer mocked (no real network
  or weights download in unit tests), `TransformerSentimentProvider().score(text)` returns
  `compound == pos - neg` for a synthetic `[p_neg, p_neu, p_pos]` softmax output, and `pos/neu/neg`
  equal the mocked `p_pos/p_neu/p_neg` respectively.
- **AC5 (shared label thresholds):** For both providers, `analyze()`'s `label` is `'positive'` when
  `compound >= 0.05`, `'negative'` when `compound <= -0.05`, else `'neutral'` — verified by feeding
  a stub provider fixed `compound` values through `SentimentAnalyzer` and asserting `label`.
- **AC6 (is_extreme/churn_risk are provider-independent):** Feeding the same extreme-negative /
  churn-risk text through `SentimentAnalyzer` configured with a stub provider that returns different
  `compound` values each time still yields the same `is_extreme`/`churn_risk` booleans — proving
  those two fields depend only on the text, not the provider.
- **AC7 (factory dispatch):** `SentimentProviderFactory.create("vader")` →
  `VaderSentimentProvider`; `create("transformer")` → `TransformerSentimentProvider`;
  `create("")`/`create("bogus")` raises `ValueError` with a clear message.
- **AC8 (lazy import, no torch at import time):** `import analyzer` / `import analyzer.sentiment`
  / `import analyzer.sentiment_providers` / `import analyzer.sentiment_providers.factory` succeed
  in a process where `torch`/`transformers` are **not importable** (simulated via
  `sys.modules` stubbing or an import-blocking `conftest.py` fixture); only calling
  `SentimentProviderFactory.create("transformer")` (or a subsequent `.score()` call, depending on
  where the import boundary lands — see Open Questions) requires them.
- **AC9 (analyzer-side fallback, PRD #9):** Given a provider stub whose `score()` raises, calling
  `SentimentAnalyzer(provider=stub).analyze(text)` does **not** raise, returns a valid 7-key dict
  scored by VADER instead, and a warning is logged (assert via `caplog`).
- **AC10 (per-process singleton, PRD #9):** Two `TransformerSentimentProvider()` instances (or two
  `.score()` calls on one instance) reuse the same loaded model/tokenizer object — assert via
  mocking `AutoModelForSequenceClassification.from_pretrained`/`AutoTokenizer.from_pretrained` and
  counting invocations across multiple `score()` calls (expect exactly 1 call each, regardless of
  provider-instance count).
- **AC11 (determinism):** Two calls to `TransformerSentimentProvider().score(text)` with the same
  input text return bit-identical output (model in `eval()` mode, no sampling) — mocked-model test
  is sufficient here since the real weights aren't downloaded in unit tests; a manual/eval-harness
  run (out of scope here) is the real-weights check.

## Dependencies & sequencing

- **Upstream:** none. This is the **first** aspect of `local-analyzer-sentiment-model`.
- **Downstream (blocked on this aspect):**
  - `per-org-resolution` — needs `SentimentProviderFactory` and the `SentimentAnalyzer(provider=...)`
    constructor shape to build `resolve_sentiment_provider(org_id, db)`.
  - `model-packaging` — needs the concrete `TransformerSentimentProvider`'s import surface
    (`transformers`/`torch` symbols actually used) to know what to pre-bake/pin in Dockerfiles.
  - `eval-harness-and-card` — needs both providers constructible via the factory to run the same
    text through each and compare.
- Reuse map: `SentimentProvider` ABC mirrors `embeddings/base.py`; `SentimentProviderFactory`
  mirrors `embeddings/factory.py` (lazy per-branch imports, `if/elif` registry, `ValueError` on
  unknown); the analyzer-side try/except-fallback mirrors the resolver's
  "return `None`/default on any failure, never raise" spirit, translated to "score with VADER
  instead, never raise" since `analyze()` must always return a value, not an `Optional`.

## Open questions / risks

- **OQ1 — exact lazy-import boundary for AC8.** Two viable placements: (a) `providers/transformer.py`
  imports `torch`/`transformers` at module level (import-time cost only when the factory imports
  that module, i.e. only when `create("transformer")` is called — never on `import analyzer`), vs
  (b) defer the import further, inside `_get_model_and_tokenizer()` (import-time cost deferred to
  first `.score()` call). **Recommend (b)**: it means even constructing
  `SentimentProviderFactory.create("transformer")` — e.g. to check `isinstance` or read
  `provider.MODEL_NAME` — doesn't require torch to be installed, which matters if the
  per-org-resolution aspect ever wants to validate provider availability without triggering a full
  model load (mirrors the "Should-have" `/sentiment/status` endpoint's likely need). Confirm no
  regression in AC10's singleton test either way (singleton lives at module-global scope in
  `transformer.py`, imported lazily by `_get_model_and_tokenizer()` too, or is the model cache
  itself the thing gated behind the deferred import — see Phase 3 of the plan).
- **OQ2 — model revision pinning.** PRD Technical Considerations says "pinned model revision."
  `from_pretrained(..., revision=<sha>)` requires picking and recording an actual HF revision SHA
  for `cardiffnlp/twitter-roberta-base-sentiment-latest`. This aspect should pin *something*
  reproducible (a named revision or `"main"` with a documented risk), but the authoritative
  "confirmed good" SHA + license check is arguably **model-packaging**'s or
  **eval-harness-and-card**'s job (whoever validates real weights). Recommend: this aspect defines
  a `_MODEL_REVISION` constant with a placeholder/documented TODO, downstream aspects confirm it
  against the real download.
- **OQ3 — `SentimentScore` shape.** `TypedDict` vs frozen `dataclass` vs plain `dict`. Recommend
  `TypedDict` (matches the existing dict-shaped contract with static typing, zero runtime overhead,
  no new dependency) — confirm in the tech-plan before Phase 1.
- **OQ4 — where does the always-on VADER fallback instance live?** Two options: (a)
  `SentimentAnalyzer` always builds a private `VaderSentimentProvider()` fallback in `__init__`
  regardless of the configured provider (cheap — VADER has no model load), reusing it if the
  configured provider *is* VADER; (b) lazily construct the fallback only on first failure. Recommend
  (a) for simplicity and because VADER construction is free (no I/O), but flag: this means a
  transformer-configured `SentimentAnalyzer` always pays VADER's tiny init cost even if the
  transformer never fails — judged acceptable (microseconds).
- **Risk — determinism can't be fully proven without real weights.** AC11 is mocked; the *real*
  weights' determinism (no dropout at inference by default for RoBERTa classification heads, but
  worth confirming no `training=True` state leaks) is a residual risk closed out by
  `eval-harness-and-card`'s reproducibility check, not this aspect's unit tests.
- **Risk — worker/backend import path divergence.** `worker-service` imports as top-level
  `analyzer.sentiment` (Dockerfile copies `analysis-engine/src/analyzer` → `/app/analyzer`) while
  `backend-api`'s sync path also `sys.path`-inserts `analysis-engine/src` and imports
  `analyzer.sentiment` the same way (see `feedback.py:25-31`) — **not** `src.analyzer.sentiment` (that
  root is analysis-engine's own test/package root). All new intra-package imports in this aspect
  **must be relative** (`from .sentiment_providers.base import ...`, not
  `from src.analyzer.sentiment_providers...`) so they resolve correctly under both the
  `src.analyzer.*` (analysis-engine tests) and bare `analyzer.*` (worker/backend copy) roots. This
  is a real gotcha found in the code dig (`understanding.md` §4) — call it out explicitly in the plan.
