# Aspect spec — retrieval-eval-card

**Parent PRD:** `../prd.md` (M5.4) · **Aspect 3 of 5** · **Sequencing: after `in-process-provider`**

## Problem slice & user outcome

"Better local embedding model" is only credible with honest, reproducible proof. Mirror the M5.1
sentiment eval-harness-and-card pattern for **retrieval**. Outcome: an operator opens the AI settings
embeddings card and sees, offline, whether the local model beats the local baseline on a committed
labeled set — with `n` always shown and no absolute-accuracy marketing claim.

## In-scope

- **Fixtures:** committed labeled query→template pairs under
  `services/backend-api/tests/fixtures/embedding_eval/` covering the 15 system templates, including
  **paraphrases** and **negatives** (queries that should match *no* template). **≥ 60 pairs total.**
- **Eval core + CLI:** `services/backend-api/scripts/eval_embeddings.py` — importable core + CLI that
  runs one or more providers over the fixtures and computes retrieval metrics at the `0.85` regime:
  **recall@1**, **MRR**, and **false-match rate** on negatives. Deterministic; offline.
- **Committed artifact:** writes `services/backend-api/eval_results/embedding_retrieval.json`
  (provider/model, per-metric values, `n`, baseline-vs-candidate, timestamp passed in — not generated
  in-process, matching M5.1). Commit a real run for the chosen local model vs the `nomic-embed-text`
  baseline.
- **Read-only endpoint:** `GET /api/v1/settings/ai/embeddings/accuracy` returning the artifact or
  `{"has_results": false}` (HTTP 200) when absent. Mirrors `.../sentiment/accuracy`.
- **Frontend card:** in the AI settings page, beside the existing embeddings status, render the
  metrics, `n`, and an honest "beats baseline / does not beat baseline" badge. `has_results:false`
  renders a neutral empty state.

## Out-of-scope

- Making the eval a CI merge gate (disclosure only, exactly like M5.1).
- Changing the matcher threshold or ranking.
- Evaluating cloud providers as the headline (baseline is the **local** `nomic-embed-text`; cloud
  numbers optional/context only).

## Acceptance criteria (testable)

1. `python scripts/eval_embeddings.py --provider local` over the fixtures produces recall@1, MRR, and
   false-match-rate and writes the JSON artifact deterministically (same inputs → same numbers).
2. Fixtures contain ≥ 60 pairs including ≥ some negatives; the eval reports false-match rate on them.
3. `GET .../embeddings/accuracy` returns the committed artifact when present and
   `{"has_results": false}` with HTTP 200 when the file is absent.
4. The committed artifact shows the chosen local model at **recall@1 ≥ baseline + 0.05** AND
   false-match rate on negatives **≤ baseline**; only then does the card badge read "beats baseline"
   (with `n`). A sub-threshold or regressed result is surfaced honestly (no massaging) and escalated
   to the review gate — it does not silently pass.
5. Frontend card renders metrics + `n` + badge; empty state when `has_results:false`. `npm run lint`
   and `npm run test` pass.

## Dependencies & sequencing

- **Depends on `in-process-provider`** (needs a runnable local provider) and `staleness-model-key`.
- Informs the final model pick for Aspects 2 & 5.

## Open questions / risks

- **Fixture bias (R2):** authored questions can flatter a model. Mitigate with paraphrase + negative
  pairs and by reporting false-match rate, not just recall. Consider a second author/agent for the
  negatives.
- Metric choice: recall@1 + MRR at 0.85 is the primary; document why (single-best-match, threshold
  gate). Keep it honest — this is retrieval quality on *our* set, not a universal benchmark.
