# Aspect Spec — trend-detection-and-health

Parent PRD: `../prd.md`
Depends on: `../rollup-rewindow-fix/spec.md`, `../usage-history-snapshot/` (both must land first)

## Problem slice & outcome

With re-windowing fixed (`rollup-rewindow-fix`) and a durable daily snapshot in place
(`usage-history-snapshot`), the data to detect a *direction* exists — but nothing reads it. The
usage component still measures level only: a customer who fell from 20 active days a fortnight
to 6 scores the same as one who climbed from 2 to 6.

Outcome: each customer carries a `usage_trend_state` and a signed `usage_trend_pct` derived from
**their own** activity ~14 days ago, and a **bounded** penalty on the **usage component of the
health score only** reflects a real decline. Nothing else in the churn stack moves.

## Evidence (observed, verified in this worktree)

- **The calibration boundary is real and load-bearing.** `probability_updater.update` computes
  the probability from `health.churn_risk_component` **alone** —
  `p, low, high = _predict_with_interval(health.churn_risk_component or 0, model)`
  (`services/worker-service/src/services/probability_updater.py:75`) — then applies the org's
  fitted isotonic model (`:74`) and derives `time_to_churn_bucket` from it (`:77`, `:82`).
  `churn_risk_component` is the inverted average of feedback-level `churn_risk_score`
  (`backend-api/src/services/health_score_service.py:191` → `_compute_churn_component`). Usage
  reaches `health_score` (`health_score_service.py:217`) and **never** reaches
  `churn_risk_component`. Folding usage in would re-point a model fitted on the feedback-only
  distribution, with no error surfaced.
- **The usage component is a single scalar read.** `_compute_usage_component` does a raw
  `SELECT usage_score FROM customer_usage ...` inside a SAVEPOINT and returns `50` on any failure
  (`health_score_service.py:65-105`). It is the one place a usage-only adjustment can be applied
  without touching anything else.
- **The stored `usage_score` has other consumers.** `classify_segment` gates `power_user` on
  `usage.usage_score >= POWER_USER_USAGE_SCORE_THRESHOLD` (=75)
  (`backend-api/src/services/segment_service.py:58`, `:147-154`). Mutating the stored
  `usage_score` with a trend penalty would silently reclassify segments — out of this aspect's
  boundary.
- **The double-count is quantified.** `compute_usage_score` blends recency at `WEIGHT_RECENCY =
  0.50`, frequency at `0.30`, breadth at `0.20`
  (`backend-api/src/services/usage_score_service.py:80-82`), with 20-point band steps
  (`:37-42`, `:54-59`). A declining customer already loses ~10 blended points per recency band
  step and ~6 per frequency band step *before* any trend penalty is applied.
- **The "NO magic numbers" convention is explicit**, stated as a section header in
  `usage_score_service.py:24-26` and honoured throughout — every threshold and every band score
  is a module-level named constant.
- **Both service copies are byte-identical today.** `diff` of
  `backend-api/src/services/usage_score_service.py` against
  `worker-service/src/services/usage_score_service.py` reports no differences; likewise for
  `segment_service.py`. Each carries the "DUPLICATED: keep in sync" header at lines 1-2.
- **The daily pass only refreshes health on a score move.**
  `if abs(new_score - old_score) >= _HEALTH_RECOMPUTE_DELTA:` (=2)
  (`worker-service/src/tasks/usage_metrics.py:31`, `:346-347`). A trend-state transition does not
  move `usage_score`, so with no change here a newly-`declining` customer's health would not be
  recomputed until something else nudged their score.
- **The profile response is built from `CustomerHealth`.** `serialize_customer_profile` reads
  only that record, and reaches sideways for cross-table fields via
  `**_read_crm_fields(record, db)` (`backend-api/src/services/customer_profile_serializer.py:88`,
  `:92`). `CustomerProfileResponse` currently ends the component block at `usage_component`
  (`backend-api/src/api/routes/customers.py:118`). Trend lives on `customer_usage`, so it needs
  the same sideways-read treatment.

## In scope

**Schema.** `customer_usage` gains:
- `usage_trend_state` — String, NOT NULL, server default `'insufficient_history'`.
- `usage_trend_pct` — Float, nullable; NULL whenever state is `insufficient_history`.

Alembic migration in `backend-api/alembic/`. (`active_days_14d` is added by
`rollup-rewindow-fix`; do not re-add it.)

