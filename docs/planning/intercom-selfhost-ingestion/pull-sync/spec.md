# Aspect Spec — `pull-sync`

**Feature:** `intercom-selfhost-ingestion` · **PRD:** `../prd.md` (R5, R7, S2) · **Date:** 2026-08-01
**Depends on:** `tenancy-discriminator` (resolution must be correct before anything is pulled)

## Problem slice

The originating user ask was for feedback to "flow in automatically instead of pasting
tickets manually" — the **pull** path. Intercom had none: `IntercomConnector.fetch_new_items`
was a stub returning `[]`.

## O2, resolved (2026-08-01)

`POST https://api.intercom.io/conversations/search`, body
`{"query": {"field": "updated_at", "operator": ">=", "value": <unix>},
  "pagination": {"per_page": <=150, "starting_after": <cursor>},
  "sort": {"field": "updated_at", "order": "ascending"}}`.
Next cursor at `pages.next.starting_after`.

## The one place this must NOT copy Zendesk

Zendesk's incremental endpoint returns an authoritative `end_time` watermark. Intercom has
no equivalent, so the cursor is **derived** from the maximum `updated_at` observed. Two
consequences, both deliberate:

- the query uses **`>=`, not `>`** — a strict `>` would silently drop a conversation sharing
  the watermark second but returned after the page cap. `>=` cannot lose one; it re-fetches
  the boundary conversation, which `FeedbackSourceEvent` dedup discards;
- the cursor **only moves forward**, and an empty page leaves it untouched rather than
  advancing to "now", which would skip anything created mid-request.

## In scope

`clients/intercom.py` (search + pagination + error taxonomy + normalization),
`tasks/intercom_sync.py` (`_sync_org` core, per-org task, fan-out), 15-minute beat, and R7
`customer_email`.

**Normalization belongs in the client.** The adapter's contract is the *webhook* envelope
(`conversation_message`); search returns the same content under `source`. Mapping it in the
client keeps one extraction path and one dedup path for pull and webhook alike — teaching
the adapter a second shape would fork exactly what the shared core exists to unify.

**R7 changes the adapter, deliberately**, so the webhook path benefits too. `customer_email`
is only set when the author is a customer (`user`/`contact`/`lead`); an `admin`/`bot` author
yields none, because attributing a teammate's reply to a customer profile would corrupt that
customer's health and churn signals.

## Acceptance criteria

| # | Criterion |
|---|---|
| P1 | A conversation becomes a `FeedbackItem` with the message body as text |
| P2 | `customer_email` populated from a customer author; never from staff |
| P3 | Cursor = `last_synced_at ?? connected_at`, never epoch |
| P4 | Cursor advances to max `updated_at`, never backwards, untouched on an empty page |
| P5 | Pagination followed via `starting_after`, capped at 20 pages/run with a logged warning |
| P6 | Re-fetch of the boundary conversation deduplicates |
| P7 | No matching source is a logged no-op, not a crash |
| P8 | Auth failure records `last_sync_status`/`last_error` and does **not** deactivate |
| P9 | The access token is never logged |
| P10 | Both tasks registered and on the beat schedule |

## Honest limits

Up to 15 minutes of latency. Only the first message of a conversation is ingested (replies
are a webhook-only path today). The 20-page cap means a very large backlog drains over
several runs rather than one. No claim is made about analysis quality — this changes whether
feedback arrives, nothing else.
