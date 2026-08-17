# Aspect spec — Docs, changelog & tracking markers

**Feature:** `intercom-pull-replies-and-ratings` (prd.md R8) · **Aspect:** `docs-tracking-changelog`

## Problem slice

The feature flips several shipped claims ("first message only / replies via webhook
only") and corrects one pre-existing falsehood (OAuth orgs do not get pull sync). Docs
must state the new reality honestly and the tracking markers must flip — part of "done".

## In-scope

- `docs/SELF_HOSTING.md:1929-1937` honest-limits block: "The pull ingests the first
  message… replies and ratings arrive through the webhook only" → replaced with the new
  reality (pull enriches replies + rating; webhook optional for latency; honest limits:
  no backfill for older conversations, enrichment applies to re-seen conversations,
  no analysis-quality claim beyond full-thread scoring).
- `docs/SELF_HOSTING.md:1732` table truth fix: OAuth column "Pull sync | Yes — every 15
  minutes" → correct (OAuth orgs have no pull; `sync_all_intercom` iterates
  `IntercomIntegration` rows only). State it as the token-paste-only pull, or honest
  "No" with the reason.
- `CHANGELOG.md` — new entry + correction of the live "Added" entry's honest-limits
  claims (CHANGELOG.md:342-343).
- `docs/planning/intercom-selfhost-ingestion/pull-sync/spec.md:65-66` — the "first
  message only" line struck/amended; the out-of-scope "per-conversation-part ingestion"
  bullet (prd.md:309-310 of that PRD) flips with a pointer.
- `AI-TRACKING.md:66` Intercom row — amend the pull description (replies/ratings now
  enriched via conversation-parts; keep the honest tone).
- `DEV-TRACKING.md` — deferred-v2 `intercom-pull-replies-and-ratings` (:509-511) →
  **SHIPPED** with the house strikethrough style; the block header count updated.
- **Flag-only (no edit):** the latent webhook reply/rating defect (dedup key +
  seed-trigger make webhook replied/rating events inert) — recorded as a follow-up
  defect note inside the SHIPPED marker, not fixed here (prd.md out-of-scope). —
  **SHIPPED 2026-08-17** as `intercom-webhook-reply-rating` (see that card's
  planning dir).

## Out of scope

- Fixing the webhook reply/rating path (separate defect). — now shipped as
  `intercom-webhook-reply-rating` (2026-08-17).
- `intercom-backlog-drain-visibility` / `intercom-oauth-path-retirement` markers.
- Landing page copy (nothing claims pull replies there; verify with a grep).

## Acceptance criteria (testable)

1. Grep: "webhook only" / "first message" claims about replies/ratings removed from
   SELF_HOSTING + CHANGELOG live entries; no surviving false "OAuth gets pull" cell.
2. DEV-TRACKING entry → SHIPPED with the shipped summary (merge facts filled
   post-merge per house rule).
3. Follow-up defect note recorded for the webhook reply/rating path.
4. No stale "one item per conversation" claims contradicted (the invariant still holds).

## Dependencies & sequencing

- Last aspect: needs the shipped facts (merge sha/PR filled post-merge per house rule).

## Open questions / risks

- Whether the OAuth table truth-fix belongs here or with the oauth-path-retirement card
  — lean: fix the cell now (it is a factual claim, not a retirement decision).