**Pure trend core, in `usage_score_service.py` (both copies).** Two pure functions plus named
constants, in the existing style — no I/O, importable by backend-api and worker-service:

- `classify_usage_trend(current_active_days_14d, baseline_active_days_14d, baseline_age_days) -> (state, pct)`
- `apply_trend_penalty(usage_component, trend_state) -> int`

Indicative constant set (values tunable in tech-plan **within** the invariants in Acceptance
criteria; names and the no-magic-numbers rule are not negotiable):

```
TREND_LOOKBACK_TARGET_DAYS      = 14
TREND_LOOKBACK_MIN_DAYS         = 12
TREND_LOOKBACK_MAX_DAYS         = 16
TREND_MIN_BASELINE_ACTIVE_DAYS  = 5      # baseline floor; below this → insufficient_history
TREND_DECLINING_PCT             = -30.0  # ≤ this → declining
TREND_SHARP_DECLINE_PCT         = -60.0  # ≤ this → sharp_decline
TREND_PENALTY_DECLINING         = 8
TREND_PENALTY_SHARP_DECLINE     = 15
TREND_PENALTY_MAX               = 15     # hard cap, asserted in test
TREND_STATE_INSUFFICIENT_HISTORY / _STABLE / _DECLINING / _SHARP_DECLINE  (slug constants)
```

**Lookback semantics.** Select the snapshot from `customer_usage_history` for
`(organization_id, customer_email)` whose `snapshot_date` is **nearest to
`TREND_LOOKBACK_TARGET_DAYS` back**, among those inside the closed band
`[TREND_LOOKBACK_MIN_DAYS, TREND_LOOKBACK_MAX_DAYS]`. If none falls inside the band → state is
`insufficient_history`, pct is NULL. **Never** widen the band, never fall back to "oldest
available", never compare against a snapshot of unknown age. `snapshot_date` is UTC, matching
the `datetime.utcnow()` used throughout the usage pipeline.

**Guards (all → `insufficient_history`, pct NULL).** No in-band snapshot; baseline
`active_days_14d` is NULL; baseline `active_days_14d < TREND_MIN_BASELINE_ACTIVE_DAYS`; current
`active_days_14d` is NULL.

**`usage_trend_pct` units.** Signed **percent**, `(current - baseline) / baseline * 100`, rounded
to 2 dp. `-50.0` means active days halved. Increases are positive and always classify `stable`.

**Wiring.** Compute and persist trend inside the daily `recompute_usage_scores` pass
(`worker-service/src/tasks/usage_metrics.py:306-355`), after re-windowing and after today's
snapshot write. Trend is a daily-cadence signal only — the event-processing path does **not**
compute it (it has no cheap access to history and must stay hot-path cheap), so trend is at most
24h stale. Extend the health-refresh trigger so a **trend-state transition** also calls
`_call_update_health`, not only a `usage_score` move ≥ `_HEALTH_RECOMPUTE_DELTA`.

**Health penalty.** Applied in `_compute_usage_component`
(`backend-api/src/services/health_score_service.py:65-105`) only: extend the existing SAVEPOINT
query to also select `usage_trend_state`, then return
`apply_trend_penalty(usage_score, trend_state)`, clamped to `[0, 100]`. The penalty is applied
**only** when a real rollup row was read — the neutral `50` fallback (missing table, missing row,
any error) is returned unpenalised.

**API.** `usage_trend_state: Optional[str]` and `usage_trend_pct: Optional[float]` on
`CustomerProfileResponse` (`customers.py:106-145`), populated by a
`_read_usage_trend_fields(record, db)` helper in `customer_profile_serializer.py` mirroring
`_read_crm_fields` — same never-raises, all-None-on-failure contract.

**Sync + tests.** Every scoring change lands in **both** copies of `usage_score_service.py`, and
the trend core is tested in `backend-api/tests/` **and** `worker-service/tests/`.

## Out of scope

- **`churn_risk_component`, `churn_probability`, `churn_probability_low/high`,
  `calibration_model_id`, `time_to_churn_bucket`, and the isotonic calibration model — untouched.
  This is the single most important boundary in this aspect.** No file under
  `worker-service/src/tasks/churn_calibration.py` or
  `backend-api/src/services/churn_calibrator.py` is edited; `probability_updater.py` is edited
  only if the trend-triggered health refresh requires it, and never in a way that changes what
  feeds `_predict_with_interval`.
