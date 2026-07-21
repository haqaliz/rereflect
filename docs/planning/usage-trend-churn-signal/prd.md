# PRD — Usage Trend Churn Signal

**Slug:** `usage-trend-churn-signal`
**Type:** feat
**Branch:** `feat/usage-trend-churn-signal`
**Status:** Draft (pre-review-gate)
**Source:** Freeform, selected via `rereflect-next` 2026-07-21. No GitHub issue.
**Inputs:** `docs/planning/_card/card.md`, `docs/planning/_card/understanding.md` (Phase 2 dig synthesis)

---

## Problem Statement

Rereflect's customer health score has had a product-usage component since M3.2
(`AI-TRACKING.md:207`), but it measures **level, not direction**. It can tell you a customer is
active or inactive right now; it cannot tell you a customer is *sliding*.

The naive framing — "detect the customer who stopped logging in" — is already solved. Recency
decays on its own (bands at 2/7/14/30/60 days, weight 0.50, `usage_score_service.py:93-114`),
and the `dormant` segment fires at >30 days since `last_active_at`
(`segment_service.py:133-137`). Total silence is covered.

**The genuinely uncovered case is the engaged-but-declining customer**: one who drops from 20
active days a month to 3 but still logs in weekly. Their recency stays healthy, so nothing
fires — and by the time recency degrades enough to notice, they have effectively already left.
This is the population where intervention is still possible, and it is invisible today.

It is invisible for a specific, verified reason.

### The defect that makes it invisible (D1)

`_compute_rollup_from_events` computes `active_days_7d/30d` and `login_count_7d/30d` against
`now` (`worker-service/src/tasks/usage_metrics.py:39-89`). It has **exactly one call site**, on
the event-processing path (`:208`). The daily `recompute_usage_scores` (`:306-355`) only calls
`compute_usage_score(row, now)` — it never re-derives the window fields.

So for a customer whose event rate falls, the frequency fields **freeze at their last-event
values**. Only recency moves. Verified consequences:

- `usage_score`'s frequency term (weight 0.30) stays inflated indefinitely.
- **`silent_churner` is unreachable.** It gates on `active_days_30d < 5`
  (`segment_service.py:120-130`) — the segment built to catch silent customers can never fire
  for one.
- The existing regression test passes only because its fixture hand-sets `active_days_30d=0`
  (`worker-service/tests/test_usage_metrics.py:359`), presupposing the re-windowing that does
  not happen. Green test, wrong production behaviour.

**D1 is therefore not adjacent cleanup — it is the feature.** A decline signal computed from
frozen frequency fields would be meaningless. Fixing re-windowing is what makes any
direction-aware usage signal possible.

### Evidence this is real

- `docs/planning/product-usage-enrichment/prd.md:67` and `:126` list "add a usage factor to the
  9-factor churn scorer" as explicit v2 of the shipped M3.2 work.
- `AI-TRACKING.md:432` records product-usage drop as unavailable, blocker stated as
  "`customer_usage` keeps no history to detect a drop against."
- `product-usage-enrichment/prd.md:14` states the original motivation directly: usage is "the
  single most predictive leading indicator of SaaS churn."

---

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| Rolling-window metrics reflect elapsed time | For a customer with no new events, `active_days_30d` decreases across consecutive daily runs; asserted by test |
| `silent_churner` becomes reachable | A previously-active customer who goes quiet classifies as `silent_churner` within one daily cycle; asserted by test |
| Declining customers are identifiable | A customer whose active-days halve over two weeks surfaces a `declining` trend state |
| No false signal during warm-up | With <14 days of snapshot history the state is `insufficient_history`, never `stable` or `declining` |
| Zero impact at usage weight 0 | Health scores for orgs at `health_weight_usage = 0` are byte-identical before/after; characterization-tested |
| The opt-in is actually reachable | An operator can set the usage weight from the UI, and saving weights no longer zeroes usage/CRM |
| **The thresholds are not miscalibrated** | Trend states are not degenerately distributed on a realistic fixture — no single state (especially `declining`/`sharp_decline`) absorbs a dominant share of customers with steady usage. See below |

**Why the last metric exists.** Every other metric above is a test assertion — it proves the
code *runs*, not that it is *right*. Thresholds set too loosely would put most customers in
`declining`, making the signal pure noise, and every other metric would still pass green. The
distribution check is the only one that can fail for the right reason. It is a sanity bound, not
an accuracy claim: on a fixture of customers with flat usage, the overwhelming majority must
read `stable`.

