# Aspect Spec — health-component

Parent PRD: `../prd.md`

## Problem slice & outcome

The customer health score gains an **opt-in** 5th component (usage), defaulting to weight 0 so **no existing org's score changes** until an operator re-weights. The change is protected by a characterization test written RED before any scorer code.

## In scope

- **Characterization test FIRST (RED):** snapshot `compute_health_score()` output (score + 4 components + risk_level) for a fixture org/customer, then assert it is **identical** after the migration + 5th-component code land with `health_weight_usage = 0`.
- `org_ai_config.health_weight_usage INT NOT NULL DEFAULT 0` (`models/org_ai_config.py`) + Alembic migration.
- `_get_org_weights()` (`health_score_service.py:32-46`) returns 5 weights; default map adds `"usage": 0.0` so the four existing defaults (35/25/25/15) are unchanged.
- `_compute_usage_component(db, org_id, customer_email, now) -> int`: reads the `customer_usage` rollup's `usage_score`; **50 (neutral) when no rollup**. (Reuses the score computed in `usage-rollup-and-score`; this function just fetches/falls back.)
- `compute_health_score()` aggregation (`:68-75`) includes `usage_component * weights["usage"]`.
- Persist `usage_component` on `customer_health_scores` + `customer_health_history` (+columns, migration). Snapshot logic (`:182-255`) records it.
- Validation: extend the health-weights Pydantic validator + GET/PUT (`api/routes/categories.py:185-238`) to **5 fields summing to 100**, default usage 0.

## Out of scope

- Producing the `usage_score` itself (aspect `usage-rollup-and-score`).
- The ingestion endpoint and frontend bar.

## Acceptance criteria (testable)

1. **Score stability:** with `health_weight_usage=0`, `compute_health_score()` returns byte-identical score/components to pre-change for the fixture (RED→GREEN).
2. With usage weight raised (e.g. 35/20/20/15/10, sum=100) and a customer with `usage_score=20`, the health score moves predictably vs. weight 0.
3. A customer with **no usage rollup** gets `usage_component=50` and (at weight 0) an unchanged total.
4. Health-weights PUT rejects a 5-field body that doesn't sum to 100 (`422`); accepts one that does; GET returns all 5 with usage defaulting to 0.
5. `usage_component` is persisted on `customer_health_scores` and snapshotted to `customer_health_history` when it changes by ≥2.
6. Existing health-score tests still pass unchanged.

## Dependencies & sequencing

- **Plan this aspect first.** It defines the contract (`_compute_usage_component` reads `customer_usage.usage_score`) that `usage-rollup-and-score` fills.
- Reads `customer_usage` (created in `usage-rollup-and-score`); for isolated tests, fixture the rollup row directly or guard the read so a missing table/row → 50.

## Open questions / risks

- Migration ordering: this aspect adds the weight + component columns; the rollup aspect adds `customer_usage`. `_compute_usage_component` must not hard-fail if `customer_usage` doesn't exist yet (defensive try/None → 50).
- Confidence: should usage volume feed `confidence_score`? Slice 1 = no (keep confidence as-is to protect score-stability); note as v2.