- The `_should_skip` hysteresis guard (`probability_updater.py:118-141`) — a known related
  defect, recorded in the PRD, not fixed here.
- Mutating the stored `customer_usage.usage_score` — the penalty is a health-component
  adjustment, not a rollup rewrite. Segment classification (`power_user`, `silent_churner`) must
  see the same `usage_score` as before this aspect.
- `segment_service.py` logic changes of any kind.
- The snapshot table, its write, and its prune (`usage-history-snapshot`).
- Re-windowing and `active_days_14d` derivation (`rollup-rewindow-fix`).
- All frontend work — the Usage Activity card and the weights editor
  (`frontend-trend-and-weights`). This aspect ships the API fields it consumes, nothing more.
- Timeline events, automation triggers, seasonality dampening, per-org thresholds (N1–N4).
- D2 / D3.

## Acceptance criteria (testable)

1. **Nearest-in-band lookback.** Given snapshots at 10, 13 and 20 days back, the comparison uses
   the 13-day snapshot. Given snapshots at 10 and 20 days back only (none in 12–16), the state is
   `insufficient_history` and `usage_trend_pct` is NULL. Asserted directly, not via the score.
2. **Nearest wins inside the band.** Given snapshots at 12 and 15 days back, the 15-day one is
   used (nearer to `TREND_LOOKBACK_TARGET_DAYS = 14`); given 12 and 16, the tie is broken
   deterministically by a rule stated in the implementation and asserted by test.
3. **Small-number guard.** A customer with baseline `active_days_14d = 2` and current `= 1`
   yields `insufficient_history` with NULL pct — **not** `declining` at −50%. Same for baseline
   `= 0` and baseline `= None` (no division-by-zero path exists).
4. **State thresholds.** Baseline 10 → current 10 is `stable` (pct `0.0`); 10 → 12 is `stable`
   (pct `+20.0`); 10 → 6 is `declining` (pct `−40.0`); 10 → 3 is `sharp_decline` (pct `−70.0`).
   All four states are reachable and mutually exclusive.
5. **Bounded penalty.** For every possible `(usage_component, trend_state)` pair,
   `apply_trend_penalty(c, s) >= c - TREND_PENALTY_MAX` and the result is in `[0, 100]`.
   Property-style test over the full 0–100 range, so the bound cannot regress silently.
6. **Double-counting bound (explicit).** A customer whose recency band has already stepped down
   **and** whose frequency band has already stepped down — i.e. already penalised through
   `WEIGHT_RECENCY = 0.50` and `WEIGHT_FREQUENCY = 0.30` — and who is additionally classified
   `declining`, must retain a usage component of **≥ 55** when their pre-decline component was
   ≥ 75. A single moderate decline must never drive an otherwise-healthy customer's usage
   component to near-zero. The test states the arithmetic in a comment so the overlap is visible
   to the next reader.
7. **`stable` and `insufficient_history` are free.** `apply_trend_penalty(c, 'stable') == c` and
   `apply_trend_penalty(c, 'insufficient_history') == c` for all `c` — warm-up must never look
   like decline.
8. **The neutral fallback is never penalised.** With no `customer_usage` row (or a raising
   query), `_compute_usage_component` returns exactly `50` regardless of any trend value.
9. **Byte-stability at weight 0.** For an org with `health_weight_usage = 0`, health scores are
   identical before and after this aspect across a fixture spanning `insufficient_history`,
   `stable`, `declining` and `sharp_decline` customers. Characterization-tested, extending the
   fixture introduced by `rollup-rewindow-fix`.
10. **No churn-stack movement.** For a customer transitioning `stable → sharp_decline` with **no
    new feedback**, `churn_risk_component`, `churn_probability`,
    `churn_probability_low/high`, `calibration_model_id` and `time_to_churn_bucket` are all
    unchanged after the daily pass. This test is the executable form of the calibration
    boundary — it must exist even though it asserts absence.
11. **Stored `usage_score` and segment are unchanged.** After a customer becomes `declining`,
    `customer_usage.usage_score` equals what `compute_usage_score` returns for that row, and
    their `segment` is what `classify_segment` would return from the unpenalised score.
12. **Trend transition refreshes health.** A customer whose `usage_score` moves < 2 points but
    whose `usage_trend_state` changes triggers `update_customer_health`. (Without this the
    penalty would not reach the health score until an unrelated event.)
