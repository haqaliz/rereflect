# Spec — `customer-factor-coverage`

**Parent PRD:** `../prd.md` · Single aspect · Service: **worker-service only**

## Problem slice

Fix the dead `resolution_time` factor, and close the coverage hole that let it stay dead:
five customer-level factors (50 of 100 points) are never executed against a real DB session
in any test.

## Decisions already made (do not re-litigate)

- **Fix forward, no backfill.** Historical `churn_risk_factors` rows keep their stale values
  until naturally re-analysed. Document `backend-api/scripts/backfill_churn_factors.py` as an
  opt-in operator command instead of running it.
- **Changelog states the score movement plainly** — churn scores rise by up to 10 points and
  some customers change risk band, because a factor was never running.

## In scope

- **S1** — `from src.models import FeedbackWorkflowEvent`, hoisted to **module level**
  (matching the automations-trigger fix already in this file). An import that cannot succeed
  must fail at startup, not silently per feedback item.
- **S2** — DB-backed tests for **all five** customer-level factors, each proving a non-zero
  score under conditions that should produce one:

  | Factor | Max | Condition that must score |
  |---|---|---|
  | `sentiment_trend` | 15 | ≥2 prior feedbacks with sentiment declining >0.5 |
  | `feedback_frequency` | 10 | last-7d count > 2× the 30d weekly average |
  | `resolution_time` | 10 | ≥1 `status_changed`→`resolved` workflow event, >7 days after creation |
  | `pain_severity` | 10 | ≥3 feedbacks with `pain_point_severity` in (critical, major) in 30d |
  | `feature_density` | 5 | >50% of last-30d feedbacks are feature requests |

- **S3** — Replace every `except Exception: pass` in the nine factor blocks with
  `logger.warning` naming the factor. **Keep the per-factor isolation** — one failing factor
  must not void the whole score. The defect is the silence, not the isolation.
- **S4** — Regression guard: a test asserting the `FeedbackWorkflowEvent` symbol resolves,
  so this cannot silently regress.
- **S5** — Changelog entry per the decision above.

## Out of scope

- Running the backfill.
- Re-tuning factor weights (product decision, not a defect).
- The isotonic calibrator — it refits weekly (Mondays 07:45 UTC) and self-heals.
- `except` sites outside the nine factor blocks.

## Acceptance criteria

1. A customer with a resolved-after-9-days workflow event scores `resolution_time` **10**,
   with a label naming the average — not `"Insufficient resolution data"`.
2. A customer with a resolved-after-1-day event scores **0** with a "resolved within" label
   (proves the branch runs, not just that it returns non-zero).
3. Each of the other four factors has a DB-backed test producing its documented non-zero score.
4. `db=None` / `customer_email=None` behaviour is unchanged — all five still score 0.
5. The four feedback-level factors are byte-identical (existing 38 tests still pass).
6. Composite score still equals the sum of factor scores, capped at 100.
7. A simulated factor failure logs a warning and leaves the other eight intact.

## ⚠️ Stop condition (PRD R4)

If a DB-backed test shows **another** factor is also broken, **report it and stop.** Do not
silently expand scope — that is the operator's call. Two of these have already been found
this session; a third changes the picture.

## Testing notes

- Existing churn tests are pure-Python with hand-built objects and no DB. **Check whether
  `worker-service/tests/conftest.py` provides a session**; if not, use the in-memory SQLite
  pattern already used elsewhere in the worker suite.
- Match house style in `tests/test_churn_factor_computation.py` (module-level helpers like
  `make_simple_feedback`, class-grouped tests).
- Command: `cd services/worker-service && ./venv/bin/pytest tests/test_churn_factor_computation.py tests/test_churn_heuristic.py -v`
- Baseline: worker suite was **1372 passed, 0 failed** on 2026-07-29.
- Where a factor's intended semantics are ambiguous, the test encodes current behaviour —
  that is **characterization, not verification**. Say so in a comment on those tests.
