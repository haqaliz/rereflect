# Phase 0 dig — webhook-realtime event shape (GO)

**Recommendation: GO** (poll-first, webhook additive). R5 resolves to documented operator config, not an unknowable Zendesk internal.

## Receiver (existing)
- Route `POST /api/v1/webhooks/zendesk/events` → `services/backend-api/src/api/routes/source_webhooks.py:405-535` (`handle_zendesk_webhook`).
- HMAC `_verify_zendesk_signature` (`:372-392`): `base64(HMAC_SHA256(secret, timestamp + raw_body))`, header `X-Zendesk-Webhook-Signature` + `-Timestamp`. Fail-closed on missing secret; integration with `webhook_secret is None` → 401 (`:451-453`). `hmac.compare_digest`.
- Body read raw (`:418`) before `json.loads` (`:421`); non-dict/invalid → 400.
- Org resolved by **subdomain** (`_resolve_zendesk_subdomain` `:335-369`: payload.subdomain → ticket.url host → `X-Zendesk-Subdomain` header) + `is_active`; secret decrypted from that row.

## Payload is OPERATOR-AUTHORED (Liquid template), not Zendesk-native
- Receiver **hardcodes** `event_type="ticket.created"` (`:528`); the ONLY discriminator today is "does `payload.ticket.id` exist" (`:485-489`).
- Canonical shape (test fixture `tests/test_zendesk_webhook.py:53-64`): `{"subdomain":"acmeco","ticket":{"id":35436,...,"status":"new","requester_email":...}}`. **`ticket.status` is already present** in the body the operator controls (adapter reads it at `worker-service/src/adapters/zendesk.py:92`).
- ⇒ For status events, the operator's UPDATE trigger must (a) fire on ticket update/status change and (b) include a literal discriminator field, e.g. `"event":"ticket.status_changed"`, so the status branch can't reach the ingestion/dedup path. Both are one-line operator config → document in `docs/SELF_HOSTING.md` (Phase 3).

## Reuse seams (all present)
- `services/backend-api/src/services/zendesk_status_core.py` — `resolve_target_status`, `decide_update`, `DEFAULT_ZENDESK_MAP`.
- `FeedbackZendeskSync` sidecar — `services/backend-api/src/models/feedback_zendesk_sync.py`.
- `workflow_service.apply_status_change(db, feedbacks, new_status, *, organization_id, actor_id=None, actor_label, resolution_note=None)` (`:15-50`) — emits `status_changed` via `create_workflow_event` (skips no-ops).

## THREE design tasks for Phase 1/2 (baked into implementer dispatch)
1. **source tag not wired today.** `apply_status_change` only persists metadata when `resolution_note and new_status=="resolved"`; `actor_label` is not persisted (docstring `:32-33`). Must thread a `metadata={"source":"zendesk",...}` dict through to `create_workflow_event` (which already accepts `metadata`, `:89,99`) to meet the AC.
2. **race-safe guard.** `apply_status_change` is a plain read-modify-write (no conditional UPDATE). For the poll↔webhook single-event idempotency AC, the backend `reconcile_ticket` must replicate the worker's conditional `UPDATE ... WHERE workflow_status=<old>` → 0-rows→no event (pattern at `worker-service/src/tasks/zendesk_status_sync.py`). Sidecar change-gate alone doesn't close the two-writers window across services.
3. **anti-spoof branch.** Branch explicitly on the new discriminator field; keep ingestion (`ticket.created`) path byte-identical.

## Tests
- `services/backend-api/tests/test_zendesk_webhook.py`: `_make_zendesk_signature(body,ts,secret)` helper; posts raw `content=` bytes; `zendesk_integration`/`zendesk_integration_no_secret` fixtures; patches `queue_source_event`. Extends cleanly to status-event tests.
