# Aspect: ingestion-core

**Slice:** The single, shared code path that turns a Zendesk ticket event into a deduped
`FeedbackItem`. Both entry points (pull, webhook) funnel through this.

## In scope
- `src/adapters/zendesk.py` — `ZendeskAdapter(BaseSourceAdapter)`:
  - `check_triggers(event_type, event_data, triggers)` — match configured triggers (new-ticket;
    keyword optional).
  - `extract_content(event_data, field_mapping)` → `{"text": subject + "\n\n" + description,
    "metadata": {subdomain, ticket_id, status, requester_email, tags, ...}}`.
  - `get_external_ids(event_data)` → `(str(ticket_id), str(ticket_id))` — **dedup key = ticket id**
    (one feedback per ticket).
  - `fetch_context(event_data, access_token, field_mapping)` — optional enrichment
    (`GET /api/v2/tickets/{id}` / requester) via the stored token when the payload is thin.
- Register in `src/adapters/__init__.py` `get_adapter` dict + `__all__`: `"zendesk": ZendeskAdapter`.
- `src/tasks/source_events.py::_find_matching_sources` — add `elif source_type == "zendesk":`
  matching `provider_context["subdomain"]` against the org's `zendesk_integrations.subdomain`
  (→ its `FeedbackSource`), mirroring the Intercom `workspace_id` block.
- Ensure `customer_email` is set from requester email on the created `FeedbackItem` (via
  `extract_content` metadata → creation path).

## Out of scope
- The pull task and the webhook route (they call this core) — separate aspects.
- Per-comment granularity.

## Acceptance criteria (mirror `test_intercom_adapter.py`)
- `check_triggers` matches new-ticket / keyword; returns `None` on no match.
- `extract_content` builds text from subject+description; strips HTML; handles missing description.
- `get_external_ids` returns ticket id as the message/dedup id.
- `fetch_context` patched httpx: empty without token, success path, graceful API-error handling.
- `get_adapter("zendesk")` returns `ZendeskAdapter`.
- Feeding a synthesized event through `process_source_event` creates exactly one `FeedbackItem`
  with `source="zendesk"`, `source_external_id=ticket_id`, `customer_email=requester`; a second
  identical event is deduped via `FeedbackSourceEvent`.

## Dependencies / sequencing
- Depends on **backend-connection** (source-type reg, subdomain on the integration).
- Blocks **ingestion-pull** and **ingestion-webhook**.