13. **Idempotency.** Running the daily pass twice with the same `now` produces identical
    `usage_trend_state` / `usage_trend_pct` and no additional health recomputations on the
    second run.
14. **Trend-distribution sanity bound.** On a fixture of ≥ 50 customers with **flat** usage
    (baseline and current `active_days_14d` equal, or differing by ≤ 1) and valid in-band
    snapshots, **≥ 95 % classify `stable`** and **zero classify `sharp_decline`**. This is the
    only criterion that fails for the right reason if the thresholds are miscalibrated — every
    other test above passes green under thresholds loose enough to make the signal pure noise.
    It is a sanity bound, not an accuracy claim.
15. **Both copies tested.** The trend core is exercised by tests under `backend-api/tests/` and
    under `worker-service/tests/`, and a test asserts the two `usage_score_service.py` copies
    remain textually in sync (or the tech-plan states an equivalent enforced mechanism).
16. **API surface.** `GET /api/v1/customers/{email}` returns `usage_trend_state` and
    `usage_trend_pct`; a customer with no `customer_usage` row returns
    `usage_trend_state = "insufficient_history"` (or NULL, per the tech-plan's stated choice)
    and `usage_trend_pct = null`, and the endpoint never 500s when the rollup table is absent.

## Dependencies & sequencing

- **Third aspect.** Hard-blocked on both predecessors: `rollup-rewindow-fix` supplies a
  trustworthy `active_days_14d` (a trend over frozen fields is meaningless), and
  `usage-history-snapshot` supplies the rows the lookback queries. Do not start before both are
  merged.
- `frontend-trend-and-weights` depends only on the API fields defined here (AC 16) — that
  contract should be frozen early so the frontend can proceed in parallel with the tests.
- Alembic is **single-head** in this repo; run a live `alembic heads` before authoring the
  migration (static parsing has repeatedly produced a false "multiple heads" reading).
- The migration is additive and nullable/defaulted — no backfill, no downtime concern. Trend is
  inert until the first daily run *and* a snapshot enters the 12–16 day band.

## Open questions & risks

- **Where the penalty is applied.** This spec places it in `_compute_usage_component`
  (health-only) rather than inside `compute_usage_score`, deliberately: the stored `usage_score`
  feeds `POWER_USER_USAGE_SCORE_THRESHOLD` (`segment_service.py:58`) and the Usage Activity card,
  and penalising it would silently reclassify segments — beyond this aspect's boundary. The
  cost is that the trend core lives in `usage_score_service.py` while its *application* lives in
  `health_score_service.py`. If tech-plan reverses this, it must handle segment impact
  explicitly; it is not a free swap.
- **Threshold calibration is unvalidatable pre-launch.** There is no labelled corpus of
  "genuinely declining" customers, and self-hosting gives no telemetry. AC 14 is a *sanity*
  bound only — it proves the thresholds are not degenerate, not that they are predictive. The
  PRD deliberately promises no accuracy lift; this spec must not imply one.
- **Banded vs linear penalty.** Banded is chosen (house style, matches every existing component
  in `usage_score_service.py`). Linear-in-pct would be smoother and is a legitimate tech-plan
  alternative, provided `TREND_PENALTY_MAX` still caps it and AC 5/6 still hold.
- **Tie-breaking at 12 vs 16 days** (AC 2) is arbitrary but must be *deterministic and stated*;
  a non-deterministic pick makes AC 13 (idempotency) flaky rather than failing.
- **Seasonality.** A company-wide holiday reads as a genuine decline. The baseline floor
  (`TREND_MIN_BASELINE_ACTIVE_DAYS`) suppresses only the small-number case, not this one. Known
  limitation, deferred to N3, and worth a sentence in the operator docs so a December spike in
  `declining` states is not read as a bug.
- **Lookback query cost.** One `customer_usage_history` read per rollup row per daily pass. The
  `(organization_id, customer_email, snapshot_date DESC)` index specified by
  `usage-history-snapshot` must exist before this lands, or the daily pass becomes a full scan
  per customer. Prefer a single batched query over a per-row query; the plan should say which.
- **The hysteresis interaction.** Even with AC 12 forcing a health recompute,
  `probability_updater._should_skip` will still skip the probability update for a customer with
  no new feedback (`probability_updater.py:118-141`). That is correct and intended here — the
  probability *should* not move — but it means "the trend changed and nothing about churn
  probability changed" is expected behaviour an operator may find surprising. Documentation
  concern, not a code change.
