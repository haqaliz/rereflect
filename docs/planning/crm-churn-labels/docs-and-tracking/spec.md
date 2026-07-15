# Aspect spec — docs-and-tracking

**Parent PRD:** `../prd.md` (M8) · **Slug:** `docs-and-tracking` · **Sequencing:** wave 4

## Problem slice & outcome

Every recent feature here ships `docs(...)` commits — CRM enrichment, writeback, status-sync and
public-API v3 all landed with `SELF_HOSTING.md` + `CHANGELOG.md` + tracking updates in the same
branch. In self-hosted OSS, docs that lag are a product that cannot be operated: **this feature is
default-deny, so an operator who never reads the setup docs gets literally nothing.** The docs are
not a write-up of the feature; they are the on-ramp to it.

**Outcome:** an operator goes from "CRM connected" to "CRM churn suggestions in the review queue"
using `docs/SELF_HOSTING.md` alone — and every surface describing this feature states, in the
product's own honest register, what it does **not** claim.

## In scope

1. **`docs/SELF_HOSTING.md` — operator setup (the load-bearing doc).** A CRM churn-labels section
   beside the existing CRM/status-sync sections: connect the CRM (one CRM per org); enable "Suggest
   churn labels from lost renewals" per provider; **pick renewal pipelines (HubSpot) / opportunity
   types (Salesforce)** from the live picker; what **default-deny means** — nothing happens until
   pipelines/types are named, and a null/unrecognised discriminator produces no suggestion, ever;
   what **backfill does** — on-demand, operator-chosen window (default 24 months, explicit max),
   suggestions not labels, resumable, capped with the dropped count surfaced; how to **review**
   (queue, evidence, bulk confirm/reject, required reason code); what confirming does (writes a
   `manual` churn event the calibrator trains on); troubleshooting (no suggestions → unconfigured
   pipelines; 403 → CRM scope; 429 → throttled).
2. **`CHANGELOG.md`** — one entry in the house format: the capability, the default-off posture, and —
   as a fix, not silently — that **AI readiness now counts only trainable labels**, so an org's
   readiness number may go *down* (M6).
3. **`AI-TRACKING.md`** — a new row in **"Current AI Capabilities (Built)"** (`:35`) for CRM-sourced
   churn label suggestions; a note under **M5.3** that label supply now has a **CRM source**
   (previously manual-entry only), and that the **500-label gate is under review per PRD R8** — the
   "≥5,000 globally" half is a pre-pivot artifact with no single-tenant meaning. Never present 500 as settled.
4. **`README.md`** — the feature named where CRM/churn capabilities are listed. One line, honest.
5. **Landing page integration copy (`services/landing-web`)** — where CRM capabilities are listed:
   `lib/integrations.ts`, `app/integrations/page.tsx`, `app/integrations/hubspot/page.tsx` (+ the SF
   equivalent), `components/landing/BentoFeatures.tsx` / `FAQ.tsx`. Same honesty bar as the docs.
6. **The honesty clauses — non-negotiable, on every surface above** (and screenshots/snippets only
   for what actually shipped — describe what shipped, not the PRD).
   - **No churn-accuracy claims.** This produces *labels*; whether more labels improve the model is
     M5.3's question (PRD "Non-metrics"). No AUC/accuracy/"better predictions" language.
   - **Suggestions are operator-confirmed, never auto-applied** — nothing reaches the training set
     without a human; no auto-confirm exists.
   - **Default-deny** — nothing happens until configured; an org that ignores this sees no change.
   - **No promise any org reaches 500.** An org's real lost-renewal count is whatever it is.
   - **A lost renewal is not always a churn** (PRD R3) — which is *why* a human confirms.

## Out of scope

- Any production code, schema, endpoint, or UI change — docs and copy only; `docs/API.md` (these
  endpoints are internal/org-scoped, not public API).
- Deferred v2 items (auto-confirm, lifecycle-stage signal, winback reconciliation) documented as if
  they exist; the stale `hubspot_sync.py:18` docstring and the three no-source-filter consumers
  (`understanding.md` Finding 3) — not fixed, so not documented as fixed.

## Acceptance criteria (testable)

- **AC-1 (setup is complete and ordered).** `SELF_HOSTING.md` contains, in order: connect CRM → enable
  toggle → pick pipelines/types → optional backfill → review queue. A reader following only this doc
  reaches a suggestion in the queue. Verified against the shipped UI, not the PRD.
- **AC-2 (default-deny is explicit).** The section states plainly that no suggestions are produced
  until pipelines/types are configured, and that null/unknown discriminators produce none.
- **AC-3 (backfill described honestly).** The paragraph states: on-demand (not automatic, not on
  enable), operator-chosen window (24-month default, explicit max), **suggestions not labels**,
  resumable/idempotent, cap truncation reported with its dropped count.
- **AC-4 (no accuracy claims — grep gate).** Across the five surfaces, **zero** occurrences of
  "improves accuracy", "more accurate predictions", "AUC", "better churn prediction", or the like.
- **AC-5 (confirm-required stated everywhere).** Each of the five surfaces says suggestions are
  human-reviewed, never auto-applied — landing copy included, no "automatically detects churn".
- **AC-6 (readiness change disclosed, not silent).** `CHANGELOG.md` states that `churn_labels_ready`
  now counts only trainable labels and that an org's readiness number may decrease as a result.
- **AC-7 (AI-TRACKING).** A new "Current AI Capabilities (Built)" row in the file's existing shape;
  the M5.3 note names the CRM label source **and** flags the 500 gate as under review per PRD R8.
- **AC-8 (landing tests stay green).** Copy edits keep `__tests__/landing/IntegrationBar.test.tsx`
  and integration-copy tests passing; a test asserting old copy is updated, never deleted.

**Test style.** Mostly reviewer checklist — this aspect ships prose. Automatable: AC-4/AC-7 (grep over
the five surfaces) and AC-8 (`npm test` in `services/landing-web`; landing-web has **no eslint**).

## Dependencies & sequencing

**Wave 4 — last. Blocked on everything.** Documenting unshipped behaviour is precisely the dishonesty
this PRD was written against, so this starts only after `provider-churn-fetch` (M1), rule + config +
picker (M2/M3), `data-model` + `harvester-core` (M4), `review-queue` (M5), `readiness-honesty` (M6)
and `historical-backfill` (M7) merge. Blocks nothing; the only file it owns alone is landing-web copy.

## Risks

- **Marketing copy drifts optimistic.** Landing pages are where "automatically detects churn" writes
  itself. AC-4/AC-5 apply the same bar to `landing-web`; IntegrationBar/BentoFeatures are riskiest.
- **Documenting the PRD instead of the diff.** If an aspect ships reduced, prose written from this
  spec becomes a lie. §7 forces a read of the merged branch: write these docs from the code.
- **The readiness disclosure is unflattering.** An operator's number may drop (M6); saying so plainly
  (AC-6) is the point — a silent correction to a trust surface is worse than the bug.
- **Restating 500 as fact.** PRD R8 says it was calibrated for a hosted multi-tenant product that
  no longer exists — AC-7 pins the framing.
