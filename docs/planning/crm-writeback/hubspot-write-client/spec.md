# Aspect: hubspot-write-client (worker)

**Slice of:** crm-writeback PRD · **Service:** `services/worker-service`
**Depends on:** nothing (pure client). **Blocks:** writeback-task-trigger.

## Problem slice / outcome

The worker's `HubSpotClient` (`src/clients/hubspot.py`) is read-only (GET). Add the outbound
write surface so the push task can set a contact property and validate the target field.

## In scope

- `update_contact_property(contact_id, property_name, value) -> None` → `PATCH /crm/v3/objects/contacts/{contact_id}` with body `{"properties": {property_name: value}}`, Bearer auth, reusing the existing httpx client + `HubSpotTransientError` on 429/5xx.
- `get_contact_property_def(name) -> dict | None` → `GET /crm/v3/properties/contacts/{name}`; returns the property definition or `None` on 404. Used to validate existence **and type** (must be a `number` field) and writability (not `calculated`/read-only).
- Map HubSpot error bodies to the existing transient/permanent split: 404 (contact or property) and 403 (scope) are **permanent** (surface to caller), 429/5xx are **transient** (raise `HubSpotTransientError`).

## Out of scope

- Company/account properties; batch PATCH; auto-creating properties; any Salesforce client.

## Acceptance criteria (testable)

- Unit test (mocked httpx): `update_contact_property` issues the correct PATCH URL + body + Bearer header.
- 429/5xx → raises `HubSpotTransientError`; 403 → raises a permanent scope error; 404 → permanent (distinguish contact-404 vs property-404 where the body allows).
- `get_contact_property_def` returns the def for an existing number property, `None` for 404, and exposes enough for the caller to reject a non-`number` / read-only field.

## Notes

Mirror the exact Bearer/httpx/timeout pattern already in `HubSpotClient`; add methods, do not restructure the class.
