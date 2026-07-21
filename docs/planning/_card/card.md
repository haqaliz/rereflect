# Card — usage-trend-churn-signal (freeform feat, no GitHub issue)

**Type:** feat
**Slug:** usage-trend-churn-signal
**Branch:** `feat/usage-trend-churn-signal`
**Source:** Freeform task selected via `rereflect-next` on 2026-07-21. No GitHub issue.

## Brief (from rereflect-next handoff, verbatim)

> Build product-usage trend/drop detection as a customer-level churn signal. M3.2
> (product-usage-enrichment, shipped 2026-06-29) gave us a usage LEVEL —
> `customer_usage.usage_score` as an opt-in 5th health component at default weight 0 — but
> no history, which `AI-TRACKING.md:432` names as the explicit blocker for usage-drop
> detection, and `docs/planning/product-usage-enrichment/prd.md:67` lists the churn-scorer
> usage factor as explicit v2. Caveat to resolve in the dig: the 9-factor scorer is
> per-feedback-item (`FeedbackItem.churn_risk_factors`), which cannot fire for a silent
> customer — the signal must land on the customer-level `CustomerHealth` recompute path, and
> you must choose between deriving the trend from the rolling 90-day `usage_event` log versus
> adding a durable daily snapshot table mirroring `customer_health_history`. Keep it opt-in
> and byte-stable for orgs with usage weight 0, exactly as M3.2 did. Stretch: expose the drop
> as an automation trigger so it composes with the shipped churn-playbook auto-run (M4.1.5).

## Why this was picked (citations)

- `docs/planning/product-usage-enrichment/prd.md:67` — *Nice-to-have (explicit v2)*: "Add a
  usage factor to the 9-factor churn scorer." Repeated at `:126`.
- `AI-TRACKING.md:432` — lists "Segment/product-usage drop" as **not viable** as an M5.3
  churn-label source, blocker stated verbatim as: "blocked — `customer_usage` keeps no
  history to detect a drop against."
- `AI-TRACKING.md:207-214` — M3.2 Product Usage Enrichment COMPLETE (shipped 2026-06-29);
  usage is an **opt-in 5th health component**, `health_weight_usage` **default 0**, described
  as a "byte-for-byte-stable upgrade".
- `docs/planning/product-usage-enrichment/prd.md:91` — `usage_event` raw log retention is
  "rolling **90 days** (raw); rollup is the durable record."

## Moat rationale

Dead-center of the stated moat: the churn → health → playbook → automation loop is all
shipped and all consumes **customer-level** signals (`CustomerHealth.churn_probability`, the
`churn_probability_threshold` automation trigger at `automation_engine.py:326`, auto-run
playbooks per M4.1.5). A usage-drop input feeds every one of them without new surfaces. Fits
OSS/self-hosted/BYOK — the usage receiver is a plain authenticated POST, not a Segment OAuth
connection (`AI-TRACKING.md:207`).

## Known caveats to resolve in the dig / PRD

1. **Wrong-shape trap.** `FeedbackItem.churn_risk_factors` is per-feedback (aggregated in
   `api/routes/customers.py:1191-1259`). A customer who goes silent files no feedback, so a
   per-feedback factor can *never* fire for the exact case this feature exists to catch. The
   signal must attach to the customer-level recompute path.
2. **Storage choice is open.** Derive the trend from the rolling 90-day `usage_event` log, or
   add a durable daily snapshot table mirroring `customer_health_history`? `customer_usage`
   itself is one mutable row per `(org, email)` — confirmed no history.
3. **Byte-stability.** Orgs that have not opted into usage (weight 0) must see unchanged
   health scores and unchanged churn probabilities, exactly as M3.2 guaranteed.
4. **Stretch, not committed.** Expose the drop as an automation trigger so it composes with
   the shipped churn-playbook auto-run (M4.1.5, `AI-TRACKING.md:251`).

## Open questions for the interview

- What counts as a "drop"? Relative % decline, absolute inactivity streak, or both?
- Over what comparison window, and what minimum history before the signal may fire
  (cold-start guard)?
- Does the drop feed the health score, the churn probability, or both?
- New opt-in knob, or does it ride the existing `health_weight_usage` opt-in?

**NOTE:** `CLAUDE.md`'s billing / plan-gating / Stripe / Resend sections are STALE
(pre-OSS-pivot). All features are unlocked (MIT, self-hosted, BYOK). Do not gate this feature
behind a plan tier.
