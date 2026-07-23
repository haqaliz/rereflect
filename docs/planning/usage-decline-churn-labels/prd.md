# PRD — Usage-Decline Churn Labels (sustained-decline suggestions + operator review)

**Slug:** `usage-decline-churn-labels`
**Branch:** `feat/usage-decline-churn-labels`
**Type:** feat (freeform — no GitHub issue)
**Status:** Draft (pre-review-gate)
**Author:** `rereflect-begin-fast` pipeline, 2026-07-23
**Sources:** `docs/planning/_card/card.md` (brief), `docs/planning/_card/understanding.md` (2-agent
dig), `docs/planning/crm-churn-labels/prd.md` (the pattern this extends), `AI-TRACKING.md` M3.2b /
M3.2c / M5.3

---

## Problem Statement

M5.3 — the upgrade from a calibrated churn *heuristic* to a real per-org churn model — is the one
open Track in the roadmap (`AI-TRACKING.md:446`), and it is gated **entirely on label supply**, not
on code.

`crm-churn-labels` (shipped 2026-07-15) attacked that gate by harvesting lost renewals from HubSpot
and Salesforce into an operator-reviewed queue. It works. **But it produces literally nothing for a
self-hoster with no CRM connected** — which is the default open-source deployment. Rereflect is MIT,
single-tenant, BYOK; assuming a Salesforce org is exactly the hosted-SaaS assumption the pivot
removed. For those operators the label count stays at whatever they hand-typed, and M5.3 stays
permanently out of reach.

That same PRD named the alternative and explicitly ruled it out at the time:

