# PRD — Churn customer-level factor coverage

**Slug:** `churn-customer-factor-coverage` · **Branch:** `bug/worker-resolution-time-scoring`
**Type:** bug (+ the test gap that hid it) · **Created:** 2026-07-29
**Card:** `../_card/card.md` · **Tracked as:** DEV-TRACKING P0b

---

## Problem Statement

`_compute_heuristic_churn_risk` (`services/worker-service/src/tasks/analysis.py`) scores
customers on 9 weighted factors totalling 100 points. One of them has never worked, and
four more have never been proven to work.

**The broken one.** Line 821 imports `FeedbackWorkflowEvent` from
`src.models.feedback_workflow_event`, a submodule that does not exist in worker-service —
the class is exported from `src.models`. The enclosing `except Exception: pass` swallows the
`ModuleNotFoundError`, so `resolution_score_pts` is permanently `0` and `resolution_label`
never leaves its `"Insufficient resolution data"` default.

This is the **third instance** of one bug class in this repo: worker-service importing a
backend-api module it can never have, inside a bare `try/except`. The first was fixed as
GitHub #3 (`f5d43234`); the second in `automations-delivery-integrity` (`52c763dd`).

**Why it matters more than 10 points.** Every customer loses the same 10 points, so this is
not a uniform offset that cancels out — a customer with genuinely slow resolution *should*
rank above one resolved quickly, and never does. Risk banding, the at-risk queue, alert
thresholds and the isotonic calibrator all key off this ordering. And because M1.4 shipped
churn **explainability**, every customer's factor breakdown has always displayed
"Insufficient resolution data" — a confident explanation of a factor that never ran.

**Why it survived.** All 9 factors sit in individual `try/except Exception: pass` blocks.
The 38 tests in `tests/test_churn_factor_computation.py` cover the four *feedback-level*
factors behaviourally, but the five *customer-level* factors are only asserted in the
`customer_email=None` / `db=None` cases — where `0` is the correct answer. Across both churn
test files, the function is **never called with a real DB session**; the only `db=`
occurrence is `db=None`.

| Factor | Max | Behavioural coverage | Status |
|---|---|---|---|
| `sentiment_trend` | 15 | none | unproven |
| `feedback_frequency` | 10 | none | unproven |
| `resolution_time` | 10 | none | **provably broken** |
| `pain_severity` | 10 | none | unproven |
| `feature_density` | 5 | none | unproven |
| 4 feedback-level factors | 55 | good | fine |

**50 of 100 points are untested.** Fixing only the import would leave four untested factors
and the swallowing pattern intact — i.e. it would fix this bug without fixing the reason it
was invisible.

---

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| `resolution_time` contributes | A customer with >7-day average resolution scores 10, not 0 |
| The other four are proven, not assumed | Each has a DB-backed test asserting a non-zero score under the right conditions |
| The class of bug can't hide again | No factor swallows an exception silently; a failure logs |
| No score regression | The four feedback-level factors keep byte-identical behaviour |

---

## Requirements

### Must-have

- **R1** — Fix the import to `from src.models import FeedbackWorkflowEvent`. Move it to
  module level, consistent with the fix already made in `analysis.py` for the automations
  trigger: an import that cannot succeed should fail at startup, not per-item.
- **R2** — DB-backed tests for **all five** customer-level factors, each proving a non-zero
  score under conditions that should produce one. This is the requirement that prevents
  recurrence; R1 alone does not.
- **R3** — Replace every `except Exception: pass` in the 9 factor blocks with a logged
  warning naming the factor. Keep the per-factor isolation (one failing factor must not
  void the whole score) — the defect is the silence, not the isolation.
- **R4** — If R2 shows any of the other four factors is also broken, **report it and stop**
  rather than silently expanding scope. That is a separate decision for the operator.

### Should-have

- **R5** — A regression test asserting `resolution_time` is reachable at all, in the spirit
  of the automations import guard: fail loudly if the symbol stops resolving.

### Out of scope (this branch)

- Recomputing historical `churn_risk_factors` rows — see Open Questions.
- Re-tuning factor weights. The weights are a product decision; this is a defect fix.
- Any change to the isotonic calibrator (it refits weekly on its own — see Risk 2).
- The other two `except Exception: pass` sites outside the factor loop.

---

## Technical Considerations

**Service:** `services/worker-service` only. No migration, no API change, no frontend change.
The factor breakdown UI reads `churn_risk_factors` and needs no update — it will simply start
showing real resolution labels.

**Test harness:** the existing churn tests are pure-Python with hand-built feedback objects
and no DB. R2 requires a session. Check whether `worker-service/tests/conftest.py` provides
one; if not, the in-memory SQLite pattern used elsewhere in the worker suite applies.

**Command:** `cd services/worker-service && ./venv/bin/pytest tests/test_churn_factor_computation.py -v`
(venv built with `python3.12`; worker suite was fully green at 1372 passed on 2026-07-29).

**No plan gate.** `SELF_HOSTED=true`.

---

## Risks & Open Questions

| # | Risk | Mitigation |
|---|---|---|
| 1 | Fixing the factor **changes every customer's churn score** on next analysis. Scores rise by up to 10 and re-rank. Anyone watching a dashboard sees movement with no release note. | Call it out in the changelog explicitly. This is a correction, not a regression, but it will look like drift. |
| 2 | The isotonic calibrator was fit on factor values where resolution was always 0. Its mapping is now slightly miscalibrated. | Self-healing: the weekly refit (Mondays 07:45 UTC) retrains on current values. No action needed, but worth stating rather than discovering. |
| 3 | R2 may reveal a second broken factor, expanding a "one-line fix" mid-flight. | R4 — report and stop; do not silently widen. |
| 4 | Historical `churn_risk_factors` JSON keeps the stale `"Insufficient resolution data"` label until each item is re-analysed. | Open question below. |

**Open questions**
1. **Backfill historical scores?** `backend-api/scripts/backfill_churn_factors.py` exists and
   could recompute. Doing so rewrites every stored churn factor set — a visible, bulk data
   change. Fixing forward leaves old rows stale but touches nothing. *Recommendation: fix
   forward; offer the backfill as a documented opt-in command.*
2. Should the changelog entry state the scoring change plainly, given churn scores are the
   product's headline signal? *Leaning yes — silent score movement is worse than an
   awkward note.*

---

## Self-critique (Phase 4)

- 🟡 **No measurable "how wrong was it" number.** The PRD asserts re-ranking but does not
  quantify how many customers change risk band. A quick query against the dev DB would make
  the changelog honest — but the local DB is mid-migration-failure (pre-existing drift), so
  this may not be cheaply answerable. Flagged rather than hand-waved.
- 🟡 **R2 is stated as "prove the other four" but their correct-behaviour conditions are
  inferred from reading the code, not from a spec.** If a factor's intended semantics are
  ambiguous, the test will encode the current implementation as correct — which is
  characterization, not verification. Call that out per-factor where it applies.
- 🟢 Scope, service boundary and out-of-scope are unambiguous.

**The question I'd want answered before greenlighting:** if four of nine factors have never
been executed in a test, what is the actual evidence that the churn score — the product's
headline number, the thing playbooks and alerts fire on — measures anything at all?
