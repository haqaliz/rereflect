# Aspect Spec — login-routes-and-identity

**Parent PRD:** `../prd.md` · **Aspect:** `login-routes-and-identity` · **Sequence:** 4

## Problem slice & outcome

The end-to-end SP-initiated login: start → IdP → ACS → validated assertion → resolved user → JWT →
`/login/callback#token=`. Reuses the OIDC identity-resolution block verbatim in shape.

## In scope (in `src/api/routes/auth.py`, mirroring the OIDC routes)

- Constants: `SAML_ACS_PATH = "/api/v1/auth/saml/callback"`, SAML `sso_error` codes.
- **`GET /api/v1/auth/saml/login`** — load the enabled SAML config (302 `?sso_error=disabled` if none);
  `SamlProvider.from_config`; `build_authn_request(relay_state=sign_state(hash_nonce(token_urlsafe)))`;
  persist the returned `request_id` (pending) via the replay store; 302 to the IdP redirect URL. Failures
  (SsrfError/ValueError) → 302 `?sso_error=config`.
- **`POST /api/v1/auth/saml/callback` (ACS)** — **auth-exempt, unauthenticated** form-POST consuming
  `SAMLResponse` + `RelayState`. Anti-forgery rationale (gap 2, state it in code + a test): the trust
  controls are the **signed assertion** + the **`InResponseTo` one-time consume**, not a session cookie;
  `RelayState` is HMAC-signed and carries only a nonce hash (no identity/trust). Steps: verify `RelayState`
  HMAC/TTL; `validate_response(..., expected_in_response_to=?, acs_url={BACKEND_URL}{SAML_ACS_PATH})`;
  conditional-consume the `InResponseTo` (replay/unsolicited → error redirect); then **identity resolution**.
- **Identity resolution (reuse OIDC L492-552 shape):**
  ```
  email = assertion.email; if not email -> sso_error=unverified
  email = email.lower()
  subject = assertion.subject; if not subject -> sso_error=token   # keep null-subject rejection
  domain gate: email domain in config.allowed_email_domains (empty = deny-all) else sso_error=domain
  user = User where saml_subject == subject
  if not user: user = User where lower(email) == email  # case-insensitive link
     if user: user.saml_subject = subject; auth_provider email/google/oidc -> add "saml"/"both"; commit
     else: JIT User(email, saml_subject=subject, auth_provider="saml", org=config.org, role="member")
  access_token = create_access_token({user_id, organization_id, role})
  302 -> {FRONTEND_URL}/login/callback#token={access_token}
  ```
  (No `email_verified` field in SAML — a validly-signed assertion's email is trusted; documented.)
- **Error redirect helper** → `{FRONTEND_URL}/login?sso_error=<code>` (fixed FRONTEND_URL, open-redirect
  guard) for all SAML codes.
- **Router registration** in `src/api/main.py` (SAML routes ride `auth.router`; `saml_config` router
  included like `oidc_config`).
- **Tests** `tests/test_saml_login.py` mirroring `test_oidc_login.py`: start redirect + no-config +
  disabled; ACS denied/malformed/invalid-signature/wrong-audience/expired/replay/unsolicited/unverified-
  email/domain-denied/empty-allowlist-denies-all; JIT-new-member; link-existing-password-user;
  **case-insensitive email link**; returning-by-subject with changed email; success fragment on fixed
  FRONTEND_URL; **missing-subject no-takeover**; forged/unsigned POST rejected (gap 2).

## Out of scope

- Provider crypto internals (previous aspect); frontend (next aspect); SP metadata export (nice-to-have).

## Acceptance criteria (testable)

- Full happy path (start→ACS→token) green against a signed test assertion.
- Every `sso_error` branch tested; no-takeover cases pass; unauthenticated forged POST rejected.
- No regression to OIDC/password/Google login routes (existing suites green).

## Dependencies & sequencing

- **Depends on:** `provider-and-replay-store`, `config-model-and-crud`. Reuses `auth.create_access_token`,
  `_oidc_state` helpers, `_frontend_url`/`_backend_url`.
- **Blocks:** `frontend-saml-ui` (API contract), `docs-and-dev-idp`.

## Open questions / risks

- Reuse `/login/callback` (already public in both frontend allowlists) — do NOT introduce a new callback path.
