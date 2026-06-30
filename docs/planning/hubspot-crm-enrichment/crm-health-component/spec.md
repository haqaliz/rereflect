# Aspect Spec — crm-health-component

**Parent PRD:** `../prd.md` · **Slug:** `hubspot-crm-enrichment`

## Problem slice & user outcome

An operator can opt CRM signal into the health/churn score. By default (weight 0%)
nothing changes — existing scores are untouched. When the operator raises
`health_weight_crm`, an imminent renewal on a low-base account lowers the customer's
health, surfacing it as at-risk. Mirrors the shipped opt-in `usage_component` (M4.2)
exactly.

## In scope

- **Columns** (backend-api, Alembic chained with the other aspects):
  - `customer_health_scores.crm_component` (Float/Int, nullable)
  - `customer_health_history.crm_component` (nullable)
  - `org_ai_config.health_weight_crm` (Int 0–100, **default 0**)
- **`_compute_crm_component(db, org_id, email, now)`** in
  `src/services/health_score_service.py`:
  - Reads `crm_enrichment` for `(org, email)` inside a SAVEPOINT, **never raises**,
    returns neutral `50.0` on no row / no data (same contract as
    `_compute_usage_component`).
  - Scoring intuition (document honestly): healthy lifecycle / no near renewal →
    higher; **renewal within N days** (e.g. ≤30) with no offsetting signal → lower
    component (more risk). Deterministic, tunable constants at module top.
- **Weight wiring:** add `crm` to module `WEIGHTS` (default 0.0), to
  `_get_org_weights` (read `OrgAIConfig.health_weight_crm`), and to the weighted sum
  in `compute_health_score`; add `crm_component` to its return dict + the upsert in
  `update_customer_health` + history snapshot.
- **Weight validation:** the existing health-weights endpoint
  (`PUT /api/v1/categories/health-weights`) must accept/validate `crm` so the 5→6
  weights still sum to 100 (extend its schema + the sum check).
- **Worker mirror:** add `health_weight_crm` to the worker's `OrgAIConfig` mirror
  (R4) — or document that the worker only triggers recompute and backend-api owns
  weight reads (tech-plan decides; default: add the column to the mirror).

## Out of scope (this aspect)

- Pulling/storing CRM data (→ `hubspot-sync`; this aspect only *reads*
  `crm_enrichment`).
- Profile card / timeline (→ `crm-profile-and-timeline`).
- Connection (→ `hubspot-connection`).

## Acceptance criteria (testable)

- With `health_weight_crm = 0` (default), `compute_health_score` returns the **same**
  score as before this aspect (regression: existing health tests still pass).
- `_compute_crm_component` returns 50.0 (neutral) when no `crm_enrichment` row
  exists, and never raises even if the table/row is malformed.
- A customer with a renewal in ≤30 days scores a **lower** `crm_component` than one
  with no near renewal (deterministic assertion).
- With `health_weight_crm > 0`, the weighted sum shifts by the expected amount
  (mirror `tests/test_health_usage_component.py` + `test_health_weights.py`).
- `PUT health-weights` rejects a 6-weight set that doesn't sum to 100 and accepts one
  that does; persists `health_weight_crm`.
- `crm_component` is persisted on `CustomerHealth` and snapshotted in history.

## Dependencies & sequencing

- **Reads `crm_enrichment`** from `hubspot-sync` — agree the table schema first;
  can be built in parallel against that schema (use a fixture row in tests).
- Shares the Alembic migration chain (adds `crm_component` ×2 + `health_weight_crm`).
- No frontend work here except the health-weights settings UI may need a `crm`
  slider — small; coordinate with `crm-profile-and-timeline` or fold into that
  aspect's frontend task (tech-plan decides).

## Open questions / risks

- Exact component formula (renewal-proximity curve, ARR influence) — keep simple,
  deterministic, documented; this is a heuristic, not a trained model (state so).
- Must not regress existing scores at weight 0 — that's the headline test.