Deliberately **not** promised: a churn-accuracy lift number. Consistent with
`product-usage-enrichment/prd.md:37` ("we do not promise a churn-accuracy lift number") and the
honest-OSS brand. Whether usage decline improves churn prediction is measurable only once
labels accumulate, and this PRD does not claim it.

---

## Users & Scenarios

**Primary persona: the self-hosting CS/ops operator** running Rereflect on their own infra,
feeding product-usage events via `POST /api/v1/webhooks/usage`.

- *Scenario A — the sliding account.* A customer's engagement halves over two weeks while they
  still log in weekly. Today: nothing changes; health stays flat. After: the usage component
  reflects the decline and the profile shows a `declining` trend, early enough to act.
- *Scenario B — the corrected score.* An operator who opted into usage weighting has been
  seeing inflated scores for quiet customers. After upgrade those scores drop to the truth.
- *Scenario C — turning it on.* An operator wants to weight usage. Today this is impossible
  from the UI. After: it is a field on the existing weights editor.

---

## Requirements

### Must-have

**M1 — Re-derive rolling windows daily (D1).** `recompute_usage_scores` must re-derive
`active_days_7d/30d`, `login_count_7d/30d` (and the new `active_days_14d`) against the current
time, not just recompute `usage_score` from frozen fields. Idempotent; safe to run repeatedly.

**M2 — Durable daily usage snapshot.** New `customer_usage_history` table, one row per
`(organization_id, customer_email, snapshot_date)`, written by the existing 04:00 UTC scan
which already visits every rollup row. Mirrors the `customer_health_history` precedent. Bounded
retention (default 180 days) with a prune task — this feature must not repeat D2.

**M3 — Relative-decline trend detection.** Compare the customer's current `active_days_14d`
against their own value from ~14 days ago in the snapshot table. Emit:
- `usage_trend_state` ∈ `insufficient_history` | `stable` | `declining` | `sharp_decline`
- `usage_trend_pct` (signed relative change, null when state is `insufficient_history`)

Comparison is always **against the customer's own past**, never a cross-customer or org
baseline (that conflates "low" with "declining").

**The lookback must not assume contiguous snapshots.** The worker can miss a day (downtime,
deploy, an org installed mid-week), so there may be no snapshot exactly 14 days back. The
comparison selects the **nearest snapshot within a tolerance band** (target 14 days, accepted
range 12–16). If no snapshot falls in the band, the state is `insufficient_history` — never a
silent comparison against the wrong period. `snapshot_date` is **UTC**, consistent with the
`datetime.utcnow()` used throughout the usage pipeline.

**M4 — Cold-start and small-number guards.** State is `insufficient_history` unless *both*: a
snapshot ≥14 days old exists, **and** the prior-period baseline clears a minimum activity floor
(a customer going from 2 active days to 1 must not read as a 50% collapse). The API and UI must
expose this state explicitly so a warming-up install is visibly warming up, not silently broken.

**M5 — Trend feeds the health score, and nothing else.** The trend applies a **bounded penalty
to the usage component only**. `churn_risk_component`, `churn_probability`, the calibration
model, and `time_to_churn_bucket` are **not touched** — see Technical Considerations.

**M6 — Usage weight editable (minimal D4).** Extend `HealthWeightsEditor` to a fifth `usage`
field and include it in the `updateHealthWeights` payload. This also fixes the silent
zeroing of `usage` and `crm` on every UI save.

**M7 — Byte-stability at weight 0.** Orgs with `health_weight_usage = 0` (the default, i.e.
every org that has not opted in) must see byte-identical health scores. Characterization-tested.

### Should-have

- **S1** — Trend surfaced on the Customer 360 Usage Activity card, including the
  `insufficient_history` state.
- **S2** — `usage_trend_state` / `usage_trend_pct` on the customer profile API response.
- **S3** — Operator documentation in `docs/SELF_HOSTING.md`: what the trend means, the ~14-day
  warm-up, and how to enable usage weighting.

### Nice-to-have (explicit v2)

- **N1** — `usage_trend_change` customer-timeline event.
- **N2** — A `usage_trend` automation trigger composing with churn-playbook auto-run (M4.1.5).
  This is the natural follow-on that reconnects the signal to the action loop.
- **N3** — Seasonality/holiday dampening.
- **N4** — Per-org configurable decline thresholds.

---

## Technical Considerations

**Services touched:** `backend-api` (model, migration, health service, profile API, weights
route already supports 6 keys), `worker-service` (daily task, snapshot write, prune),
`frontend-web` (usage card, weights editor). `analysis-engine` unaffected.

### The calibration trap — why health-score-only

