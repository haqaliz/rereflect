# Aspect Spec — salesforce-write-client

**Feature:** `salesforce-crm-writeback` · **Aspect:** `salesforce-write-client` · **Deps:** none

## Problem slice / outcome

The shipped Salesforce client is query/read-only, and there is no field-validation service. Provide
(a) a client method to PATCH a Contact field and (b) a describe-based validation service, so the
config-api can validate a field before enabling and the push task can write a score.

## In-scope

1. **Client PATCH (`services/worker-service/src/clients/salesforce.py`)** —
   `update_contact_field(self, contact_id: str, field_name: str, value) -> None`:
   - `PATCH {instance_url}/services/data/{api_version}/sobjects/Contact/{contact_id}` with JSON body
     `{field_name: value}` where **value is the raw number** (do NOT stringify — unlike HubSpot's
     `_format_number`).
   - Validate `contact_id` with the existing `_validate_sf_id` / `_SFID_RE`.
   - Refresh access token via existing `_refresh` (context-manager `__enter__`).
   - Error mapping mirroring the read methods + `hubspot.py` write semantics: 429/5xx →
     `SalesforceTransientError`; 401 → refresh-once-then-retry (reuse existing 401 handling) else
     `SalesforceAuthError`; 403 → a scope error (add `SalesforceScopeError` or reuse an existing class
     mapped to `missing_write_scope`); 404 → not-found (mapped to `contact_not_found`). 2xx (SF
     returns 204 on update) → success.
2. **Client describe (`salesforce.py`)** —
   `describe_object(self, sobject: str = "Contact") -> dict` (or a narrower
   `get_field_def(sobject, field_name)`): `GET .../sobjects/{sobject}/describe`, return parsed field
   metadata. Reuse token refresh + transient/auth mapping.
3. **Validation service (`services/backend-api/src/services/salesforce_writeback_validation.py`)** —
   `validate_writeback_field(refresh_token, instance_url, field_name) -> Tuple[bool, Optional[str]]`
   mirroring `hubspot_writeback_validation.py` contract (never raises; returns `(bool, reason)`):
   - Obtain an access token server-side (reuse `_refresh_access_token` in
     `routes/salesforce_integration.py:252`, or a shared helper).
   - Call the sObject describe REST endpoint for `Contact`, find `field_name` in `fields`.
   - Reason codes: `field_not_found` (absent), `missing_write_scope` (403 on describe/refresh),
     `wrong_type` (field `updateable != true` OR `type` not in
     `{double, int, currency, percent}`), `validation_error` (other HTTP/network).
   - Success → `(True, None)`.

## Out-of-scope

- Routes (config-api aspect), the Celery task (push-task aspect), any model change.

## Acceptance criteria (testable)

- `test_salesforce_client_writeback.py` (new): `update_contact_field` issues the PATCH to the correct
  URL with a raw-number JSON body; 204→success; 429→`SalesforceTransientError`; 403→scope error;
  404→not-found; invalid id→rejected before any HTTP call. `describe_object` returns parsed fields.
  (httpx mocked; no live Salesforce.)
- `test_salesforce_writeback_validation.py` (new): each reason code path
  (`field_not_found`/`missing_write_scope`/`wrong_type` for non-updateable and for text-type/
  `validation_error`) plus the happy path `(True, None)`. Never raises.
- Worker tests + backend tests green; no read-path regression.

## Dependencies / sequencing

Independent of `model-migrations` (touches no columns). Can run in parallel with aspect 1. Its
validation service is a prerequisite for `writeback-config-api`; its client PATCH is a prerequisite for
`push-task-trigger`.

## Open questions / risks

- Whether a `SalesforceScopeError` class exists or should be added — mirror the read client's error
  taxonomy (`SalesforceTransientError`/`SalesforceAuthError`/`SalesforceQueryError` at
  `salesforce.py:46-60`); add a scope class if none maps to 403-on-write.
- API version constant: reuse the client's `api_version` (`v60.0`) for the URL.
