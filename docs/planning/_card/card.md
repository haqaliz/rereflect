# Card — feat/intercom-pull-replies-and-ratings (freeform, no GitHub issue)

Source: DEV-TRACKING.md "Deferred v2 — Intercom" entry `intercom-pull-replies-and-ratings`
(line ~509), plus the `intercom-selfhost-ingestion` planning docs. Branch
`feat/intercom-pull-replies-and-ratings`, worktree `.claude/worktrees/feat-intercom-pull-replies`.

## Brief

The Intercom **15-minute pull ingests the first message of a conversation only**.
Replies and ratings arrive **via the webhook path only**, so a pull-only install (no
webhook wired — the common self-host case, since webhook subscription is
Developer-Hub-only and cannot be provisioned via API) **never sees replies or
ratings**. The AI pipeline (sentiment, categories, churn) then analyzes first messages
only for those orgs. This card adds **conversation-parts fetching** to the pull path
so replies and ratings are ingested without a webhook.

## Caveats (carried into the PRD, must not be papered over)

- **One-feedback-item-per-conversation semantics.** The ingestion core dedups by
  `external_message_id` (source_events.py:312-319) so exactly one FeedbackItem per
  conversation exists (intercom_sync.py D3). Replies/ratings must slot into the
  existing per-conversation item semantics — either as updates to the conversation's
  item or as separate items — without breaking the dedup, analysis, or Customer 360
  behavior the webhook path already establishes.
- **Pull capacity is bounded** (20 pages/run, no historical backfill, cursor never
  epoch). Fetching parts per conversation adds a second API call per conversation —
  rate limits (429/Retry-After) and the 20-page/run cap must be respected, and the
  per-run work must stay bounded.
- **What "rating" means in the API**: `conversation.rating.added` carries the rating
  object; the pull's `/conversations/search` summaries may or may not include it —
  verify the actual payload shape before assuming parity with the webhook adapter.
- **No claim about analysis quality** (house rule — the ingestion PRD makes the same
  disclaimer). This changes label *supply* (more complete conversations), not the
  model.

## Roadmap facts (from DEV-TRACKING.md, cited)

- Deferred v2 entry (`DEV-TRACKING.md:509-511`): "the 15-minute pull ingests the
  **first message** of a conversation only. Replies and ratings arrive via the webhook
  path, so a pull-only install (no webhook wired) never sees them. Needs
  conversation-parts fetching."
- The pull itself (`AI-TRACKING.md:66`): 15-min beat, `POST /conversations/search`,
  `updated_at >=` cursor, `starting_after` pagination, 20-page/run cap, routed through
  the shared `_find_matching_sources` / `_process_event_for_source` core.
- The webhook path already handles the three topics
  (`conversation.user.created/replied/rating.added`) — the reply/rating adapters are
  the parity target for the pull path.

## Deliverables (proposed, refine in PRD)

1. Pull path fetches conversation parts (replies) and ratings for conversations it
   ingests, producing the same feedback items the webhook path would.
2. Bounded: respects 429/Retry-After, per-run caps, no unbounded fan-out.
3. Dedup semantics unchanged (one item per conversation, or a documented deliberate
   change with tests).
4. Docs + CHANGELOG + DEV-TRACKING marker (deferred-v2 entry → SHIPPED).

## Out of scope (guardrails)

- Not building `intercom-backlog-drain-visibility`, `intercom-writeback` (shipped),
  or `intercom-oauth-path-retirement` (gated on evidence of use) — separate slices.
- No plan gates (`SELF_HOSTED=true`); no new vendor dependency; no claims beyond what
  the pull actually delivers.
