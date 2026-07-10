# Aspect Spec — eval-harness-and-card

**Parent PRD:** `../prd.md` · **Sequencing:** DISCLOSURE layer — consumes `sentiment-provider-core`
(hard dep: needs both `VaderSentimentProvider` and `TransformerSentimentProvider` importable),
soft-depends on `model-packaging` (transformer deps must actually be installed to run the model
half of the harness; the VADER half + the metrics/plumbing work without it).

## Problem slice & outcome

Prove — honestly, offline, reproducibly — whether the transformer sentiment provider beats VADER,
and surface that proof where operators already look (`Settings → AI → Accuracy` tab). This is
**disclosure, not a merge gate**: per the review-gate decision recorded in the PRD
(`prd.md:163-168`), the spine ships and the transformer provider ships **OFF by default** even if
it loses in-domain. This aspect's job is to make the result **visible and honest** — including
when it's a loss — not to block anything.

Two deliverables:
1. An **eval script** that runs both providers over two labeled CSVs and computes
   precision/recall/F1 per class + macro-F1 + confusion matrix, reusing the
   `tp/fp/fn/tn → precision/recall/f1/accuracy` helper pattern already in
   `admin_backtest.py:56` (`_safe_precision_recall_f1_accuracy`), generalized to multiclass via
   one-vs-rest confusion-matrix rows.
2. A **backend endpoint + frontend card** that reads the script's committed results and renders
   transformer-vs-VADER metrics (incl. `n`) under the existing `accuracy` tab
   (`settings/ai/page.tsx:41`), mirroring `churn_accuracy.py:107` (`get_org_accuracy_card`) +
   `ModelAccuracyCard.tsx`.

## In scope

- **Two labeled CSV eval sets**, schema `text,label` (`label ∈ {negative,neutral,positive}`),
  **≥150 rows each**:
  - `public_eval.csv` — a small **committed, redistribution-safe** 3-class set used as the CI
    baseline (see Licensing decision below).
  - `in_domain_eval.csv` — hand-labeled rows derived from root `sample_feedback_diverse.csv`
    (product-feedback domain, matches the honest "in-domain" claim in the PRD success metric).
  - A **tiny fixture CSV** (~8-10 rows, hand-crafted, obvious labels) for the eval-script's own
    unit tests — separate from the two real sets so script tests never depend on hand-labeling
    quality.
- **`services/backend-api/scripts/eval_sentiment.py`** — CLI + importable functions:
  - `load_eval_csv(path) -> list[(text, label)]`
  - `run_provider(provider, rows) -> ProviderEvalResult` (predicts, builds confusion matrix)
  - `confusion_to_binary_counts(confusion, label) -> (tp, fp, fn, tn)` (one-vs-rest slice)
  - `compute_multiclass_metrics(confusion, labels) -> {per_class, macro_precision, macro_recall,
    macro_f1, accuracy}` — **calls the reused `_safe_precision_recall_f1_accuracy`-shaped helper**
    per class, then averages for macro.
  - `run_eval_set(set_name, csv_path) -> EvalSetResult` — runs both providers, computes
    `macro_f1_delta = transformer.macro_f1 - vader.macro_f1`, `meets_target` (in-domain only,
    `delta >= 0.05`).
  - `main()` — runs both sets, writes the committed results artifact
    (`services/backend-api/eval_results/sentiment_accuracy.json`), prints a human summary.