> **Usage/Segment-derived churn labels.** Blocked: `customer_usage` keeps only current 7d/30d
> counters with no history (`customer-360-unified-timeline` R1, "we will not fabricate a drop
> event").
> — `docs/planning/crm-churn-labels/prd.md`, Out of Scope

**That blocker is gone.** M3.2b (`usage-trend-churn-signal`, 2026-07-22) added the durable
`customer_usage_history` daily snapshot and a real decline classifier. `AI-TRACKING.md:480-485`
records the change and the remaining condition:

> **Update 2026-07-22:** the no-history blocker is resolved … using a sustained usage decline as a
> churn-label *source* is now feasible but remains **unplanned** (it would need a confirm-in-review
> step like `crm-churn-labels`, not auto-labelling).

**This PRD is that confirm-in-review step.** It is the unblocking of a written-down deferral, not a
new idea.

**Who feels it.** The self-host operator with product telemetry but no CRM — the modal OSS user.
Today they have exactly one label producer: typing into the "Mark as churned" dialog one customer at
a time (`routes/churn_events.py:357`).

**Evidence it's real (file:line):**
- The deferral is written down and now unblocked: `AI-TRACKING.md:480-485`.
- M5.3 is label-gated: `AI-TRACKING.md:446-451`.
- The CRM source is structurally CRM-only: opt-in lives on
  `models/hubspot_integration.py:47-48` / `models/salesforce_integration.py:49-50` — an org with
  neither integration row has no way to enable anything.
- The signal now exists and is durable: `models/customer_usage_history.py:39-97`,
  `services/usage_score_service.py:203-366`.

---

## Goals & Success Metrics

**Goal.** Give a CRM-free operator a *second* churn-label producer that is honest enough to trust —
without lowering label quality. Every label that reaches the calibrator is still human-confirmed.

> **The design constraint is precision, not volume.** `crm-churn-labels` could target ≥0.8 precision
> because a lost renewal is strong evidence. **A sustained usage decline is weaker evidence.** The
> realistic failure mode is not a bug — it is a queue that fills with seasonal dips, holidays, and
> one power user going on leave, until the operator stops opening the page. Every design decision
> below resolves toward *fewer, better* suggestions.

| Metric | Target | Measured by |
|---|---|---|
| Suggestion precision (confirmed ÷ reviewed) | ≥ 0.6 on an enabled org | `churn_label_suggestions.status` counts, `provider='usage_decline'` |
| False labels reaching the calibrator | **0 by construction** | pending suggestions never enter `customer_churn_events` |
| Readiness honesty | `churn_labels_ready` unchanged by pending suggestions | `routes/ai_readiness.py:244` |
| Blast radius on the churn stack | **zero, provably** | `test_usage_trend_churn_boundary.py` green *and unmodified* |

**Why 0.6 and not 0.8.** Stating the CRM target for a weaker signal would be dishonest. 0.6 is a
hypothesis, not a measurement — **nobody has run this detector against real data**, and with no
telemetry in a self-hosted product we may never see an aggregate number. It is written down so the
first enabled org can falsify it.

**Non-metrics.** We do **not** claim improved churn accuracy, AUC, or that any org reaches the M5.3
gate. This PRD produces *labels*; whether more labels improve the model is M5.3's question. See R6
on the gate itself.

---

## User Personas & Scenarios

> **Evidence tag: `assumed`.** Rereflect is self-hosted OSS with no telemetry. We cannot verify that
> any org has instrumented usage events, let alone enough history. `AI-TRACKING.md:262` already flags
> operator usage-instrumentation as **unvalidated**. These personas are hypothesized from the ICP.

- **Self-host operator with telemetry, no CRM.** Has been posting to `POST /api/v1/webhooks/usage`
  for a month. Opens Settings → AI, enables "Suggest churn labels from sustained usage decline".
  A week later: 6 pending suggestions. Each shows a 14-day active-day series falling from 11 days to
  2, held for 7 consecutive days, last seen 3 weeks ago. Confirms 4, rejects 2 (one was a known
  seasonal customer). Four real labels, zero typing.
- **Operator who enables it and gets nothing.** Their customers are all light-usage — under the ≥5
  active-day baseline floor. They see an explicit empty state that **says why**, rather than
  concluding the feature is broken.
- **Org that never enables it.** Sees nothing. No suggestions, no new UI surface, no behaviour
  change. Default off.

---

## Requirements

### Must-have

**M1 — Sustained-decline detector (level-based, not edge-based).**
A customer qualifies **only** when `usage_trend_state == "sharp_decline"` (≥60% drop in
`active_days_14d` vs. the 12-16-day-old baseline) has held for **N consecutive daily snapshots**,
default `N = 7`.
- **The milder `declining` state (≥30%) does not qualify in v1.** Deliberate precision choice.
- `insufficient_history` **never** qualifies and never breaks a streak by counting as decline — it
  is an explicit non-signal, matching how `usage_trend_severity.py` deliberately omits it from
  `TREND_SEVERITY`.
- **This cannot reuse M3.2c's post-commit drain seam.** That seam is edge-triggered — it appends to
  `pending_trend_transitions` only on a state *change* (`worker-service/src/tasks/usage_metrics.py:635-638`),
  so a customer who enters `sharp_decline` and stays there produces exactly one event, on day 1,
  which is the moment of *least* evidence. The detector must instead read the daily
  `customer_usage_history` rows and compute streak length. Streak is derived from history rows, not
  stored, so no new columns on the history table.

**M2 — Per-org opt-in, default-deny, with a shadow mode.**
New columns on `OrgAIConfig` (`models/org_ai_config.py`, which already carries `health_weight_usage`
and the three `*_classifier_mode` columns — the established home for per-org AI knobs):
- `usage_churn_labels_mode` — String(20), `server_default='off'`: **`off` | `shadow` | `active`**,
  mirroring the shipped `*_classifier_mode` columns and `AutomationRule.mode`.
  **`shadow` evaluates and records what it *would* suggest without writing a
  `ChurnLabelSuggestion`** — the operator can see the volume and the evidence before arming it.
  M3.2c made shadow the default for exactly this "we don't know if it'll be noisy yet" reason
  (`AI-TRACKING.md:254-256`); the same reasoning applies with more force to a weaker signal.
  A three-state column also costs no more than the boolean it replaces.
- `usage_churn_label_config` — JSON, nullable: `{"sustain_days": 7}`.
- Default is **`off`**, not `shadow`: unlike M3.2c this writes into a queue an operator must trust,
  and silently accumulating shadow rows for every org is not default-deny.
- One Alembic migration. **Chain off whatever `alembic heads` returns at write time** — it is
  `a1c2d3e4f5a6` today (verified live, single head), but re-run the tool; do not grep the files.
  *(House lesson: the `crm-churn-labels` PRD had to publish a correction for a fabricated two-head
  fork produced by exactly that static-parse shortcut.)*
- `off` org → detector returns immediately, writes nothing, costs nothing.

**M3 — Suggestion write path (no new table, no route changes).**
Write `ChurnLabelSuggestion` rows with:
- `provider = "usage_decline"` — the column is an unconstrained `String(50)` with no CHECK/enum
  (`models/churn_label_suggestion.py:47`), so **no migration on this table**.
- `external_opportunity_id = "usage:{customer_email}:{streak_start_date}"` — stable while a streak
  continues (⇒ idempotent re-detection via the existing
  `UniqueConstraint(organization_id, provider, external_opportunity_id)`), and **a genuinely new
  decline episode after a recovery mints a new key**, so a rejected suggestion is never re-suggested
  while a real second episode still can be.
- `suggested_churned_at = customer_usage.last_active_at` — the last day they actually showed up.
  Semantically honest and the most useful timestamp for a future M5.3 backtest.
  *Nuance to document:* `last_active_at` can drift after insert (a single login need not break a
  14-day-window streak), but the row is written once and never updated, so the stored value is
  stable. We do not chase it.
- **`last_active_at IS NULL` → no suggestion.** The column is nullable
  (`models/customer_usage.py:48`), and without it there is no defensible churn date. Deny rather
  than substitute a fallback date — a wrong label date is worse than no label.
- Reuse verbatim: the `_existing_suggestion_row` pre-check, the `_has_active_churn_event`
  suppression, and the `begin_nested()` + `IntegrityError` → `skipped_existing` race backstop
  (`worker-service/src/services/churn_suggestion_harvester.py:48-79,142-161`).
- Per-run cap with a **logged, surfaced count of anything dropped** (house rule: no silent caps).

**M3b — Population-level sanity guard (added by self-critique — non-negotiable).**
A usage decline is only meaningful if it is *specific to that customer*. If the operator's usage
pipeline breaks — webhook misconfigured, events dropped by a deploy, API key rotated — then **every**
customer's `active_days_14d` collapses simultaneously, and ~12 days later the entire customer base
crosses into `sharp_decline` and holds it (the pipeline is still broken). The 7-day sustain window
does not protect against this; it *confirms the artifact*.

- Before writing any suggestions for an org on a given run, compute the share of that org's
  trend-eligible customers that qualify. If it exceeds `MAX_QUALIFYING_SHARE` (default **0.25**),
  **suppress the entire run for that org**, write nothing, and record a surfaced warning
  ("possible usage-instrumentation outage — N of M customers declined simultaneously").
- Also suppress when the org's total ingested `usage_event` volume for the period is zero while
  customers exist — an unambiguous outage signature rather than a behavioural one.
- The suppression must be **visible, not silent** (house rule: no silent caps). The operator needs
  to see that the detector deliberately declined to act, and why.

**M4 — Evidence a human can actually adjudicate.**
This is the precision mechanism, not a nice-to-have — the operator is the only thing standing
between a seasonal dip and a poisoned training set. `evidence` JSON carries:
`{trend_state, trend_pct, baseline_active_days_14d, current_active_days_14d, streak_days,
streak_start_date, last_active_at, snapshot_series: [{date, active_days_14d}]}`.
- The frontend `EvidenceCell` reads CRM-shaped keys (`deal_name`/`amount`/`stage`) and otherwise
  falls back to *"No CRM detail captured"* (`customers/churn-suggestions/page.tsx:27-47`). Add a
  **provider-aware branch** rendering the decline summary. Do **not** smuggle usage data into
  `deal_name` to exploit the existing renderer.

**M5 — Detector placement + isolation.**
Runs off the daily `recompute_usage_scores` pass (`worker-service/src/tasks/usage_metrics.py:492-713`),
**strictly after** its commits, in its own transaction, with per-customer try/except isolation —
mirroring how M3.2c's drain seam (`:659-681`) was made unable to fail the parent task.
- **The worker cannot import backend-api code.** Any shared pure logic follows the established
  duplicate-and-parity-test pattern (as `usage_trend_severity.py` and `usage_score_service.py`
  already are, byte-identical in both services).
- New pure core module for the streak decision, with the same `TestPurityGuard` discipline as
  `churn_harvest_core.py` (no Celery/SQLAlchemy/FastAPI/httpx imports).

**M6 — Settings UI + honest empty states.**
A card on Settings → AI: toggle + `sustain_days`. Copy must state the real limits — the ~12-16 day
warm-up, the +N-day sustain window, and that **customers below the ≥5 active-day baseline floor can
never produce a suggestion**. An operator who enables this and sees nothing must be able to learn
why from the UI, not from the source.

**M7 — Docs + tracking (repo convention).**
`docs/SELF_HOSTING.md` (what it does, what it cannot see, how to enable), `CHANGELOG.md`,
`AI-TRACKING.md` (resolve the "unplanned" note at `:480-485`; add the capability row).

### Should-have

- Frontend `ChurnSuggestionProvider` union widened from `'hubspot' | 'salesforce'`
  (`lib/api/churn-suggestions.ts:8`) so the new provider can be filtered type-safely. TS-only, no
  runtime effect.
- De-CRM-ify the shared queue copy: header "CRM churn suggestions", subtitle "CRM-sourced
  closed-lost deals" (`page.tsx:127-132`), and the "CRM close date" field label
  (`ConfirmSuggestionDialog.tsx:88`) are now wrong for half the sources.
- `last_detection_at` / `last_detection_status` surfaced on the settings card, as the status-sync
  cards do — including the M3b suppression state when a run is withheld.
- **A precision read-out on the settings card**: confirmed / rejected / pending counts for
  `provider='usage_decline'`. Without it the ≥0.6 target is unfalsifiable in practice — a
  self-hosted product has no telemetry, so if the *operator* cannot see the ratio, nobody can.
  This is a `GROUP BY status` over a table we already index by `(org, status)`.

### Nice-to-have (explicitly deferrable)

- `declining`-state suggestions behind a separate, more conservative threshold.
- A "seasonality" guard (compare against the same customer's window last year) — needs >180-day
  history, which retention currently forbids.
- Backfill over existing history at enable time. **Not v1**: history only began 2026-07-22, so there
  is nothing meaningful to backfill yet. Revisit once orgs hold months of snapshots.

---

## Technical Considerations

**Rough size.** ~1 week equivalent — materially smaller than `crm-churn-labels` (which needed 2
providers, a new table, an API-paging backfill, and 6 endpoints). Here: **zero new endpoints, zero
new tables, one small migration**, one detector, one settings card, one evidence renderer.

**Services touched.** `services/worker-service` (detector + pure core), `services/backend-api`
(2 `OrgAIConfig` columns + migration + settings read/write on the existing AI settings surface),
`services/frontend-web` (settings card, evidence branch, type widening). `analysis-engine` untouched.

**Why no route changes.** `routes/churn_suggestions.py` treats `provider` as an opaque string in all
three places it appears — list filter (`:262-263`), bulk cohort filter (`:219-220`), response
passthrough. Only `status` is validated (`:251-255`).

**Why labels stay trainable.** `_confirm_one` (`:70-127`) always writes
`CustomerChurnEvent(source="manual", marked_by_user_id=<user>)` — `provider` is never propagated.
`ai_readiness.py:91-99` excludes only `source == "auto_suggested"` from `trainable`, so a confirmed
usage-decline label counts identically to a confirmed CRM one. `_pending_suggestion_count`
(`:160-178`) has no provider filter, so `pending_suggestions` picks the new provider up
automatically and stays out of `churn_labels_ready` (`:244`) **with no code change**.

**M5.3 provenance is already solved.** `ChurnLabelSuggestion.churn_event_id` back-links to the
event, and the suggestion keeps `provider` — CRM-sourced and usage-sourced labels remain separable
by join. No new column, no new `source` value.

**Plan gating.** The suggestions router carries `require_feature("advanced_churn_prediction")`
(`:51-58`). This is inert: `plans.py:329-330` returns `True` unconditionally in self-hosted mode.
Inherit it; do not add a gate, do not remove this one. (`CLAUDE.md`'s billing sections are
pre-pivot and stale.)

**Multi-tenancy.** Every query scoped by `organization_id`; the detector iterates per-org and the
existing review endpoints are already `require_admin_or_owner`.

**Hard scope fence (executable).** `tests/test_usage_trend_churn_boundary.py` asserts a
`stable → sharp_decline` transition leaves `churn_risk_component`, `churn_probability`,
`churn_probability_low/high`, `calibration_model_id`, `time_to_churn_bucket` byte-for-byte
unchanged. M3.2b and M3.2c both kept it green **and unmodified**; so must this branch. Baseline
verified green (95 passed across the 6 affected suites) before any change.

### Data Model

```sql
-- ONLY schema change in this PRD
ALTER TABLE org_ai_configs
  ADD COLUMN usage_churn_labels_mode  VARCHAR(20) DEFAULT 'off',  -- off|shadow|active
  ADD COLUMN usage_churn_label_config JSON        NULL;          -- {"sustain_days": 7}

-- churn_label_suggestions: UNCHANGED. New rows only:
--   provider                = 'usage_decline'
--   external_opportunity_id = 'usage:{email}:{streak_start_date}'
--   suggested_churned_at    = customer_usage.last_active_at
--   evidence                = {trend_state, trend_pct, baseline_active_days_14d,
--                              current_active_days_14d, streak_days, streak_start_date,
--                              last_active_at, snapshot_series:[{date, active_days_14d}]}
```

### API Contracts

**No new endpoints.** The existing surface serves the new provider unchanged:

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/customers/churn-suggestions` | `?provider=usage_decline` already works |
| POST | `/api/v1/customers/churn-suggestions/{id}/confirm` | → `CustomerChurnEvent(source='manual')` |
| POST | `/api/v1/customers/churn-suggestions/{id}/reject` | unchanged |
| POST | `/api/v1/customers/churn-suggestions/bulk` | unchanged |

Only the existing Settings → AI config read/write grows two fields.

---

## Risks & Open Questions

- **R1 — Precision is unproven and may disappoint.** A sustained usage decline is weaker evidence
  than a lost renewal. **Mitigations:** `sharp_decline` only; 7-day sustain; rich evidence; the human
  confirm step; default-deny; an off switch. **Residual risk is real and accepted** — 0.6 is a
  hypothesis, and the first enabled org falsifies or supports it.
- **R2 — The ≥5 active-day baseline floor excludes the likeliest churners.** A customer who was
  never very active cannot produce a suggestion at all
  (`usage_score_service.py:288-331` forces `insufficient_history`). This is **structural and
  inherited from M3.2b**, not introduced here, and it is a genuine blind spot — the quietest accounts
  are plausibly the most churn-prone. **Mitigation: state it in the UI and the docs. Do not fix it
  here** — changing the floor would alter the shipped health-score signal.
- **R3 — Latency is substantial.** ~12-16 day warm-up (baseline band) **plus** 7 sustain days
  **plus** ~24h beat latency. A customer can be gone ~3 weeks before they surface. Acceptable for
  *label collection* (a retrospective task); it would not be acceptable for intervention, and we do
  not claim it for intervention.
- **R4 — Unvalidated upstream dependency.** Requires the operator to have instrumented usage events
  — `AI-TRACKING.md:262` flags this as unvalidated. If nobody instruments usage, this feature is
  inert. **Mitigation:** honest empty state; zero cost when disabled.
- **R4b — The detector only ever sees customers declining *right now*.** A customer who left three
  months ago has no in-band (12-16 day) baseline and is permanently `insufficient_history` — they
  can never be suggested. Combined with R2's floor, the addressable population is "customers who
  were recently active enough to have a ≥5-day baseline **and** are declining within the last
  ~3 weeks". That is a genuinely narrow slice, and it must be stated in the UI copy so an operator
  does not read an empty queue as "no churn".
- **R5 — Streak computation cost.** Reading N days of history per customer per day, across all
  customers. `ix_customer_usage_history_lookback (org, email, snapshot_date)` exists and is sized for
  this; the plan should batch (as `_load_trend_baselines` already does at `:279-338`) rather than
  query per customer.
- **R6 — The 500-label gate may be wrong, and this feature does not fix that.**
  `CHURN_LABEL_TARGET = 500` was copied from a hosted multi-tenant PRD whose "≥5,000 globally" half
  is meaningless single-tenant (`AI-TRACKING.md:467-478`). **Do not justify this feature by "it gets
  you to 500."** Its value is threshold-independent: more human-confirmed labels help under any
  threshold. Re-deriving the gate remains a separate, arguably higher-leverage piece of work.
- **R7 — Two label sources can now collide on one customer.** An org with both CRM and usage sources
  could produce two suggestions for the same person. The existing `_has_active_churn_event`
  suppression and the confirm-time collision handling (`:96-104`, `:115-121`) already resolve this to
  `skipped`/`already_marked` rather than an error — inherited, not new, but should be asserted by a
  test rather than assumed.
- **R8 — The M3b guard has its own failure mode.** A 25% threshold is itself a guess. An org with
  genuinely catastrophic churn (or a very small customer count, where 2 of 6 customers is 33%) would
  be suppressed wrongly. **Mitigation:** the suppression is loud and states the count, so the
  operator can recognize a false suppression; the threshold is configurable. Small-org behaviour
  (apply a minimum-population floor before the ratio test) is an open question for the plan.
- **(resolved) New table?** No — `provider` is an unconstrained string.
- **(resolved) New endpoints?** No — the queue is provider-agnostic.
- **(resolved) Re-suggestion after recovery?** Yes, via a streak-start-keyed id.
- **(resolved) M5.3 provenance?** Already available via `churn_event_id` + `provider`.

---

## Out of Scope

- **Auto-confirming any suggestion.** The review queue is the entire safety mechanism. Never.
- **Routing this provider through `/integrations/{provider}/churn-labels`.**
  `crm_churn_label_options.py`'s `CHURN_LABEL_CONFIG_KEYS` (`:43-46`) is hardwired to two providers
  and `_validate_churn_label_config:244` would `KeyError` on a third. Hard fence.
- **Touching the churn stack** — `churn_risk_component`, `churn_probability`,
  `churn_probability_low/high`, `calibration_model_id`, `time_to_churn_bucket`, isotonic calibration.
- **Changing the trend classifier** — thresholds (-30/-60), the `[12,16]` baseline band, the ≥5
  active-day floor, and `apply_trend_penalty` all stay byte-stable. This PRD *reads* the signal.
- **Changing the 180-day retention** (`usage_metrics.py:46`).
- **`declining`-state suggestions**, seasonality guards, enable-time backfill — named nice-to-haves.
- **Training anything.** This produces labels; M5.3 trains.
- **Re-deriving the 500-label gate** — real work, separate branch (R6).
- **Fixing inherited churn-event route gaps** (no role dependency, inconsistent dedup,
  `RejectRequest.note` accepted but persisted nowhere at `churn_suggestions.py:453-458`). Logged,
  not fixed here.
- **Any claim of improved churn-prediction accuracy.**
