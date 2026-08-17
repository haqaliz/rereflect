# PRD — Intercom webhook reply/rating enrichment

**Slug:** `intercom-webhook-reply-rating` · **Branch:** `feat/intercom-webhook-reply-rating`
**Type:** feat (defect fix) · **Created:** 2026-08-16
**Card:** `docs/planning/_card/card.md` (freeform, no GitHub issue) · **Source:** the
follow-up defect note from #16 (DEV-TRACKING.md:518-522)

---

## Problem Statement

The Intercom **webhook reply/rating path is inert** — and has been since the
integration shipped. Two swallow points, verified in code:

1. **Trigger check.** The seeded source trigger is `{"new_conversations": True}`
   (`intercom_integration.py:272`); `check_triggers` matches `conversation.user.replied`
   / `conversation.rating.added` only against `replies`/`ratings`/`all_conversations`
   configs (`adapters/intercom.py:63-71`). With the seed, replied/rating events die at
   `source_events.py:300-306` as `no_trigger_match` — **and the trigger UI is inert for
   intercom keys** (frontend `toggleTrigger` only handles `all_messages`/`mentions.bot`/
   `new_ticket`; the backend `TriggerConfig` schema lacks the intercom keys), so no
   operator can change this.
2. **Dedup.** Even with a matching trigger, `get_external_ids` returns
   `message_id = conversation_id` for all three event types (`adapters/intercom.py:171-180`),
   so a replied/rating event dedups against the conversation's `created` row and returns
   `duplicate` (`source_events.py:312-319`).

Additionally, the adapter's `_extract_reply`/`_extract_rating` expect **part-shaped**
items (top-level `body`/`author`/`rating`), while real Intercom webhook payloads for all
three topics are **conversation-wrapped** (the webhook docs' Object column is
"Conversation"; `data.item.id` IS the conversation id; parts nested at
`item.conversation_parts.conversation_parts[]`, rating at `item.conversation_rating`) —
so against real payloads the adapter would produce `message_id = ""` and empty text
anyway. Only `conversation.user.created` was ever end-to-end real.

Since #16, the **pull** enriches items with replies + rating on its 15-minute cycle.
This card gives the webhook path the **same enrichment in real time** for webhook-wired
installs — the flagged follow-up defect becomes a fix.

## Goals & Success Metrics

| Goal | Measure |
|---|---|
| Webhook replies/ratings reach the item | A `conversation.user.replied` webhook delivery enriches the existing item's text; a `rating.added` delivery writes `source_metadata` rating — verified by tests |
| One item per conversation, ever | All six one-item characterization tests pass unchanged; a created+replied+rating sequence yields exactly 1 item |
| Idempotent redelivery | Re-delivering the same reply merges nothing twice (part_id membership) and re-analyzes at most once |
| Bounded re-analysis | Text-changed enrichments dispatch exactly one re-analysis, after commit; rating-only changes dispatch none |
| No create-path interference | The enrichment's event-log status cannot collide with the created path's dedup (out-of-order delivery safe) |
| Honest docs | The "still dedup-inert" claims flip; the golden fixture pins the real conversation-wrapped shapes |

Non-goals: metrics (single-tenant OSS).

## User Personas & Scenarios

- **Webhook-wired install.** Subscribes to all three topics per the settings card.
  Today replies/ratings are silently dropped (no visible error). After: a customer
  reply enriches the conversation's feedback item within seconds (not up to 15
  minutes), and the rating lands on the item.
- **Pull-only install.** Unchanged — the pull keeps delivering on its cycle; the
  webhook path is additive.

## Requirements

### Must-have

**R1 — Enrichment branch in the shared core, before both swallow points.** In
`_process_event_for_source` (`source_events.py:275-428`), an intercom-specific guard at
the top: when `source.source_type == "intercom"` and `event_type in
("conversation.user.replied", "conversation.rating.added")`, route to the enrichment
path (R2) **instead of** the trigger check / dedup / create flow. **Trigger semantics
decision:** enrichment is NOT trigger-gated — a reply/rating enriches whenever the
conversation's item exists, regardless of the source's trigger config (the trigger UI
is inert for intercom keys anyway; enrichment is additive to items the org already
receives). If no item exists → logged noop (the create path owns item creation).

**R2 — Webhook enrichment module (new, seam-tested).** A new worker module
(`src/services/intercom_webhook_enrich.py` — the house "service" layer used by
writeback/usage cores) with one function, e.g.:
`enrich_webhook_item(db, source, event_type, event_data) -> dict`:
1. Conversation id: `event_data["data"]["item"]["id"]` (the real conversation-wrapped
   shape — same extraction the route uses, `source_webhooks.py:451`).