`churn_probability` is **not** derived from the health score. `probability_updater.update`
computes it from `health.churn_risk_component` **alone**
(`worker-service/src/services/probability_updater.py:75`), then applies the org's fitted
isotonic calibration model plus a bootstrap CI.

`churn_risk_component` is the inverted average of feedback-level `churn_risk_score`
(`health_score_service.py:190`) — purely feedback-derived. Folding usage into it would
**silently invalidate every org's calibration model**, which was fitted against the
feedback-only score distribution. No error would surface; the probabilities would simply become
wrong. Any such change requires an explicit refit/versioning story and is out of scope here.

Related, and worth recording: `_should_skip` skips recomputation when `churn_risk_component`
moved <2 points versus the last history snapshot (`probability_updater.py:118-141`). A customer
with no new feedback has an unchanged component, so their probability is frozen regardless of
this feature. Same structural theme; not addressed here.

### Multi-tenancy

Every new row carries `organization_id`. Keyed `(organization_id, customer_email)` — identical
to `customer_usage` and `customer_health_scores`. Email is namespaced per org; no global email
namespace, no cross-tenant read path.

### Duplicated service modules

`usage_score_service.py` and `segment_service.py` exist as **duplicated copies** in both
`backend-api` and `worker-service`, with an explicit "keep in sync" header comment
(`worker-service/src/services/usage_score_service.py:1-2`). Any change to scoring logic must be
applied to both copies, and tests must cover both. This is a known trap, not a discovery to be
made mid-implementation.

### Data Model (indicative — finalised in tech-plan)

`customer_usage_history`:
`id`, `organization_id` (FK, CASCADE, indexed), `customer_email` (indexed), `snapshot_date`
(date), `active_days_7d`, `active_days_14d`, `active_days_30d`, `login_count_30d`,
`distinct_feature_count`, `usage_score`, `last_active_at`, `created_at`.
Unique `(organization_id, customer_email, snapshot_date)`; index
`(organization_id, customer_email, snapshot_date DESC)` for the lookback query.

`customer_usage` gains `active_days_14d`, plus `usage_trend_state` and `usage_trend_pct`.

**Initial values on migration.** `active_days_14d` is added nullable and starts NULL on every
existing row; it is populated by the first M1 daily re-derivation (or that customer's next
event, whichever comes first). `usage_trend_state` defaults to `insufficient_history`. This
means the trend is inert until the first daily run *and* a snapshot enters the 12–16 day
lookback band — consistent with the cold-start guard, not an additional failure mode. No data
backfill is required for correctness.

**Double-counting.** A declining customer is already penalised once through the decaying
recency term (weight 0.50). The trend penalty is a *second* deduction on the same underlying
behaviour, so its bound must be chosen with that overlap in mind — the combined effect must not
drive an otherwise-healthy customer to a near-zero usage component on a single moderate
decline. The penalty ceiling is set in tech-plan with this interaction stated explicitly.

**Migration note:** alembic in this repo is **single-head**; run a live `alembic heads` before
authoring (static parsing has repeatedly produced a false "multiple heads" reading).

### Non-functional

- The daily task already scans every rollup row; the snapshot write must not turn that into an
  N+1. Batch the insert.
- Snapshot growth is bounded by the prune task. At 10k customers × 180 days ≈ 1.8M rows —
  acceptable, and explicitly bounded unlike `usage_event`.

---

## Risks & Open Questions

| Risk | Mitigation |
|---|---|
| **Feature appears dead after install** — no backfill means no signal until ~14 days of snapshots exist | 14-day window (not 30) + explicit `insufficient_history` state surfaced in UI and API + documented warm-up |
| **Seasonality false positives** — holidays/vacation read as decline | Minimum-baseline floor (M4) suppresses small-number noise; full seasonality handling deferred to N3 and stated as a known limitation |
| **Health scores change on upgrade** for orgs that opted into usage | Deliberate correction, documented (below). Weight-0 orgs unaffected and characterization-tested |
| **Sync drift between duplicated service copies** | Change both copies; test both. Called out above |
| **Snapshot table becomes the next `usage_event`** | Prune task ships *with* the table, not after |

### Known debt explicitly NOT fixed here

Recorded so it is visible rather than forgotten:

- **D2** — `usage_event` has no retention despite the documented "rolling 90 days"
  (`product-usage-enrichment/prd.md:91`), and `_do_process_usage_event` re-reads the customer's
  entire event history on every event (`usage_metrics.py:202-206`), i.e. O(lifetime) per event
  against an unbounded table.
- **D3** — A failed Celery enqueue is swallowed while the event is still counted `accepted`
  (`api/routes/usage_webhooks.py:172-180`); no path ever re-scans for un-rolled-up rows, so a
  Redis blip permanently drops events from the rollup.