- **`GET /api/v1/settings/ai/sentiment/accuracy`** (new route, alongside `ai_settings.py`'s
  existing `/embeddings/status` pattern) — reads the committed JSON artifact, never raises;
  returns an honest "not yet run" (`has_results: false`) state if the file is absent. No DB
  table this slice (mirrors the PRD's explicit "no new table required" data-model note).
- **Frontend**: `SentimentAccuracyCard` rendered inside the existing `accuracy` `TabsContent` in
  `settings/ai/page.tsx`, below the existing AI-corrections stats block; a small
  `lib/api/sentiment-accuracy.ts` client mirroring `lib/api/churn-accuracy.ts`'s shape
  (types + fetch fn + a `formatMetricPercent`-style helper). Card states: loading skeleton, error,
  no-results-yet (script never run), and populated (per-set macro-F1 for both providers, the
  delta, `n`, and an honest badge: "beats VADER" / "does not beat VADER" — never hides a loss).
- Reuse the `_safe_precision_recall_f1_accuracy` **pattern** (function shape/logic), not a direct
  cross-module import — `admin_backtest.py` is route-local; the eval script defines its own
  copy of the same tp/fp/fn/tn math (same precedent `backtest_churn.py` already sets: the two
  existing metric helpers are independently defined, not shared via a common module).

## Out of scope

- `SentimentProvider` ABC, `VaderSentimentProvider`, `TransformerSentimentProvider`, the factory
  (`sentiment-provider-core` aspect — **hard dependency**, this aspect only *consumes* the two
  provider classes to run predictions).
- `resolve_sentiment_provider`, `OrgAIConfig.sentiment_provider` column, per-org opt-in wiring,
  the two runtime call-site injections (worker `analysis.py:479`, backend `feedback.py:47`) —
  **per-org-resolution** aspect. The eval script instantiates providers directly (no org/DB
  context — it's explicitly offline/reproducible, per must-have #6).
- `torch`/`transformers` added to `worker-service/requirements.txt`, Dockerfile pre-bake,
  `HF_HOME` wiring, air-gap docs — **model-packaging** aspect. This aspect only needs the
  transformer deps present in **backend-api's** environment to run
  `eval_sentiment.py --provider transformer` locally/in CI; see Dependencies below for what
  happens when they're absent.
- The M5.0 AI training-readiness report (must-have #8) — separate slice/aspect.
- Persisting eval runs to a DB table, historical trend charts for the sentiment card (nice-to-have
  per PRD's "provider/label tagging on persisted eval runs" should-have — deferred; the committed
  JSON is a single "latest run" snapshot, matching the churn card's simplest read path but without
  its `history` array).
- Fine-tuning, additional models, non-3-class eval sets.

## Scope decisions (explicit, per task brief)

1. **Where the eval sets live:** `services/backend-api/tests/fixtures/sentiment_eval/`
   (`public_eval.csv`, `in_domain_eval.csv`, `tiny_fixture.csv`). Chosen over
   `docs/planning/.../eval/` because (a) the backend-api Dockerfile does `COPY . .`, so anything
   under `tests/` still ships in the runtime image and stays reachable by
   `scripts/eval_sentiment.py`, while `docs/planning/` is meta-planning content with no such
   shipping guarantee; (b) it matches the existing convention of DB-fixture-adjacent test data
   living under `tests/`; (c) keeping eval-set CSVs next to the scripts that consume them (both
   under `backend-api`) avoids a cross-service path reach.
2. **Eval script location — `services/backend-api/scripts/eval_sentiment.py`** (not
   `analysis-engine/scripts/`). Justification:
   - `feedback.py:24-31` already establishes the exact import pattern this script needs
     (`sys.path.insert` to `../../../analysis-engine`, then `from analyzer... import ...`) —
     the script reuses that precedent verbatim, it isn't inventing a new cross-service coupling.
   - `analysis-engine` has no independent runtime/venv in this repo — it is never `pip install`-ed
     or run as its own service; it's copied-as-source into the worker image and reached via
     `sys.path` from backend-api. There is no "analysis-engine environment" to run a script in
     without first standing one up.
   - Must-have #5 already adds `torch`+`transformers` to **`backend-api/requirements.txt`** (for
     the synchronous `feedback.py:47` path), so backend-api's env is guaranteed to have both
     providers' deps installable — the script doesn't need anything analysis-engine's
     `requirements.txt` doesn't already promise backend-api will also have.
   - The metrics-helper precedent (`admin_backtest.py`) and the CLI-script-with-importable-core
     precedent (`backtest_churn.py`, tested via `tests/test_backtest_backfill_scripts.py`) both
     live in `backend-api/scripts/` + `backend-api/tests/` — colocating keeps one script
     directory, one test directory, one place to run `pytest` for this whole aspect.
   - The accuracy **endpoint** also lives in backend-api; colocating the script that produces its
     input artifact avoids a cross-service artifact hand-off path.
3. **CSV schema:** `text,label` header; `label ∈ {negative,neutral,positive}` (lowercase, matches
   `SentimentAnalyzer`'s `label` output exactly — no remapping needed when comparing predicted vs
   gold).
4. **Live vs committed accuracy endpoint:** reads a **committed JSON artifact**
   (`services/backend-api/eval_results/sentiment_accuracy.json`), produced by running
   `python scripts/eval_sentiment.py` locally/in CI and committing the output — mirroring how the
   churn accuracy card summarizes a **previously-fit** model/run (`ChurnCalibrationModel`,
   refreshed by a scheduled job) rather than computing live on every request. Rationale: running
   the transformer over 150+ rows synchronously inside a request handler is exactly the
   cold-start/latency risk the PRD flags (`prd.md:160-161`) — unacceptable in a GET handler. No
   live-recompute endpoint ships in this aspect; recomputation is `python scripts/eval_sentiment.py`
   + commit (documented in the plan's Definition of Done). A future aspect may add an
   admin-triggered async re-run (should-have, not here).

## Licensing note (flag, do not silently resolve)

- **Public eval set:** to fully sidestep redistribution risk in an MIT repo, default to a small
  **self-authored, CC0-equivalent synthetic set** (~150-200 short, unambiguous 3-class sentences
  written for this task) rather than repackaging a third-party corpus. This is the safe default
  proposed here.
- **If a real public corpus is substituted later** (e.g. `tweet_eval`/`sentiment` — Apache-2.0 —
  or an SST-style set), its license **must be confirmed compatible with MIT redistribution**
  before committing any of its rows to this repo. Do not commit a Twitter/X-scraped corpus without
  checking ToS separately from the dataset's own license (Twitter's terms have historically
  restricted redistribution of raw tweet text even under a permissive dataset license).
- **HF model license** (`cardiffnlp/twitter-roberta-base-sentiment-latest`): confirm its model
  card license permits the intended self-hosted redistribution/use pattern (this repo does not
  bundle model weights in git — they're pulled/pre-baked per `model-packaging` — but confirm
  before that aspect bakes weights into a distributed image).
- **In-domain set:** derived from `sample_feedback_diverse.csv`, which is already first-party repo
  content (synthetic sample data, not scraped) — no external licensing risk.

## Acceptance criteria (testable)

- AC1: `compute_multiclass_metrics(confusion, labels)` given a hand-built 3-class confusion
  matrix with known per-class tp/fp/fn/tn returns exact expected precision/recall/F1 per class
  and the correct macro-F1 (mean of per-class F1) — mirrors
  `test_backtest_backfill_scripts.py::TestMetricsComputation`'s known-input-known-output style.
- AC2: `run_eval_set` against the tiny fixture CSV (both providers stubbed/real-VADER) returns
  the exact expected per-class counts and `n` matching a hand-counted expectation of the fixture.
- AC3: `GET /api/v1/settings/ai/sentiment/accuracy` returns `has_results: false` (200, not an
  error) when `eval_results/sentiment_accuracy.json` is absent.
- AC4: `GET /api/v1/settings/ai/sentiment/accuracy` returns parsed metrics (incl. `n`,
  `macro_f1_delta`, `meets_target`) when the artifact is present — schema-locked via a Pydantic
  response model.
- AC5: `SentimentAccuracyCard` renders macro-F1 for both providers, the labeled `n`, and an
  honest beats/doesn't-beat badge for both the populated and no-results states (frontend test
  mirrors `ModelAccuracyCard.test.tsx`'s loading/error/empty/populated matrix).
- AC6: The committed `public_eval.csv` and `in_domain_eval.csv` each have **≥150 rows** and pass a
  CSV-shape test (header exact, all labels in the 3-class set, no empty text).

## Dependencies & sequencing

- **Hard dependency — `sentiment-provider-core`:** needs `VaderSentimentProvider` and
  `TransformerSentimentProvider` (or the outer `SentimentAnalyzer` composed with an injectable
  provider) importable from `analysis-engine/src/analyzer`. Until that lands, this aspect can
  build and test everything **except** the actual `transformer` provider run (metrics math,
  script plumbing, CSV fixtures, endpoint/card against a hand-written fixture JSON are all
  independently gradable).
- **Soft dependency — `model-packaging`:** the transformer half of the eval script needs
  `torch`+`transformers` importable in backend-api's env. Until that lands, `eval_sentiment.py`
  runs VADER-only and the script/endpoint must **degrade gracefully** (`transformer: null` in the
  artifact + card shows "transformer not evaluated" rather than erroring) — this graceful-skip
  behavior is itself testable now, independent of both dependencies.
- **Does not depend on `per-org-resolution`** — the eval harness never resolves a per-org
  provider; it instantiates both provider classes directly and offline.

## Open questions / risks

- OQ1: Should the committed results JSON be regenerated by CI on every PR (fails the build if it
  drifts) or manually refreshed and just committed? Recommend **manual refresh + committed**,
  matching the "disclosure not gate" decision — a CI job that fails on drift would effectively
  re-introduce a merge gate the PRD explicitly rejected. Confirm in the tech-plan review.
- OQ2: Confirm the exact public-set licensing approach (self-authored vs named permissive corpus)
  before Phase where `public_eval.csv` content is written — flagged above, not resolved here.
- R1: If `sentiment-provider-core` lands with a different provider constructor signature than
  assumed here (e.g. requires a config object rather than being directly instantiable), the
  script's `run_provider()` wiring needs a small adapter — low risk, isolated to one function.
- R2: Macro-F1 on a 3-class set with `n≈150` has real sampling noise; the card must show `n`
  prominently (must-have #6/#7) so operators can judge significance themselves — no confidence
  interval is computed this slice (unlike the churn card's bootstrap CI) to keep scope tight;
  flagged as a possible nice-to-have follow-up, not required here.