2. Item lookup (index-backed): `FeedbackItem(organization_id=source.organization_id,
   source="intercom", source_external_id=conversation_id)` — no item → `noop/no_item`.
3. Parts + rating: **payload-first** — extract from the payload's
   `conversation_parts.conversation_parts[]` / `conversation_rating` when present
   (real webhook payloads are API-aligned); **fallback** — `IntercomClient
   .get_conversation(conversation_id)` when absent (single fetch per event, no cap
   needed; 404 → `noop/not_found`, 401/403 → `error/auth_error` recorded, 429/5xx →
   transient → task retry).
4. Merge via the #16 seams (`extract_reply_parts`, `extract_rating`,
   `_enrich_conversation_replies` — idempotent by part_id; rating metadata-only).
5. Returns `{"status": "enriched"|"noop/...", "changed": bool, "feedback_id": int|None}`
   — `changed` True only when text changed (re-analysis trigger).

**R3 — Event log with a distinct status.** The enrichment outcome logs a
`FeedbackSourceEvent` with **`status="enriched"`** (message_id = conversation id,
feedback_id set when enriched). Rationale: the dedup filter only matches
`processed`/`pending` (`source_events.py:315`) — a `processed` row for a replied event
with message_id = conversation id would swallow a LATER `created` delivery
(out-of-order hazard); `enriched` cannot. `noop` outcomes log `ignored`.

**R4 — Re-analysis dispatch after commit.** The branch returns changed feedback ids;
`process_source_event` dispatches `reanalyze_feedback` for them **after** the core's
end-commit (`source_events.py:105`), alongside the existing cache invalidation —
mirroring the pull's post-commit dispatch (`intercom_sync.py:388 → 397-406`). Never
call `reanalyze_feedback` (which commits itself, `analysis.py:299`) inside the core
before the end-commit.

**R5 — Golden fixtures pin the real shapes.** Two new cross-service fixtures in
`worker-service/tests/fixtures/` — `intercom_webhook_reply_envelope.json` and
`intercom_webhook_rating_envelope.json` — conversation-wrapped per the real API
(`item.id` = conversation id; `conversation_parts.conversation_parts[]` with
`part_type: "comment"` + author; `conversation_rating`). Read by BOTH suites with the
existing raise-if-missing contract (worker: `test_intercom_envelope_seam.py:52-69`;
backend: `test_intercom.py:591-615`). Backend route tests for replied/rating gain the
full kwargs pins (external_event_id, event_data, provider_context — today only
`event_type` is asserted, test_intercom.py:534/:564).

**R6 — Tests.** Worker: end-to-end via the shared core (the
`test_intercom_envelope_seam.py` harness pattern — `_patch_db_session` +
`_no_op_side_effects` + direct `process_source_event`): created→replied→rating
sequence yields 1 item with enriched text + rating metadata; redelivery idempotent;
re-analysis dispatched once after commit (ordering test mirroring
`test_intercom_enrichment.py::test_dispatch_happens_after_commit`); no-item →
noop/ignored; out-of-order (reply before created) → noop, then created → item created
(dedup unaffected — the `enriched` status test); 429 → transient. Backend: route
kwargs pins + golden-fixture contract. All six one-item characterization tests
unchanged.

**R7 — Docs & tracking.** SELF_HOSTING honest-limits flip (:1956-1957 "still
dedup-inert" → real-time webhook enrichment; :1724-1725/:1752 claims become true;
webhook topic implications true); CHANGELOG correction entry (house correction
pattern, :383-386 style); DEV-TRACKING follow-up note (:518-522) → **FIXED** with a
shipped summary; the #16 planning PRD's "not fixed here" lines get a pointer (no
history editing).

### Should-have

- **S1 — Adapter part-shaped tests stay as-is** (the create-path extraction is
  untouched; the enrichment path uses `intercom_parts.py`, not the part-shaped
  `_extract_reply`/`_extract_rating`).

### Nice-to-have (deferrable)

- **N1 — Fix the inert trigger UI** (frontend `toggleTrigger` + backend
  `TriggerConfig` gaining the intercom keys). Separate concern — the enrichment
  bypasses triggers, so the UI fix is cosmetic; defer.

## Technical Considerations

