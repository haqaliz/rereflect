# Aspect spec — Docs, changelog & tracking markers

**Feature:** `intercom-webhook-reply-rating` (prd.md R7) · **Aspect:** `docs-tracking-changelog`

## Problem slice

The feature flips the honest-limits claims from #16 ("the webhook's replied/rating
events are still dedup-inert — flagged follow-up, not fixed") and closes the
follow-up defect note. Docs must state the new reality; tracking markers flip.

## In-scope

- `docs/SELF_HOSTING.md`:
  - :1956-1957 "still dedup-inert … the pull is what delivers replies and ratings" →
    replaced: webhook replied/rating events now enrich the conversation's item in real
    time (when the item exists); the pull remains the guaranteed fallback.
  - :1724-1725 / :1752 / :1821-1822 / :1907-1910 — the "replies and ratings become
    feedback items" + "three topics handled" + subscribe-all-three claims become
    accurate; verify the phrasing needs no change beyond the honest-limits block.
  - Honest limits: webhook enrichment applies only to conversations whose items exist
    (no backfill); payloads without parts fall back to a detail fetch.
- `CHANGELOG.md`: a new entry + a correction of the #16 entry's ":43-44 the webhook's
  replied/rating.added events remain dedup-inert" claim (house correction pattern,
  :383-386 style).
- `DEV-TRACKING.md`: the follow-up defect note (:518-522, inside the #16 SHIPPED
  bullet) → **FIXED** with a shipped summary + merge-facts placeholder
  (`(merged <merge-sha>, PR <# pending>)`, filled post-merge per house rule).
- `docs/planning/intercom-pull-replies-and-ratings/prd.md` + its
  docs-tracking-changelog spec: the "not fixed here" lines get a pointer to this card
  (no history editing).

## Out of scope

- The inert trigger UI (deferred — N1 in the PRD).
- Landing page (no claims about webhook reply delivery there — verify with a grep).
- `intercom-oauth-path-retirement` marker (unchanged).

## Acceptance criteria (testable)

1. Grep: "dedup-inert"/"still inert" gone from live docs (SELF_HOSTING + CHANGELOG);
   the CHANGELOG correction references the fix.
2. DEV-TRACKING follow-up note reads FIXED with the shipped summary + placeholders.
3. Docs state the honest limits (existing-item-only, no backfill, fallback fetch).
4. No landing-page claims affected.

## Dependencies & sequencing

- Last aspect (after code lands; merge facts filled post-merge).

## Open questions / risks

- None material.
