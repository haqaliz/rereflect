# Aspect Spec — `oidc-login-flow`

**Feature:** `oidc-sso` · **Aspect:** `oidc-login-flow` · **PRD:** `../prd.md` (M5-M10, M12) · **Date:** 2026-07-17
**Status:** Draft → ready to plan · **THE SECURITY CORE. Highest-risk aspect.**

---

## Problem slice & user outcome

Turn the stored `OidcConfig` into a working login: a user clicks "Sign in with SSO", is redirected to
the operator's IdP, authenticates, and returns authenticated to Rereflect — provisioned (JIT) or linked,
with an internal JWT. All existing auth paths remain untouched (additive only).

## The load-bearing divergence from the Salesforce precedent

Salesforce's OAuth (`salesforce_integration.py`) runs with an **authenticated** user — its signed
`state` carries `org_id`+`user_id`. **OIDC login has NO prior session.** Therefore:
- The signed `state` carries **only** a CSRF nonce hash + a PKCE/nonce binding — never a user/org id.
- **Identity is resolved from the validated ID token**, not from state.
- The callback returns a **token to an unauthenticated browser** — via a **URL fragment** redirect.
Everything else (HMAC-signed stateless state, HttpOnly nonce cookie via `_hash_nonce`/`_sign_state`/
`_verify_state` + `hmac.compare_digest`, `RedirectResponse`) mirrors Salesforce directly.

## In-scope (PRD M5-M10, M12)

1. **Dependency + schema (M7):** add `authlib` to `requirements.txt` (pinned). Add `users.oidc_sub`
   (String(255), unique, nullable, indexed) + allow `auth_provider="oidc"`. Additive migration off head
   `c9d0e1f2a3b4`, verified on **scratch Postgres** (never `-x sqlalchemy.url`, never dev DB).
2. **OIDC provider service (M6, M10):** discovery (`GET {issuer}/.well-known/openid-configuration`),
   JWKS fetch, **both cached with a bounded TTL** (uncached-per-login is a DoS amplifier). **SSRF gate
   on the issuer host** — resolve + reject loopback/private/link-local before any fetch. ID-token
   validation: signature vs JWKS, `iss` == configured issuer, `aud` == client_id, `exp`/`nbf`, and
   `nonce` == the value bound in `state`. Use `authlib` for token validation; do NOT hand-roll JWKS.
3. **`GET /auth/oidc/start` (M5):** load the single enabled config; build the authorize URL from
   discovery with `response_type=code`, `scope=openid email profile`, **PKCE** (S256), a random
   `nonce`, and a signed `state`; set the nonce/verifier binding in an **HttpOnly, Secure, callback-path
   -scoped cookie**; `RedirectResponse` to the IdP. If SSO disabled → 404/redirect to login with error.
4. **`GET /auth/oidc/callback` (M6-M9, M12):** the integration —
   a. verify `state` (HMAC) + the nonce cookie (`hmac.compare_digest`); reject on mismatch → redirect
      to frontend login with a generic error (never leak internals).
   b. exchange `code` (+ PKCE verifier) server-side for tokens.
   c. validate the ID token (service, item 2). **Reject unless `email_verified: true`** (M9/D6) → 403.
   d. **M12 domain allowlist:** the email's domain must be in `allowed_email_domains`; **empty list =
      deny-all** → 403, no user created.
   e. resolve identity: match `oidc_sub` first, then email. Existing password/Google user by email →
      **link** (set `oidc_sub`, `auth_provider="both"`) only under (c)+(d). Unknown → **JIT provision**
      (M8): new `User` in the enabled config's org, `role="member"`, `auth_provider="oidc"`.
   f. mint the internal JWT (`create_access_token`, claim shape `{user_id, organization_id, role}`),
      `RedirectResponse` to `{FRONTEND_URL}/login/callback#token=<jwt>` (fragment, never query).

## Out-of-scope

- Frontend button / callback page / settings UI (`oidc-frontend`).
- Docs / Keycloak compose (`oidc-docs-and-compose`).
- "Require SSO" / disabling passwords (PRD out-of-scope).
- Migrating the two existing `_assert_host_not_ssrf` copies (jira/zendesk) — see SSRF decision below.
- Refactoring the Google path onto this seam.

## SSRF helper decision (resolves PRD S-1)

Create **`src/utils/ssrf.py`** with one shared `assert_host_not_ssrf(host)` (lifted from the jira/zendesk
copies, same semantics) + its own unit tests. **OIDC uses the shared helper.** The two existing copies
(`jira_integration.py:195`, `zendesk_integration.py:185`) are **left untouched** this PR — migrating
shipped integrations from an auth PR is scope creep; their consolidation onto the new helper is a
**named follow-up** (`docs/planning/oidc-sso/oidc-login-flow/` will note it). Net: no *new* duplication —
OIDC gets the clean shared version; we don't touch shipped code.

## Acceptance criteria (testable — mock the IdP via httpx, no live server)

- **AC1** — `users.oidc_sub` migration applies+reverses on scratch Postgres; single head preserved.
- **AC2 (SSRF)** — an issuer host resolving to loopback/private/link-local → rejected before any HTTP
  fetch; `assert_host_not_ssrf` unit-tested for public-pass / private-reject.
- **AC3 (ID-token validation)** — wrong `iss`, wrong `aud`, expired, bad signature, and **mismatched
  `nonce`** each rejected. A valid token passes.
- **AC4 (email_verified)** — `email_verified:false`/absent → 403, no user created, no link.
- **AC5 (M12 allowlist)** — email domain not in `allowed_email_domains` → 403, no user created; **empty
  list → all rejected**; in-list domain → provisioned.
- **AC6 (JIT)** — unknown in-list verified identity → new `User`, org = enabled config's org,
  `role="member"`, `auth_provider="oidc"`, JWT minted.
- **AC7 (link)** — existing password user, same verified in-list email → `oidc_sub` set,
  `auth_provider="both"`, same `User` row, no duplicate.
- **AC8 (returning)** — same `oidc_sub`, changed email → matched by sub, same `User`.
- **AC9 (CSRF)** — missing/mismatched state or nonce cookie → rejected, generic error redirect, no token.
- **AC10 (fragment)** — success redirects to `{FRONTEND_URL}/login/callback#token=…` (fragment, not query).
- **AC11 (additive)** — `test_auth.py` + `test_google_auth.py` + `test_oidc_config.py` still green.
- **AC12 (caching)** — discovery + JWKS fetched at most once per TTL (assert the HTTP mock call count).

## Dependencies & sequencing

- **Blocked by:** `oidc-config` (done — model, status, CRUD). **Blocks:** `oidc-frontend`.
- Internal order: dep+schema → provider service → `/start` → `/callback` (callback integrates all).

## Risks

- **R1 (crypto correctness).** ID-token validation is where auth bugs live. Mitigation: use `authlib`'s
  validated JWT claims; test every rejection branch (AC3); do not hand-roll JWKS parsing.
- **R2 (TOCTOU on SSRF).** Resolve-then-fetch has a re-resolution gap (inherited from the existing
  copies). Accept for parity this PR; note as debt. Do not claim it's closed.
- **R3 (open redirect).** The post-login redirect target must be the **configured `FRONTEND_URL`**, never
  a value derived from the request/IdP. Assert the redirect base is fixed.
- **R4 (token in fragment).** Best available given `localStorage` auth (PRD R6); the callback page
  (`oidc-frontend`) consumes it. Fragment, not query — never logged/referred.
