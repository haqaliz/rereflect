# Card — feat/intercom-webhook-reply-rating (freeform, no GitHub issue)

Source: the follow-up defect note recorded in DEV-TRACKING.md:518-522 (from
`intercom-pull-replies-and-ratings`, PR #16), plus the dig findings of that feature.
Branch `feat/intercom-webhook-reply-rating`, worktree
`.claude/worktrees/feat-intercom-webhook-reply`.

## Brief

The Intercom **webhook reply/rating path is inert**. Two independent causes:

1. **Dedup key = conversation id for all three event types**
   (`adapters/intercom.py:171-180` → `source_events.py:312-319`): a
   `conversation.user.replied` or `conversation.rating.added` event dedups against the
   conversation's `created` row and never creates or updates anything.
2. **The seeded source trigger is `{"new_conversations": True}`**
   (`intercom_integration.py:262-271`): replied/rating webhook events fail
   `check_triggers` before the dedup is even reached.

Since #16, the 15-minute **pull** enriches the per-conversation item with replies +
rating. This card gives the **webhook path the same enrichment in real time** — a
webhook reply/rating event should merge into the existing item (same merge semantics,
same bounded re-analysis), not vanish. For webhook-wired installs this removes the up
to-15-minute latency for reply/rating content; for pull-only installs nothing changes.

## Caveats (carried into the PRD, must not be papered over)

- **Payload-shape divergence (the dig's open question, unresolved).** The adapter's
  `_extract_reply`/`_extract_rating` expect **part-shaped** items (top-level `body`,
  `author`, `id` = part id), while the backend's own webhook tests use
  **conversation-wrapped** payloads (`item.conversation_parts.conversation_parts[]`,
  `item.conversation_rating`) — and the real Intercom webhook payloads are
  conversation-wrapped. Against real payloads, `_extract_reply` reads `item.get("body")`
  → `""` → `empty_text` ignored. **The enrichment must key off the conversation id
  and fetch/merge robustly regardless of the item shape** (the pull already fetches
  `GET /conversations/{id}` via `IntercomClient.get_conversation`).
- **One-item-per-conversation invariant stays.** Webhook reply/rating events enrich
  the existing item; they never create siblings (the D3 invariant, pinned by six
  characterization tests).
- **Trigger semantics.** The seed trigger (`new_conversations` only) means replied/
  rating events were never even evaluated. Fixing the delivery path must also decide
  the trigger story: replied/rating events should be deliverable (checked) regardless
  of trigger config, since they now *enrich* rather than create — or the seed trigger
  must gain `replies`/`ratings`. Decide in the PRD.
- **Re-analysis is bounded** (only changed items, via the `reanalyze_feedback` seam
  from #16) — a webhook reply re-analyzes its conversation's item exactly once.

## Roadmap facts (from DEV-TRACKING.md, cited)

- Follow-up note (DEV-TRACKING.md:518-522): "the webhook reply/rating path is still
  inert — the dedup key (`external_message_id` = conversation id for all three event
  types) and the `new_conversations`-only seed trigger make `conversation.user.replied`
  / `conversation.rating.added` events dedup into nothing; the pull covers the content
  on its 15-minute cycle."
- Enrichment + reanalysis seams to reuse (from #16): `_enrich_conversation_replies`
  (intercom_sync.py), `extract_reply_parts`/`extract_rating`/`format_reply_merge`
  (adapters/intercom_parts.py), `reanalyze_feedback` (analysis.py), and
  `IntercomClient.get_conversation` (clients/intercom.py).

## Deliverables (proposed, refine in PRD)

1. Webhook replied/rating events reliably reach an enrichment path: conversation id
   extracted robustly from the payload, existing item found, merge + bounded
   re-analysis via the #16 seams.
2. Trigger story resolved (delivery regardless of `new_conversations`-only seed, with
   tests).
3. Payload-shape divergence resolved or pinned (golden fixture for the replied/rating
   webhook envelopes, read by both suites like the created-envelope fixture).
4. Docs + CHANGELOG + DEV-TRACKING follow-up note → FIXED.

## Out of scope (guardrails)

- Not changing the pull enrichment (#16) — this is the webhook delivery path only.
- Not building `intercom-oauth-path-retirement` (gated on evidence of use).
- No plan gates (`SELF_HOSTED=true`); no new vendor dependency; no claims about
  analysis quality beyond "webhook-wired installs get reply/rating content in real
  time instead of on the pull cycle".
