# Aspect — worker-detector

**PRD:** `../prd.md` (M1, M3, M3b, M5)
**Sequence:** 3rd. Depends on `config-and-migration` + `detector-core`.

## Problem slice

Wire the pure core to real data: scan each enabled org's usage history daily, find qualifying
sustained declines, and write `ChurnLabelSuggestion` rows — without touching the churn stack, without
being able to fail the parent task, and without flooding the queue during an instrumentation outage.

## User outcome

An operator with `usage_churn_labels_mode='active'` wakes up to a small number of well-evidenced
pending suggestions in the existing review queue.

## In scope

- New worker module (e.g. `services/worker-service/src/services/usage_decline_label_detector.py`)
  with a `detect_usage_decline_labels(org_id, db, ...)` entrypoint.
- **Placement:** runs off the daily `recompute_usage_scores` pass
  (`services/worker-service/src/tasks/usage_metrics.py:492-713`), in its own transaction,
  **after the daily snapshot commit at `:693-694`**.
  > **Correction (2026-07-23).** An earlier draft of this spec said to mirror "the M3.2c post-commit
  > drain seam (`:659-681`)". **That placement is wrong.** Verified order is: score/trend commit
  > (`:655-657`) → M3.2c drain seam (`:667-681`) → **snapshot write + commit (`:693-694`, separate
  > transaction, last)**. Today's snapshot row does not exist at the drain seam, so a detector there
  > reads history missing the current day — permanently one day stale, and the symptom would look
  > like an off-by-one in the sustain window rather than a placement error. See
  > `./plan_20260723.md` §1.
  - Per-org and per-customer `try/except` isolation: **one broken org or customer must never fail
    the parent task.** M3.2c pinned this shape; copy it.
  - It does **not** consume `pending_trend_transitions` (edge-triggered, wrong semantics — see PRD
    M1). It reads `customer_usage_history` rows directly.
- **Gating:** skip immediately unless `usage_churn_labels_mode` ∈ `{shadow, active}`.
  - `shadow` → evaluate fully, log what *would* be suggested (count + evidence), write **no**
    `ChurnLabelSuggestion` rows.
  - `active` → write suggestions.
- **Query:** batch-load the last `sustain_days + margin` snapshots for the org's customers in **one**
  query, grouped in Python — mirroring `_load_trend_baselines` (`usage_metrics.py:279-338`).
  Never query per customer. The composite index
  `ix_customer_usage_history_lookback (org, email, snapshot_date)` exists for exactly this.
- **M3b outage guard:** compute qualifying vs. eligible counts for the org **before** writing
  anything; if `outage_suspected(...)`, write nothing for that org and record a **surfaced** warning
  with the counts. No silent suppression.
- **Per-customer denials** (all → no suggestion): `last_active_at IS NULL`; an existing suggestion
  with the same natural key; the customer already has an active `CustomerChurnEvent`.
  Reuse `_existing_suggestion_row` / `_has_active_churn_event` semantics from
  `services/churn_suggestion_harvester.py:48-79`.
- **Write:** `ChurnLabelSuggestion(provider='usage_decline', external_opportunity_id=suggestion_key(...),
  suggested_churned_at=customer_usage.last_active_at, evidence=build_evidence(...), status='pending')`.
  - Wrap the insert in `db.begin_nested()` with `IntegrityError` → `skipped_existing`, reusing the
    race backstop at `churn_suggestion_harvester.py:142-161`.
- **Per-run cap** with a logged, surfaced count of anything dropped (house rule: no silent caps).

## Out of scope

- Any change to `classify_usage_trend`, `select_nearest_in_band_snapshot`, `apply_trend_penalty`,
  or the trend thresholds — read-only.
- **Any write to** `churn_risk_component`, `churn_probability`, `churn_probability_low/high`,
  `calibration_model_id`, `time_to_churn_bucket`, or the isotonic calibration. Hard fence.
- Changing `customer_usage_history` schema or the 180-day prune.
- Confirm/reject behaviour (already shipped, provider-agnostic).
- Backfill over existing history (PRD nice-to-have; history only began 2026-07-22).

## Acceptance criteria (testable)

1. `mode='off'` → detector writes nothing and performs no history query.
2. `mode='shadow'` → evaluates, logs a would-suggest count, writes **zero** `ChurnLabelSuggestion`
   rows.
3. `mode='active'` with a qualifying 7-day `sharp_decline` streak → exactly one suggestion, with
   `provider='usage_decline'`, the expected key, and `suggested_churned_at == last_active_at`.
4. Running the detector **twice** on the same unchanged streak → still exactly one row
   (idempotent via the natural key).
5. `last_active_at IS NULL` → no suggestion.
6. Customer with an existing active `CustomerChurnEvent` → no suggestion.
7. Cross-org isolation: org A's history never produces a suggestion for org B.
8. **Outage guard:** an org where >25% of eligible customers qualify (with population ≥ min) →
   **zero** rows written and a warning recorded.
9. Same qualifying share in a tiny org (population < min) → suggestions **are** written.
10. A raised exception for one customer does not prevent other customers being processed, and does
    not fail `recompute_usage_scores`.
11. Fires **strictly after** the parent commit — assert in-loop regression fails loudly, as M3.2c
    did with an in-`side_effect` assertion (`test_usage_trend_trigger_seam.py` pattern).
12. Batch query count does not scale with customer count (assert ≤ a small constant number of
    history queries for N customers).
13. **`test_usage_trend_churn_boundary.py` remains green and UNMODIFIED.**
14. Per-run cap: with cap+N qualifying customers, exactly cap rows written and the dropped count
    logged.

## Dependencies & sequencing

- Needs `config-and-migration` (the mode column, worker-side mirror) and `detector-core` (all pure
  functions).
- `frontend-settings-and-evidence` can proceed in parallel once the evidence shape is fixed.

## Open questions / risks

- Whether to run inside `recompute_usage_scores` or as a separate chained task. Spec says inside,
  post-commit (M3.2c precedent, no new beat); a planner may prefer a separate task for isolation —
  if so, it must still run after the snapshot write, or it reads stale history.
- Cost at large customer counts: the streak read is wider than M3.2c's single-baseline read.
  Measure; if it's heavy, narrow the window to exactly `sustain_days` rows.