Both warrant their own branch.

### Open questions for tech-plan

1. Exact decline thresholds for `declining` vs `sharp_decline`, and the minimum-baseline floor
   value. Should be named constants in the `usage_score_service` style (no magic numbers).
2. Penalty shape: linear in decline %, or banded like the existing components? Banded matches
   house style; linear is smoother. Bounded either way.
3. Whether `active_days_14d` is added to the rollup table or derived on read.

---

## Out of Scope

- Touching `churn_risk_component`, `churn_probability`, the calibration model, or
  `time_to_churn_bucket` (calibration trap).
- The per-feedback 9-factor scorer — structurally cannot serve this case; a silent customer
  produces no feedback to score.
- D2 and D3 (above).
- Retroactive backfill of snapshots from `usage_event`.
- Automation triggers and timeline events for the trend (N1/N2).
- Cross-customer or industry baselines — dead single-tenant, same reason M4.3 benchmarks were
  dropped (`AI-TRACKING.md:320-321`).
- Any plan-tier gating. Rereflect is MIT/self-hosted with all features unlocked; `CLAUDE.md`'s
  billing sections are stale pre-pivot.

---

## Rollout & adoption

This is a self-hosted product with no telemetry back to us, so "adoption" means: does an
operator who upgrades end up with the feature on and understood? Three concrete obligations:

1. **Discovery of the score change.** Operators at a non-zero usage weight will see health
   scores move after upgrade with no in-product explanation. The CHANGELOG entry and the
   `SELF_HOSTING.md` section must both state the cause plainly, and the release note is the
   primary vehicle — there is no in-app migration notice in scope (emitting one is N1).
2. **Discovery of the feature itself.** Usage weighting defaults to 0, so for most operators
   this ships dormant. The weights editor gaining a fifth field (M6) is the only in-product
   surface that makes it discoverable at all; that is the adoption mechanism, and it is why M6
   is a must-have rather than polish.
3. **Warm-up legibility.** The `insufficient_history` state must be visible in the UI, not just
   the API, so a freshly-installed operator sees "warming up" instead of an empty card that
   looks broken.

**No post-launch usage measurement is possible or planned.** Single-tenant self-hosting means
we cannot observe whether anyone enables the weight. This is a genuine limitation of the
feature's feedback loop, not an oversight — the same constraint that killed M4.3 benchmarks
(`AI-TRACKING.md:320-321`).

## Evidence quality — an honest caveat

The problem statement is grounded in **verified code defects** (D1 reproduced and cited) and in
**the repo's own roadmap** (`product-usage-enrichment/prd.md:67`, `AI-TRACKING.md:432`). It is
**not** grounded in operator research: no user has reported this, and the personas in
"Users & Scenarios" are reasoned constructs, not interviews. The strongest claim this PRD can
honestly make is that the current behaviour is *demonstrably wrong* (frozen windows, unreachable
`silent_churner`), not that operators are *demonstrably asking* for trend detection.

## Deliberate break of the M3.2 byte-stability guarantee

M3.2 shipped with `health_weight_usage` defaulting to 0 specifically so existing scores were
"byte-for-byte unchanged" (`AI-TRACKING.md:207`, `product-usage-enrichment/prd.md:32`).

This feature **preserves that guarantee for every org at weight 0** — which is every org that
has not opted in, and is characterization-tested (M7).

For orgs that **have** opted into usage weighting, health scores **will change on upgrade**,
generally downward for customers whose engagement has fallen. This is a **correction, not a
regression**: those scores were computed from frozen frequency fields and were overstated. The
CHANGELOG and release note must say exactly that, in the same honest register as the M5.1
sentiment-model disclosure, which shipped a model that only marginally beat its baseline and
said so plainly (`AI-TRACKING.md:364-367`).

---

## Proposed Aspect Decomposition

| Aspect | Boundary |
|---|---|
| `rollup-rewindow-fix` | D1: re-derive rolling windows in the daily task; fix the misleading test fixture; characterize weight-0 stability |
| `usage-history-snapshot` | `customer_usage_history` model + migration + daily batch write + prune task |
| `trend-detection-and-health` | Trend state/pct computation, guards, bounded usage-component penalty, profile API fields |
| `frontend-trend-and-weights` | Trend + `insufficient_history` display on the Usage card; 5th usage weight field and payload (D4) |

Sequencing: `rollup-rewindow-fix` → `usage-history-snapshot` → `trend-detection-and-health` →
`frontend-trend-and-weights`. The first two are independently valuable and independently
testable; `frontend-trend-and-weights` depends only on the API surface from the third.
