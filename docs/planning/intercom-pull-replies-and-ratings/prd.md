# PRD — Intercom pull: replies & ratings enrichment

**Slug:** `intercom-pull-replies-and-ratings` · **Branch:** `feat/intercom-pull-replies-and-ratings`
**Type:** feat · **Created:** 2026-08-15
**Card:** `docs/planning/_card/card.md` (freeform, no GitHub issue) · **Source:** DEV-TRACKING deferred-v2 entry

---

## Problem Statement

The Intercom **15-minute pull ingests the first message of a conversation only**
(intercom_sync.py D3; pull-sync/spec.md:65-66). Replies and ratings were assumed to
arrive "via the webhook path" — **but the dig found that path is effectively inert
too**:

- The dedup key (`external_message_id`) is the **conversation id for all three event
  types** (`adapters/intercom.py:171-180`), so a `conversation.user.replied` or
  `.rating.added` event dedups against the conversation's `created` row and never
  creates an item (`source_events.py:312-319`).
- The seeded source trigger is `{"new_conversations": True}` (`intercom_integration.py:262-271`),
  so replied/rating webhook events fail `check_triggers` anyway.
- No code anywhere appends reply content to an existing item.

Net: **replies and ratings never reach the analyzed content in any install** — pull-only
or webhook. The AI pipeline (sentiment, categories, churn risk) scores the first message
of each conversation only, and the satisfaction rating is lost entirely.

The deferred-v2 entry names the fix: *"Needs conversation-parts fetching"*
(DEV-TRACKING.md:509-511).

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| Full conversation content is ingested | A pull run on a conversation with replies produces **one** FeedbackItem whose `text` includes the reply content; the rating lands in `source_metadata` — verified by tests |
| One item per conversation, ever (D3 invariant) | All six existing one-item characterization tests pass **unchanged** |
| Idempotent enrichment | Re-running the pull on the same conversation changes nothing (no duplicated reply text); verified by a redelivery test |
| Analysis reflects the thread | An item that gained new reply content is **re-analyzed** (sentiment/categories/churn refreshed); unchanged items are not — seam test pins the call |
| Bounded & honest | Per-run work respects the 20-page cap; 429/5xx → retry via the client taxonomy; no claims about analysis quality beyond "the full thread is now scored" |

Non-goals: adoption metrics (single-tenant OSS).

## User Personas & Scenarios

- **Self-hoster with a pull-only install (no webhook — the common case).** Today they
  see only first messages; replies from the customer and the support team are invisible,
  so sentiment/churn score half the conversation. After: the item text contains the
  thread, the rating is on the item, and re-analysis scores the full conversation.
- **Operator of an existing install with old conversations.** Conversations already
  ingested before this ships stay first-message-only unless they get new activity
  (honest limit — no backfill).

## Requirements

### Must-have

**R1 — Client: conversation parts access.** `IntercomClient` (`src/clients/intercom.py`)
gains a way to fetch conversation parts + rating. **Primary path to verify in the plan
(R1a):** `/conversations/search` with `display_as: "conversation_parts"` so parts ride
along in the search response (no fan-out). **Fallback (R1b):** `GET /conversations/{id}`
per changed conversation (the parsing already exists in `adapter.fetch_context`,
intercom.py:216-229). The plan MUST verify which shape the API actually returns before
implementing (mock the documented response either way; a real-app smoke check is
preferred). Both paths route through the existing error taxonomy
(IntercomAuthError/TransientError/NotFoundError) and the injectable transport.

