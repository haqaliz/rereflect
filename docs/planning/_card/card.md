# Card — churn resolution-time factor silently dead

**Type:** bug · **Slug:** `churn-customer-factor-coverage` · **Branch:** `bug/worker-resolution-time-scoring`
**Source:** freeform — found 2026-07-29 sweeping worker-service for imports that resolve to
nothing, during the `automations-delivery-integrity` work (merged `52c763dd`). No GitHub issue.
**Tracked as:** DEV-TRACKING **P0b**.

> `_card/card.md` is per-worktree by design; the previous card remains in `master` history.

---

## Brief (as given)

`services/worker-service/src/tasks/analysis.py:821` does

```python
from src.models.feedback_workflow_event import FeedbackWorkflowEvent
```

but that submodule does not exist in worker-service — the class lives at `src.models`
(`src/models/__init__.py:551`). Proven empirically:

```
>>> from src.models.feedback_workflow_event import FeedbackWorkflowEvent
ModuleNotFoundError: No module named 'src.models.feedback_workflow_event'
>>> from src.models import FeedbackWorkflowEvent
<class 'src.models.FeedbackWorkflowEvent'>          # works
```

The `except Exception: pass` at ~line 873 swallows it, so `resolution_score_pts` is always
`0` and `resolution_label` never leaves its default.

Fix: correct the import, and narrow the bare `except` so this class of failure cannot hide.

This is the **third instance of a recurring repo bug class** — worker-service importing
backend-api modules it can never have, inside a bare `try/except`. See CLAUDE.md
"Automations engine (two copies)" and the memory note.

---

## Phase 2 dig — what the brief got right, and what it missed

### Confirmed

- `_compute_heuristic_churn_risk(feedback, db)` in `worker-service/src/tasks/analysis.py` is
  the **only** implementation. There is no backend twin, so the two processes cannot disagree.
  (`backend-api/scripts/backfill_churn_factors.py:68` imports the worker's function by putting
  worker `src` on `sys.path`, with a stub fallback that hardcodes
  `"resolution_time": {"score": 0, ... "label": "Backfilled"}`.)
- Defaults at `analysis.py:700-701`: `resolution_score_pts = 0`,
  `resolution_label = "Insufficient resolution data"`.
- Factor assembled at `analysis.py:926`:
  `"resolution_time": {"score": resolution_score_pts, "max": 10, "label": resolution_label}`.
- Total is `sum(v["score"] for v in factors.values())`, capped at 100.

### Consequences the brief understated

1. **It is user-visible, not just numeric.** M1.4 shipped "AI explainability on churn risk:
   show factor breakdown". Every customer's breakdown has always read
   **"Insufficient resolution data"** for resolution time. Users have been shown a
   confident-looking explanation of a factor that never ran.
2. **Scores are not merely 10 points low — they are differently ranked.** A customer with a
   genuinely slow resolution history should gain 10 points relative to one resolved quickly.
   Since neither ever gains, the *ordering* between customers is wrong too, and everything
   downstream keys off it: risk banding, the at-risk queue, alert thresholds, and the
   isotonic churn calibrator that was fit on these very factor values.

### The real finding — why it survived, and what else is unproven

Every one of the 9 factors is wrapped in its own `try/except Exception: pass`. The test
suite covers the **feedback-level** factors for real behaviour, but the **customer-level**
factors are only asserted in the `customer_email=None` / `db=None` cases, where `0` is the
correct answer.

Across **both** churn test files (`tests/test_churn_factor_computation.py` — 38 tests — and
`tests/test_churn_heuristic.py`), `_compute_heuristic_churn_risk` is **never once called
with a real DB session.** The only `db=` occurrence in either file is `db=None`
(`test_churn_factor_computation.py:321`).

So five factors worth **50 of the 100 points** have **zero behavioural coverage**:

| Factor | Max | Behavioural coverage | Status |
|---|---|---|---|
| `sentiment_trend` | 15 | none | unproven |
| `feedback_frequency` | 10 | none | unproven |
| `resolution_time` | 10 | none | **provably broken** |
| `pain_severity` | 10 | none | unproven |
| `feature_density` | 5 | none | unproven |

**A one-line import fix would leave four untested factors and the swallowing `except`
pattern intact.** The fix that actually prevents recurrence is DB-backed tests for all five
— which simultaneously proves or disproves the other four.

## Open questions for the PRD

- Should the four unproven factors be in scope, or only proven-and-fixed?
- Do historical `churn_risk_factors` rows need recomputing, or is fixing forward enough?
  (`backfill_churn_factors.py` exists and could be reused.)
- Does the isotonic churn calibrator need a refit once the factor starts contributing?
- Should the bare `except Exception: pass` become a logged warning across all nine factors,
  or only the one being fixed?
