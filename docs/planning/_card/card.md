# Card — usage-decline-churn-labels (freeform feat, no GitHub issue)

**Type:** feat
**Slug:** usage-decline-churn-labels
**Branch:** `feat/usage-decline-churn-labels`
**Source:** Freeform task selected via `rereflect-next` on 2026-07-23. No GitHub issue.

## Brief (from rereflect-next handoff, verbatim)

> Add product-usage decline as a third churn-label SUGGESTION source, feeding the existing
> review queue shipped by `crm-churn-labels` (docs/planning/crm-churn-labels/). AI-TRACKING.md:480-485
> names this as newly feasible-but-unplanned now that M3.2b's `customer_usage_history` snapshot exists.
> A worker detector reads `customer_usage_history` (reusing `usage_trend_severity.py`) and, on a
> sustained decline, writes a `ChurnLabelSuggestion` with `provider='usage_decline'` and a deterministic
> synthetic `external_opportunity_id` — the unique constraint is (org, provider, external_opportunity_id)
> and `churn_suggestions.py` filters provider as a free string with no whitelist, so aim for no migration
> and no route changes in slice 1. Default-deny + opt-in per org, confirm-in-review only (never
> auto-applied), and these must stay excluded from `churn_labels_ready` on the readiness card exactly as
> CRM suggestions are. Be honest in the docs: a usage decline is not churn, the ≥5 active-day baseline
> floor permanently excludes quiet accounts, there's a ~14-day warm-up, this makes no claim about
> churn-prediction quality, and the 500-label M5.3 gate remains under review (AI-TRACKING.md:467-478).

## Why this was picked (citations)

- `AI-TRACKING.md:480-485` — the M5.3 note's **Update 2026-07-22**: the old "no history to detect a
  drop against" blocker is resolved by M3.2b's `customer_usage_history`; using a sustained usage
  decline as a churn-label *source* is "now feasible but remains **unplanned** (it would need a
  confirm-in-review step like `crm-churn-labels`, not auto-labelling)."
- `AI-TRACKING.md:446-451` — **M5.3 (Per-org churn ML model)** is the one open Track, and it is
  gated purely on **label supply**.
- `AI-TRACKING.md:453-461` — `crm-churn-labels` (shipped 2026-07-15) established the exact pattern
  to reuse: suggestions are **not labels**, they enter a review queue, become `source='manual'`
  churn events only on operator confirmation with a reason code, default-deny, and
  `pending_suggestions` is **deliberately excluded** from `churn_labels_ready`.
- `AI-TRACKING.md:216-263` — M3.2b (`usage-trend-churn-signal`, 2026-07-22) and M3.2c
  (`usage-trend-automation-trigger`, 2026-07-23) built the durable snapshot + trend classification
  this detector reads.
- `services/backend-api/src/models/churn_label_suggestion.py` — unique constraint is
  `(organization_id, provider, external_opportunity_id)`; `provider` is a plain `String(50)` with
  no enum/whitelist.
- `services/backend-api/src/api/routes/churn_suggestions.py:219,262` — `provider` is used purely as
  a free-string **filter**; no validation list to extend.

## Moat rationale

The shipped CRM label source produces **nothing** for a self-hoster with no HubSpot/Salesforce —
which is the default OSS deployment. A usage-decline source is the only label supply that works
CRM-free, and it reuses telemetry the operator already instruments. It also closes the loop the
last two branches opened: M3.2b built the trend signal, M3.2c wired it to actions, and this wires
it to *learning*. No plan gate, no SMTP, no cross-tenant data.

## Known caveats to resolve in the dig / PRD

1. **A usage decline is not churn.** This changes label *supply*, not label *quality*. False
   positives land on a human reviewer — the review queue is the whole safety mechanism, and the
   suggestion's `evidence` payload has to be good enough for a human to actually adjudicate.
2. **Inherited structural blind spot.** M3.2b's **≥5 active-day baseline floor permanently excludes
   light-usage customers** (`AI-TRACKING.md:258-263`), so the quietest accounts — arguably the most
   likely to churn — structurally cannot produce a suggestion. This must be stated, not hidden.
3. **Warm-up.** `customer_usage_history` began 2026-07-22; most customers are
   `insufficient_history` for ~2 more weeks. `insufficient_history` must be an explicit non-source.
4. **Unvalidated upstream dependency.** The whole feature sits downstream of the operator having
   instrumented usage events — `AI-TRACKING.md:262` calls that unvalidated.
5. **No migration is the goal, not a guarantee.** The dig must confirm `provider='usage_decline'`
   and a synthetic `external_opportunity_id` genuinely satisfy the existing NOT NULL + unique
   constraint and the existing review/confirm path, incl. the readiness card's
   `pending_suggestions` split.
6. **Scope fence.** `churn_risk_component`, `churn_probability`, and the isotonic calibration stay
   untouched — same guarantee M3.2b and M3.2c both preserved.
7. **The 500-label gate is under review** (`AI-TRACKING.md:467-478`) — do not restate it as settled,
   and do not justify this feature by "it gets you to 500".

## Open questions for the interview

1. What counts as a **sustained** decline worth suggesting — `sharp_decline` only, or `declining`
   held for N consecutive days? Is there a minimum absolute-usage floor on top of the trend state?
2. **Re-suggestion semantics.** The synthetic `external_opportunity_id` determines whether a
   customer who declines, is rejected, and declines again months later can produce a second
   suggestion. What is the intended key (email + decline-start date? + episode counter?)?
3. What is `suggested_churned_at` for a usage decline — the decline start, the last active day, or
   the detection date?
4. What goes in `evidence` so a reviewer can actually judge it (usage series? trend pct? last
   active day? feedback/health context)?
5. Where does the detector run — inline in the daily `recompute_usage_scores` seam (like M3.2c's
   evaluator) or as its own scheduled task?
6. Does the review-queue UI need a provider-specific evidence renderer, or does the CRM renderer
   degrade acceptably?
7. Should a confirmed usage-decline suggestion record a distinguishable churn-event reason code so
   later M5.3 backtests can separate CRM-sourced from usage-sourced labels?

**NOTE:** `CLAUDE.md`'s billing / plan-gating / Stripe / Resend sections are STALE (pre-OSS-pivot).
All features are unlocked (MIT, self-hosted, BYOK). Do not gate this feature behind a plan tier.