- **Services:** worker-service (core branch + new service module + tests), backend-api
  (route test pins only), frontend-web: none. No migration, no new deps, no plan gate
  (`SELF_HOSTED=true`).
- **Import direction:** `source_events.py` lazily imports the new module inside the
  branch (house convention — `analysis.py:156`, `source_events.py:389`); the new module
  imports `intercom_parts.py` + `intercom_sync._enrich_conversation_replies` +
  `clients.intercom.get_conversation` lazily as needed. The import-sweep guard
  (`test_worker_import_sweep.py`) bans only backend-only paths — a plain lazy import,
  never a swallowed-`except` import.
- **The payload-first assumption is the one real API risk.** The "webhook payloads
  aligned with API responses" claim (Intercom v2.15+ serialization note) is the basis;
  the golden fixtures pin the shape, the `get_conversation` fallback covers payloads
  without parts, and a real-app smoke check is the final authority (note in docs).
- **Rating:** metadata-only (never in text, no email attribution) — the #16 semantics
  reused verbatim.
- **Never creates items** — the enrichment path is strictly merge-into-existing
  (D3 invariant).

## Risks & Open Questions

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Payload shape drift** (payloads without `conversation_parts`/with different keys) | Payload-first + `get_conversation` fallback; golden fixtures pin the assumed shape; smoke check noted |
| R2 | **Out-of-order delivery** (reply webhook before created) | No item → noop/ignored; `enriched` status cannot block the created path's dedup (pinned by a test) |
| R3 | **Mid-task commit hazard** (reanalysis commits itself) | Dispatch strictly after the core's end-commit; ordering test |
| R4 | **Trigger-bypass surprises** (events processed despite trigger config) | Enrichment is additive (merge into items the org already receives); never creates; documented in the PRD + changelog |
| R5 | **Duplicate re-analysis on concurrent reply floods** | Part_id idempotency + per-item merge → only genuinely new content triggers; `reanalyze_feedback` is the same bounded seam #16 uses |

**Open questions**
- **OQ1 — Trigger semantics confirmed?** *Enrichment bypasses trigger config (never
  gated); item creation stays trigger-gated.* Rationale above; the alternative (seed
  change) is impossible without an operable trigger UI.
- **OQ2 — `enriched` vs `processed` status** — `enriched` chosen (dedup-safety).
- **OQ3 — Backfill?** None — enrichment only for conversations that already have items
  (same no-backfill rule as the pull).

## Out of Scope

- **The inert trigger UI** (N1 — deferred; enrichment bypasses triggers so it's
  cosmetic).
- **Item creation from replied/rating events** (never — D3 invariant).
- **The pull path** (#16 — untouched).
- `intercom-oauth-path-retirement` (gated on evidence of use).
- No plan gate; no migration; no new dependencies; no analysis-quality claims.

## Honest limits (state in docs + changelog)

- Enrichment is **webhook-delivery-only** and applies to conversations whose items
  already exist — a reply on a conversation Rereflect never created stays unseen
  (same no-backfill rule as the pull).
- The payload-shape assumption (conversation-wrapped, API-aligned) is pinned by golden
  fixtures; payloads without parts fall back to a `GET /conversations/{id}` fetch.
- No analysis-quality claim: replies/ratings reach the item faster (webhook) or on the
  pull cycle; the full thread is scored either way.

## Self-critique (Phase 4)

- 🔴 **The payload-shape assumption is the whole ballgame** — the feature's value
  depends on real webhook payloads being conversation-wrapped with parts (or the
  fallback fetch working). The fixtures pin it; a real-app smoke check is noted as the
  final authority. Honest in the PRD, not assumed away.
- 🟡 **Trigger-bypass is a semantic change** an operator could notice (events processed
  "despite" config) — mitigated by the additive-only property and documented; the
  alternative (fixing the inert trigger UI first) is deferred deliberately.
- 🟡 **The `enriched` status is new vocabulary** in the event log — the plan must pin
  its meaning (never dedup-relevant, never blocks created) with tests, or future
  readers will treat it as processed.
- 🟢 Both swallow points are eliminated in one place; the one-item invariant, commit
  ordering, and idempotency all mirror shipped #16 semantics.

**The question I'd want answered before greenlighting:** if a webhook-wired install
already waits up to 15 minutes for pull content anyway, does real-time reply delivery
move the needle enough to justify the change — or is the honest fix simply to make the
webhook path not-lie (deliver what it promises) and let the pull stay the content
backbone? — The settings card instructs operators to subscribe all three topics; a
subscription that silently delivers nothing is the defect. Fix it.
