# Aspect — `trigger-registration`

**Slice:** register `usage_trend` as a first-class trigger type in the backend, with its
edge-triggered severity semantics.

**PRD requirement:** M2 (semantics), M6 (backend half).

---

## Problem slice & outcome

The automation engine can validate, store and evaluate a `usage_trend` rule. No firing seam yet
— that is `worker-trend-evaluator`.

## In scope

1. `VALID_TRIGGER_TYPES` — add `"usage_trend"` (`api/routes/automations.py:49-55`).
2. `UsageTrendConfig` Pydantic schema + branch in `TriggerSchema.validate_trigger`
   (`:74-127`, `:180-201`):
   - `states: list[str]`, non-empty, subset of `{"declining", "sharp_decline"}`
   - `"stable"` and `"insufficient_history"` are **rejected (422)** — neither can be entered as
     a worsening transition, so accepting them would create a rule that can never fire
3. `_trigger_usage_trend(cfg, context)` + dispatch branch
   (`automation_engine.py:208-225`), with context shape
   `{"old_trend_state": str, "new_trend_state": str, "customer_email": str}`.
4. Context-shape docstring parity (`automation_engine.py:76-81`).
5. A shared severity helper — the single source of truth for the ordering, used by both the
   backend checker and (mirrored) the worker evaluator.

## Behavior — the firing rule

Severity ranking: `stable (0) < declining (1) < sharp_decline (2)`.
`insufficient_history` has **no rank**.

Fire when **all** hold:
1. `new_trend_state` ∈ `cfg["states"]`
2. both `old_trend_state` and `new_trend_state` are ranked (neither is
   `insufficient_history`, neither is `None`)
3. `rank(new) > rank(old)` — strictly worsening

Never fire on: equal states, any improvement, or any transition touching
`insufficient_history` in either direction (the baseline-seed rule, PRD M2).

## Out of scope

- The worker-side evaluator and the daily seam (`worker-trend-evaluator`).
- Any frontend (`automations-frontend`).
- `seed_churn_cooldowns` — stays churn-only. Edge-triggering removes the stampede mode it
  guards against (PRD M2); do **not** extend it.

## Acceptance criteria

- **AC1** — Each firing transition (`stable→declining`, `stable→sharp_decline`,
  `declining→sharp_decline`) returns `True` when the target state is configured.
- **AC2** — `declining→declining` returns `False`.
- **AC3** — Every transition involving `insufficient_history`, in **both** directions, returns
  `False` — including `insufficient_history→sharp_decline`. This is the warm-up guard (PRD E3)
  and deserves an explicit named test.
- **AC4** — Improvements (`sharp_decline→declining`, `declining→stable`) return `False`.
- **AC5** — A missing/`None` `old_trend_state` or `new_trend_state` returns `False`, never
  raises (mirrors `_trigger_churn_probability`'s never-fire-on-missing-signal behavior at
  `automation_engine.py:329-330`).
- **AC6** — API: creating a rule with `states: ["declining"]` succeeds; `states: []`,
  `states: ["stable"]`, and `states: ["insufficient_history"]` each return 422.
- **AC7** — The other four trigger types are unaffected — existing engine tests green.

## Dependencies & sequencing

Independent of the snapshot/timeline aspects; can run in parallel with them.
**`worker-trend-evaluator` depends on this** for the config shape and the severity helper.

## Risks / open questions

- The severity helper will be needed by the worker too, which cannot import backend-api code
  (PRD F3/R5). Expect it to be duplicated, following the existing `usage_score_service.py`
  precedent (duplicated with a "keep in sync" header comment). Decide the file location here so
  the worker aspect mirrors it rather than inventing a second shape.
