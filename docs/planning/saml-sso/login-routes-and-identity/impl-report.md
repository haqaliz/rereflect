# Impl Report — `login-routes-and-identity` (SAML 2.0 SSO, aspect 4)

**Branch:** `feat/saml-sso` · **Date:** 2026-07-18 · **Method:** strict TDD (RED → verify-fail → GREEN)

## Status: DONE — green

Two routes wired into `src/api/routes/auth.py` (riding the existing `auth.router`, prefix
`/api/v1/auth`), plus the reused OIDC-shaped identity-resolution block. 27 new tests, all green;
no regression across the SSO + auth suites (163 passed).

## Commits (phase-sized, TDD RED→GREEN)

| SHA | Message |
|---|---|
| `9ec9e0c` | test(saml-sso): SP-initiated /saml/login start route tests (Phase A) |
| `e5325ec` | feat(saml-sso): GET /saml/login SP-initiated start route |
| `388b928` | test(saml-sso): ACS validation, replay, identity & security tests (Phases B-E) |
| `835409f` | feat(saml-sso): POST /saml/callback ACS route + identity resolution |

## Files changed

- `services/backend-api/src/api/routes/auth.py` — imports (`Form`, `SamlProvider`,
  `SamlValidationError`, `SAML_ACS_PATH`, `register_request`, `consume_request`, `ConsumeOutcome`);
  `SAML_SSO_ERROR_CODES`; `saml_login` (GET); `_extract_saml_in_response_to` helper; `saml_callback`
  (POST ACS) + identity resolution.
- `services/backend-api/tests/test_saml_login.py` — new, 27 tests mirroring `test_oidc_login.py`.

No other files touched. No migrations (schema owned by aspect 2). `alembic heads` = single head
(`q1r2s3t4u5v6`). Router wiring unchanged — `main.py` already includes `auth.router`; the
`test_login_route_is_registered_not_404` test proves the new routes resolve (not 404).

## Seam reconciliation (plan §9 — the interface DID drift from the plan's assumption)

The plan (§2.1) *assumed* the provider would return `ValidatedAssertion.in_response_to` for a
route-owned consume. The **actual** aspect-3 provider instead:
- `ValidatedAssertion(subject: str, email, attributes)` — **no `in_response_to` field**, and
  `subject` is already non-null (provider rejects null NameID).
- `validate_response(b64, *, expected_in_response_to, acs_url)` — takes the expected value as a
  **required kwarg** (it does not hand one back).
- Replay store helpers are `register_request(db, *, request_id, organization_id, ttl_seconds=...)`
  and `consume_request(db, *, request_id) -> ConsumeOutcome` (str enum `ok/replay/unsolicited/expired`).

Per the plan's directive ("adapt the import in auth.py — do not redefine the artifact"), the ACS
sources the `InResponseTo` itself via a small route-level helper `_extract_saml_in_response_to`
(reads the `@InResponseTo` attribute off the raw Response envelope using OneLogin's XML utils),
passes it as `expected_in_response_to` (so the library confirms consistency), then consumes it.
This is **XSW-safe**: `InResponseTo` is a non-identity value used ONLY as a replay-store lookup key
(a forged value resolves to `unsolicited`/`replay`); identity (`subject`/`email`) is read solely
from the provider's validated `ValidatedAssertion`. The consume runs strictly AFTER crypto
validation. No sibling model/provider was redefined.

The identity-link `auth_provider` promotion set is `("email", "google", "oidc") -> "both"` (SAML
adds `oidc` to the OIDC set, per plan §5); JIT users get `auth_provider="saml"`.

## Test commands + output

Aspect suite:
```
$ python -m pytest tests/test_saml_login.py -q
27 passed
```

Regression (SSO + auth; scoped to avoid the known full-suite segfault in test_report_ws.py):
```
$ python -m pytest tests/test_oidc_login.py tests/test_auth.py tests/test_google_auth.py \
    tests/test_saml_provider.py tests/test_saml_replay.py tests/test_saml_config.py \
    tests/test_saml_deps.py tests/test_oidc_config.py tests/test_oidc_provider.py -q
163 passed
```

RED evidence captured during TDD: Phase A tests failed with `404`/`405` (route absent) before
`saml_login` landed; Phase B-E tests failed with `405 Method Not Allowed` (KeyError on the missing
`location` header) before `saml_callback` landed. Both went fully green after the respective feat
commit.

## How the load-bearing security properties are proven

**ACS never 500s / never leaks a stack trace** (carried note (a)):
- `saml_callback` wraps `validate_response` so `SamlValidationError -> exc.code`, `SsrfError ->
  config`, and **any other exception -> generic `?sso_error=assertion`**. An outer
  `try/except Exception` around the whole handler is the belt-and-braces guard (covers DB errors on
  consume/commit too).
- `test_unexpected_provider_exception_is_sso_error_not_500` stubs `validate_response` to raise a bare
  `RuntimeError` (xmlsec-segfault surrogate) and asserts a `302 …?sso_error=assertion`, not a 500,
  and zero users created.

**Forged / unsigned POST rejected** (gap 2, proves auth-exempt-but-safe):
- `test_forged_unsigned_post_rejected` POSTs a real garbage `SAMLResponse` body with the provider
  modelling an unsigned assertion (`SamlValidationError("signature")`). Asserts `?sso_error=signature`,
  no user created/linked, AND — proving the validate-before-consume ordering — a pre-seeded
  legitimate pending `req-1` is **still claimable** (`consume_request(...) == OK`) because the forged
  POST failed validation before reaching the consume. The route carries the anti-forgery rationale as
  a docstring: cross-site POST means no SameSite cookie is possible; trust = XML signature +
  one-time InResponseTo consume; RelayState is a bare HMAC nonce hash with no identity/trust.

**Missing-subject no-takeover**:
- `test_missing_subject_no_takeover` seeds an org owner + a valid pending request, then returns an
  assertion with `subject=None`. Asserts `?sso_error=token`, no `#token=` in the redirect, user count
  unchanged, and the owner's `saml_subject` still `None`. The null-subject guard runs before any
  `User.saml_subject == subject` query, so it never degrades to `WHERE saml_subject IS NULL`.

**Other guards under test**: replay/unsolicited/expired against the REAL SQLite store; empty
allowlist denies all; domain gate; case-insensitive email link (no duplicate row); returning-by-
subject with a changed email; success fragment on the fixed `http://localhost:3000/login/callback`
(no `?token=`/`&token=`); JWT claims decode to the resolved user (org scoping). Every error-path
test asserts `db.query(User).count()` is unchanged.

## Concerns / follow-ups

- `_extract_saml_in_response_to` parses the raw Response envelope for `@InResponseTo` before crypto
  validation. This is safe (non-identity key; consume gated behind validation), but a cleaner long-
  term seam would be for the provider to surface the validated `in_response_to` on
  `ValidatedAssertion` so the route never touches raw XML. Flag for the provider aspect owner.
- The optional true end-to-end test with a real signed `SAMLResponse` fixture (plan §10) is not
  included here — it depends on aspect-3's signed-assertion fixtures and an `xmlsec`-available
  marker. This aspect's tests stub the provider at the route boundary by design.
