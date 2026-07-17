# Aspect Spec — provider-and-replay-store

**Parent PRD:** `../prd.md` · **Aspect:** `provider-and-replay-store` · **Sequence:** 3

## Problem slice & outcome

A pure, testable service that (a) builds an SP-initiated AuthnRequest and (b) validates a returned SAML
Response/Assertion to a trusted identity — plus the server-side replay store that makes the ACS safe.
No FastAPI routes here (that's the next aspect); this is the crypto/validation core + its store.

## In scope

- **`src/services/saml_provider.py`** — `class SamlProvider` built `from_config(saml_config)`; wraps
  `python3-saml` (build the OneLogin settings dict from our config + SP entity id/ACS from `BACKEND_URL`).
  - `build_authn_request(relay_state) -> (redirect_url, request_id)`: HTTP-Redirect binding, **unsigned**
    request; returns the IdP redirect URL and the generated `ID` for `InResponseTo` tracking.
  - `validate_response(saml_response_b64, *, expected_in_response_to, acs_url) -> ValidatedAssertion`:
    delegate signature + condition validation to `python3-saml` (do NOT post-process the XML ourselves).
    Enforce: **assertion is signed** (reject unsigned/response-only-signed per policy — require signed
    assertion), signature verifies against `idp_x509_cert`, `Audience`==SP entity id, `Destination`/
    `Recipient`==ACS URL, `NotBefore`/`NotOnOrAfter` within **±60s** skew, `Issuer`==`idp_entity_id`,
    `InResponseTo`==expected. Raise a typed `SamlValidationError(code=...)` mapping to `sso_error` codes
    (`signature|assertion|audience|recipient|expired|unsolicited|replay`).
  - Extract `ValidatedAssertion{subject, email, attributes}`: `subject` = NameID; `email` = NameID when
    `Format=emailAddress`, else the configured `email_attribute`, else default chain
    `email` → `urn:oid:0.9.2342.19200300.100.1.3` → `http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress`.
    **Keep the null-subject rejection.**
  - **SSRF-gate** the IdP SSO URL via `_require_https_public`/`assert_host_not_ssrf` (reuse).
- **Replay store (gap 1 — explicit state machine).** New model `src/models/saml_auth_request.py`
  (`saml_auth_requests`): `request_id` (PK/unique), `organization_id`, `created_at`, `expires_at`
  (`NotOnOrAfter`-derived / issue time + TTL), `consumed_at` nullable. State machine:
  | State | Set when | ACS outcome |
  |---|---|---|
  | **pending** | row inserted at `/saml/login` (issue) | — |
  | **consumed** | ACS marks `consumed_at` via conditional UPDATE on first valid use | first use OK |
  | replay | ACS sees `InResponseTo` already `consumed_at` | → `replay` |
  | unsolicited | ACS sees `InResponseTo` with **no** row | → `unsolicited` |
  | expired | `expires_at < now` | → `expired`/`unsolicited` |
  - Conditional `UPDATE ... WHERE consumed_at IS NULL` guarantees one-time use race-safely (poll/dup POST
    can't double-consume). Opportunistic cleanup: delete expired rows on insert (bounded), no Celery beat.
  - (Optional additionally track consumed assertion IDs if the IdP reuses request-less flows — not in
    slice 1 since SP-initiated always has `InResponseTo`.)
- **Tests** `tests/test_saml_provider.py`: valid assertion passes; unsigned/wrong-cert/**XSW**
  (signature-wrapping) rejected; wrong audience/recipient/expired/not-yet-valid/wrong-issuer/mismatched
  `InResponseTo` rejected; SSRF private-IP SSO URL rejected; email extraction from NameID vs attribute vs
  default chain; null-subject rejected. `tests/test_saml_replay.py`: pending→consumed happy path;
  second use → replay; unknown id → unsolicited; expired → rejected; concurrent double-consume → exactly
  one wins.

## Out of scope

- The FastAPI `/saml/login` and `/saml/callback` routes (next aspect wires this service in).
- IdP-initiated (no `InResponseTo`), SLO, encrypted assertions.

## Acceptance criteria (testable)

- Every rejection path above is covered and red-before-green.
- XSW and unsigned-assertion rejection explicitly tested (R2).
- Replay store enforces exactly-once consume under concurrency.

## Dependencies & sequencing

- **Depends on:** `deps-and-docker`, `config-model-and-crud` (reads `saml_configs`), `utils/ssrf`.
- **Blocks:** `login-routes-and-identity`.

## Open questions / risks

- **R2:** trust `python3-saml`'s validated API surface; assert we read the *validated* assertion, never
  re-parse raw XML for the subject/email (that's how XSW slips in).
- **R3:** replay store DB-backed (chosen) vs Redis — revisit only if a perf need appears.
- Fixture generation: signed SAML responses for tests (use `python3-saml` test utils / a Keycloak-captured
  sample / a locally-generated signed assertion with a throwaway key).
