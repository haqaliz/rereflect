# Understanding — usage-decline-churn-labels (Phase 2 dig)

**Date:** 2026-07-23
**Branch:** `feat/usage-decline-churn-labels`
**Method:** 2 read-only agents (suggestion-queue pipeline; usage-history/trend stack) + direct reads of
`docs/planning/crm-churn-labels/prd.md` and a live environment check.
**Environment verified:** venv rebuilt on **Python 3.12** (system `python3` is 3.9.6 and cannot install
`Authlib==1.7.2`); `alembic heads` run **live** → **single head `a1c2d3e4f5a6`**; baseline
`pytest` over the 6 affected suites → **95 passed**.

---

## What this feature really is

Not a new idea — the **unblocking of a written-down deferral**. `crm-churn-labels`' own
Out of Scope section says:

> **Usage/Segment-derived churn labels.** Blocked: `customer_usage` keeps only current 7d/30d
> counters with no history (`customer-360-unified-timeline` R1, "we will not fabricate a drop
> event").

M3.2b (`usage-trend-churn-signal`, 2026-07-22) added the durable `customer_usage_history` snapshot.
`AI-TRACKING.md:480-485` records the blocker as resolved and the work as "feasible but **unplanned**
… it would need a confirm-in-review step like `crm-churn-labels`, not auto-labelling."

**Why it matters:** the shipped CRM label source produces **nothing** for a self-hoster with no
HubSpot/Salesforce — the default OSS deployment. This is the only label supply that works CRM-free.

---

## Finding 1 — The backend genuinely needs no migration and no route changes

- `models/churn_label_suggestion.py:47` — `provider` is `String(50)`, **no CHECK, no enum, no DB
  whitelist**. Enum values are Python-list-validated by house convention, and `provider` isn't even
  in such a list.
- `routes/churn_suggestions.py` — `provider` appears in exactly 3 places, all opaque string
  handling: list filter (`:262-263`), bulk cohort filter (`:219-220`), response passthrough. Only
  `status` is validated (`:251-255`). **Zero changes needed.**
- The natural key `UniqueConstraint(organization_id, provider, external_opportunity_id)` (`:84-101`)
  gives idempotent re-detection for free — a new provider just needs a **stable synthesized id**.

## Finding 2 — Confirm is provider-blind, so labels are trainable on identical footing

`_confirm_one` (`routes/churn_suggestions.py:70-127`) always writes
`CustomerChurnEvent(source="manual", marked_by_user_id=<confirming user>)` — **`provider` is never
propagated into the churn event**. Since `ai_readiness.py:91-99` excludes only
`source == "auto_suggested"` from `trainable`, a confirmed usage-decline label counts exactly like a
confirmed CRM one. And `_pending_suggestion_count` (`:160-178`) has **no provider filter**, so
`pending_suggestions` picks up the new provider automatically while staying out of
`churn_labels_ready` (`:244`). The readiness-honesty requirement is satisfied by construction.

## Finding 3 — The opt-in home is the one real collision with "no migration"

Default-deny today lives on the CRM integration rows themselves:
`HubSpotIntegration.churn_labels_enabled` + `churn_label_config` (`models/hubspot_integration.py:47-48`)
and the Salesforce twin (`:49-50`), mirrored in `worker-service/src/models/__init__.py:1133-1134,1187-1188`.

**There is no non-CRM row to hang a flag off.** The nearest org-level home is `OrgAIConfig`
(`models/org_ai_config.py`), which already carries `health_weight_usage` and the classifier-mode
columns — but adding a column there is a migration. This is a genuine fork, not a detail:
**default-deny is non-negotiable (it is the house pattern and the safety property), so if honoring it
costs a migration, the migration wins over the "no migration" aspiration.**

## Finding 4 — `crm_churn_label_options.py` is a fence, not a tool

`CHURN_LABEL_CONFIG_KEYS` (`:43-46`) is hardwired to exactly hubspot/salesforce;
`_validate_churn_label_config:244` would `KeyError` on a third key, and `fetch_renewal_options:64-65`
returns `("options_fetch_failed")` for anything else. **Never route this provider through
`/integrations/{provider}/churn-labels`.** Write it into the PRD as an explicit out-of-scope fence.

## Finding 5 — Correction: where the trend logic actually lives

The card/handoff said "reusing `usage_trend_severity.py`". **Imprecise.** That module
(`services/backend-api/src/services/usage_trend_severity.py`, byte-identical worker duplicate) is
*only* `TREND_SEVERITY = {stable:0, declining:1, sharp_decline:2}` + `is_worsening_transition` —
`insufficient_history` is deliberately absent so every transition touching it returns `False`.

The **classification** lives in `usage_score_service.py:203-366` (byte-identical worker duplicate):
- `select_nearest_in_band_snapshot` (`:245-285`) — baseline from history rows aged
  `[12, 16]` days, nearest to 14, ties → older. Never widens the band.
- `classify_usage_trend` (`:288-331`) — `pct <= -60` → `sharp_decline`; `pct <= -30` → `declining`;
  else `stable`. Returns `("insufficient_history", None)` when there's no in-band baseline, or when
  **`baseline_active_days_14d < 5`** (the floor).
- `apply_trend_penalty` (`:334-366`) — `-8` / `-15` on the **health usage component only**.

## Finding 6 — Edge-triggered vs. sustained: the central design fork

The post-commit drain seam M3.2c added (`worker-service/src/tasks/usage_metrics.py:659-681`) is
**edge-triggered**: `pending_trend_transitions` is appended to **only on a genuine state change**
(`:635-638`). It is exception-isolated per transition and fires strictly after `db.commit()` — an
excellent seam, and the closest precedent is
`worker-service/src/services/automation_usage_trend_trigger.py` (332 lines, `TRIGGERED_BY =
"auto_usage_trend"`).

**But "sustained decline" is a level-based concept, and the seam cannot express it.** A customer who
enters `sharp_decline` and stays there produces exactly **one** transition, on day one — which is the
*least* evidence-backed moment. A detector wanting "declining held for N consecutive days" must read
`usage_trend_state` per scanned row each day, independent of the transitions list. This is the single
biggest open design question and it is **not** resolvable from the files.

## Finding 7 — Hard scope fence (executable, not just convention)

`tests/test_usage_trend_churn_boundary.py` (216 lines) asserts a `stable → sharp_decline` transition
with zero new feedback leaves `churn_risk_component`, `churn_probability`,
`churn_probability_low/high`, `calibration_model_id`, `time_to_churn_bucket` **byte-for-byte
unchanged**, while proving non-vacuity (the usage component *does* drop by exactly 15). M3.2b and
M3.2c both kept it green and unmodified. **This branch must too.**
Confirmed by grep: `usage_score_service.py` has **zero** matches for
`churn_probability|churn_risk_component|isotonic|calibrat`.

## Finding 8 — Plan gating is inert, correctly

`routes/churn_suggestions.py:51-58` carries a router-level
`require_feature("advanced_churn_prediction")`. This is **not** a live plan gate:
`plans.py:329-330` — `has_feature` returns `True` unconditionally in self-hosted mode. Inheriting it
is consistent with the OSS pivot. Do not add a new gate; do not remove this one.

## Finding 9 — Frontend is cosmetic-only, plus one contained type edit

- **Needs editing:** `lib/api/churn-suggestions.ts:8` —
  `ChurnSuggestionProvider = 'hubspot' | 'salesforce'`. TS-only, not runtime-validated, so a new
  provider *renders* fine; but filtering by it type-safely requires widening the union.
- **Renders fine, reads wrong (cosmetic):** page header "CRM churn suggestions" + subtitle
  (`customers/churn-suggestions/page.tsx:127-132`); the `provider` badge is plain text (`:198-207`,
  no provider-keyed icon/link, so no break); `EvidenceCell` (`:27-47`) reads CRM-shaped keys
  (`deal_name`/`amount`/`stage`) and falls back to *"No CRM detail captured"*; the
  `ConfirmSuggestionDialog.tsx:88` field is hardcoded-labeled **"CRM close date"**.
- The `/customers` pending-count StatCard (`customers/page.tsx:219-220`) is provider-agnostic and
  picks the new provider up for free.

## Finding 10 — Reusable pure core, with a caveat

`worker-service/src/services/churn_harvest_core.py:decide_suggestion` (`:24-52`) is generic by
signature (`is_closed, is_won, discriminator, renewal_set, customer_email, known_emails`) and
deny-ordered. `_process_raw_record` (`churn_suggestion_harvester.py:82-161`) takes `adapt` as an
**injected callable**, so a new adapter slots in **without editing shared code**; only
`_fetch_raw_candidates` (`:39-45`) and the `_ADAPTERS` dict (`:33-36`) are hardwired, and a
usage-decline path simply wouldn't call them. Dedup + `begin_nested()`/`IntegrityError` race backstop
(`:142-161`) are reusable verbatim.

**Caveat:** `test_churn_harvest_core.py` has a `TestPurityGuard` asserting no
Celery/SQLAlchemy/FastAPI/httpx/CRM imports. Any reuse must preserve that. And bending
`is_closed=True, is_won=False, discriminator=<trend state>` onto a usage signal may be forcing a
CRM-shaped abstraction onto a non-CRM one — worth deciding deliberately rather than by default.

---

## Contradictions / corrections to the brief

1. **`usage_trend_severity.py` is not the classifier** (Finding 5). The brief named the wrong module.
2. **"No migration" may be unattainable** without abandoning default-deny (Finding 3). The brief
   framed no-migration as the target; the dig says default-deny is worth more.
3. **The M3.2c seam does not give "sustained"** (Finding 6). The brief assumed the trend stack would
   supply the signal directly; it supplies *edges*, and sustained-ness must be built.

## Open questions for the interview

1. **Detection rule** — edge on entering `sharp_decline`, or level-based "held N consecutive days"?
   (Finding 6. Materially changes where the detector hangs and what it reads.)
2. **Opt-in home** — new `OrgAIConfig` column (migration, honors default-deny) vs. always-on?
   (Finding 3.)
3. **`suggested_churned_at` semantics** — decline start, last active day, or detection date? The CRM
   source uses the *close date* explicitly because stability makes re-harvest idempotent; the
   usage analogue needs the same stability property.
4. **Synthetic `external_opportunity_id`** — determines whether a customer who declines, is
   rejected, recovers, and declines again months later can ever produce a second suggestion.
5. **`evidence` payload** — what does a reviewer need to adjudicate honestly (usage series? pct?
   baseline? last active day? recent feedback)? Note the frontend renders CRM keys or falls back.
6. **Reuse `decide_suggestion` or write a parallel core?** (Finding 10 caveat.)
7. **Distinguishable provenance for M5.3 backtests** — should confirmed usage-sourced labels be
   separable from CRM-sourced ones later? (`churn_event_id` back-link exists; `source` is `manual`
   for both.)

## Honest limits to carry into the PRD (unchanged by the dig, now precisely located)

- **A usage decline is not churn.** The review queue is the entire safety mechanism.
- **≥5 active-day baseline floor** (`usage_score_service.py:288-331`) permanently excludes
  light-usage customers — arguably the likeliest churners. Structural, inherited, must be stated.
- **~12-16 day warm-up** minimum before any decline can be classified (band is `[12,16]` days).
- **180-day retention** (`usage_metrics.py:46`, weekly `purge_old_usage_history`) — ample vs. the
  16-day lookback, but caps longer-window analysis.
- **Unvalidated upstream dependency**: requires the operator to have instrumented usage events.
- **No claim about churn-prediction quality.** This changes label *supply* only.
- **The 500-label gate is under review** (`AI-TRACKING.md:467-478`); do not restate it as settled and
  do not justify this feature by "it gets you to 500".