**R2 — Adapter: part extraction + merge.** New adapter logic (reusing `_contact_email`
and `strip_html`): from a conversation's parts, extract `{part_id, author, body,
created_at}` for reply parts (`part_type`/`type` "comment"-family — verify the real
shape), excluding the first message itself, and the `{rating, remark}` object. **Admin /
bot authors:** reply content is INCLUDED in the text, but the author is never used as
`customer_email` (existing `_contact_email` rule — a teammate's reply must not corrupt
health/churn attribution).

**R3 — Pull enrichment, idempotent by part id.** In `_sync_org`
(`intercom_sync.py:111-214`), after the event loop, for each conversation that the run
saw: fetch parts (R1), diff against `source_metadata` (a `replies[]` array of part_ids
already merged), append only NEW replies to the item's `text` (with a documented
separator + author attribution line) and store the full part list + `rating`/`remark` in
`source_metadata`. Same conversation seen twice across runs → second run is a no-op.

**R4 — Re-analysis, bounded to changed items.** When an item gained new content in a
run, re-run its analysis via the existing re-analyze seam (the feedback detail
"re-analyze" action's underlying function — verify the force seam in the plan; the
analysis task skips already-analyzed items by default, analysis.py:166-168). Items that
did not change are not touched. The re-analysis must reuse the normal analysis pipeline
(sentiment, categorization, churn factors, health recompute when `customer_email`
present) — identical to a manual re-analyze.

**R5 — Bounded per-run work.** The enrichment must not unboundedly fan out: the search
window + 20-page cap bound the conversations per run; the detail-fetch path (R1b) must
cap per-run detail calls with a logged drop count (mirror the usage-decline per-run cap
pattern) and honor 429/`Retry-After` via the client's IntercomTransientError → task
retry. The `>=` boundary re-fetch conversation is enriched at most once per change.

**R6 — Rating captured, metadata-only.** The satisfaction rating + remark are stored in
`source_metadata` (`rating`, `remark`, `rated_at` when available) and surfaced on the
feedback detail. **Not** appended to `text` (a "Rating: 5/5" line would skew sentiment
analysis). No `customer_email` attribution for ratings (unchanged by design).

**R7 — Tests.** (a) New: part extraction, merge formatting, idempotent redelivery,
rating metadata, admin-author handling, re-analysis seam (fires for changed, not for
unchanged), per-run cap behavior. (b) **Characterization:** the six existing
one-item-per-conversation tests pass unchanged
(test_intercom_sync.py:246-261, :389-407; test_intercom_envelope_seam.py:197-268;
test_intercom_tenancy_discriminator.py:282-318; test_intercom_sync.py:365-387).

**R8 — Docs & tracking (part of "done").** SELF_HOSTING.md:1929-1937 honest-limits block
(the "first message only / webhook only" claims flip); CHANGELOG entry + correction of
the live "Added" entry claims (CHANGELOG.md:342-343); `pull-sync/spec.md:65-66` struck;
AI-TRACKING.md:66 row amended; DEV-TRACKING deferred-v2
`intercom-pull-replies-and-ratings` → SHIPPED. **Truth fix (separate finding, same docs
pass):** SELF_HOSTING.md:1732 claims OAuth orgs get pull sync ("Yes — every 15
minutes"), but `sync_all_intercom` iterates only `IntercomIntegration` rows
(intercom_sync.py:296-304) — OAuth orgs have no pull. Correct the table cell.

### Should-have

- **S1 — Re-analysis batching:** the re-analysis dispatch is a single bounded fan-out
  (one `analyze_single_feedback.delay` per changed item), not a per-part loop.

### Nice-to-have (explicitly deferrable)

- **N1 — Surface the rating in the UI** (badge on feedback detail reading
  `source_metadata.rating`) — metadata is stored now; the badge is a separate frontend
  slice.
- **N2 — Part content on the feedback detail** (expandable "Full conversation" view
  from `source_metadata.replies`) — same, separate slice.

## Technical Considerations

- **Services:** worker-service only for code (client + adapter + sync task + analysis
  seam). No migration — `source_metadata` is free-form JSON on the existing
  `FeedbackItem`. Docs/tracking across the repo.
- **The one-item invariant is load-bearing.** All enrichment merges into the existing
  item. Part-scoping dedup keys (separate-items design) was rejected in the interview —
  it breaks cross-path dedup with the webhook and six pinned tests.
- **Re-analysis seam:** verify whether the UI "re-analyze" action calls
  `analyze_single_feedback` with a force flag or a distinct task; the pull must reuse
  exactly that seam so behavior is identical to a manual re-analyze (characterization).
- **Content merge format:** `"\n\n--- Reply by {author_name} ({created_at}) ---\n{body}"`
  (HTML-stripped, admin authors included but never attributed as customer). Document the
  exact format in the spec; the webhook-parity "Rating: X/5" text form is NOT used
  (R6).
- **API verification is the plan's first task (R1).** The `display_as` parameter's
  exact behavior must be confirmed against Intercom's documented response shape; the
  MockTransport tests pin whichever shape is real. If `display_as` is unreliable, R1b
  (`GET /conversations/{id}`, parse already proven in `fetch_context`) is the fallback
  with the R5 cap.
- **Trigger interplay:** the enrichment runs for conversations the pull already ingests
  (`new_conversations` trigger, the seed). A source configured to `replies`/`ratings`
  only still ingests nothing from the pull today (created fails check_triggers) — the
  enrichment inherits the pull's existing trigger behavior; not changed here (flag,
  don't fix).
- **No plan gate** (`SELF_HOSTED=true`); no new dependencies; CPU/network bounded per
  R5.

## Risks & Open Questions

| # | Risk | Mitigation |
|---|---|---|
| R1 | **`display_as: "conversation_parts"` may not return what we expect** (unverified API behavior) | Plan's task 0: verify against Intercom docs/response shapes; R1b fallback with cap; MockTransport pins the real shape either way |
| R2 | **Re-analysis churn**: every reply triggers a full LLM/analysis pass | Bounded to changed items only (R4); re-analysis is a normal queued task; the plan should assert unchanged items never dispatch |
| R3 | **Enrichment of admin replies** could look like customer sentiment | Content included, `_contact_email` rule untouched — never attributed; honest docs note |
| R4 | **Duplicate text on redelivery** | Idempotent by part_id set in `source_metadata` (R3); redelivery test (R7) |
| R5 | **Latent webhook reply/rating path** (findings: dedup key + seed trigger make it inert) | Flagged as a separate defect — NOT fixed in this card (scope discipline); the docs pass states the honest current state. **— SHIPPED 2026-08-17** by `intercom-webhook-reply-rating`: the webhook replied/rating path now enriches the conversation's existing item in real time (existing-item-only). |
| R6 | **Old conversations stay first-message-only** | Honest limit, stated in docs (no backfill — enrichment applies to conversations the pull re-sees) |

**Open questions**
- **OQ1 — Re-analysis force seam.** Does the UI re-analyze reuse `analyze_single_feedback`
  with a flag, or a separate task? *The plan verifies and reuses whatever the UI does —
  identical semantics.*
- **OQ2 — Merge format details.** Exact separator/attribution format and whether reply
  content is HTML-stripped (yes) and length-capped (text column limits?). *Decide in
  spec; keep the format documented and pinned by tests.*
- **OQ3 — Rating `rated_at` availability.** Whether the parts/rating response carries a
  timestamp for the rating. *Optional metadata field; absent → omit.*

## Out of Scope

- **Separate items per reply/rating** (rejected in interview — breaks the D3 invariant
  and cross-path dedup).
- ~~**Fixing the latent webhook reply/rating path** (flagged as a separate defect; the
  docs pass states the honest current state instead of claiming webhook parity).~~
  — **SHIPPED 2026-08-17** (`intercom-webhook-reply-rating`): the webhook replied/rating
  path now enriches the conversation's existing item in real time (existing-item-only,
  no backfill; the pull stays the fallback). See
  `docs/planning/intercom-webhook-reply-rating/`.
- **Backfill of parts for pre-existing conversations** (R6 honest limit).
- **Rating → `customer_email` attribution** (unchanged by design).
- **UI slices** (N1 rating badge, N2 full-conversation view) — deferred.
- `intercom-backlog-drain-visibility` and `intercom-oauth-path-retirement` — separate
  cards.
- **No plan gate**, no migration, no new dependencies.

## Honest limits (state in docs + changelog)

- Enrichment applies to conversations the pull **re-sees after the feature ships** —
  older conversations stay first-message-only until they get new activity.
- "Replies and ratings are now pulled" does **not** claim improved analysis quality —
  it means the full thread is scored instead of the first message.
- The webhook reply/rating path is **not** fixed by this card; docs stop claiming it
  delivers replies/ratings today.
- Per-run detail-fetch cap: very large active backlogs may take several runs to enrich
  fully (logged drop count, cursor resumes).

## Self-critique (Phase 4)

- 🔴 **The `display_as` verification is the whole ballgame.** If Intercom's search
  response shape differs from expectations, R1a is dead and R1b (per-conversation GET)
  becomes the implementation — with real per-run cost. The PRD does not resolve this;
  the plan must make it task 0 and the tests must pin the verified shape.
- 🟡 **Re-analysis semantics need characterization before the slice.** The "skip if
  already analyzed" gate means the pull cannot naively call the analysis task; reusing
  the UI re-analyze seam is assumed to exist with a force path — verified in the plan,
  not asserted here.
- 🟡 **The webhook-parity myth is bigger than the card.** The finding that replied/rating
  webhook events dedup into nothing contradicts CHANGELOG/SELF_HOSTING claims that
  predate this work; correcting those claims is in scope (R8) but the actual webhook
  defect is a separate card that should follow — **shipped 2026-08-17** as
  `intercom-webhook-reply-rating`.
- 🟢 Scope, invariant preservation, idempotency, and honesty framing are pinned.

**The question I'd want answered before greenlighting:** if replies never reached
analysis in any install so far, is the *content* merge enough for the first slice, or
does the product value depend on the (separate-card) webhook reply path also being made
real — and should the two ship together?
