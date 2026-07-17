# Aspect Spec — docs-and-dev-idp

**Parent PRD:** `../prd.md` · **Aspect:** `docs-and-dev-idp` · **Sequence:** 6 (last)

## Problem slice & outcome

A self-hosting operator can follow docs to register Rereflect as a SAML SP with their IdP, configure it,
and test locally against Keycloak's SAML support.

## In scope

- **`docs/SELF_HOSTING.md`** — new `## Single Sign-On (SAML 2.0)` section mirroring the OIDC section:
  - Register the SP with your IdP: ACS URL `{BACKEND_URL}/api/v1/auth/saml/callback` (HTTP-POST binding),
    SP Entity ID (document its value/derivation), NameID format `emailAddress` (or map an email attribute),
    **the IdP must sign assertions** (we reject unsigned).
  - Configure in the app: the `/settings/sso` SAML fields (Entity ID, SSO URL, X.509 cert, email
    attribute, allowed domains, button label, enable).
  - Allowed email domains: empty = **deny-all** (reuse OIDC wording).
  - **One SSO protocol per deployment** — enabling SAML requires OIDC disabled (and vice-versa).
  - JIT provisioning + account linking (new user → `member`; existing verified-email account linked).
  - **Known limitations (slice 1):** SP-initiated only (no IdP-initiated), no SLO, no SCIM, signed-but-not-
    encrypted assertions, single IdP, single cert (document cert-rotation caveat — see PRD hard question:
    rotate by pasting the new cert before the old is retired; owner password login is the lockout fallback).
  - **Testing against local Keycloak (SAML):** `docker compose --profile dev-idp up keycloak`, create a
    SAML client in a realm, copy its SAML metadata (Entity ID / SSO URL / signing cert) into `/settings/sso`.
  - Troubleshooting: the `?sso_error=` code table (`disabled|config|signature|assertion|audience|recipient|
    expired|replay|unsolicited|unverified|domain|denied`).
- **`.env.example`**: confirm the ACS-URL note under `BACKEND_URL` (added in `deps-and-docker`); nothing
  new required (no SP key in slice 1).
- **`docker-compose.yml`**: no new service required (existing Keycloak speaks SAML); optionally add a
  comment that the `dev-idp` Keycloak can host a SAML realm.
- **Tracking:** tick `DEV-TRACKING.md:234` M3.6 SAML line + `AI-TRACKING.md` M3.6 row; `CHANGELOG.md`
  entry. **Honesty:** describe exactly slice-1 scope (SP-initiated, no SLO/SCIM), no overclaiming.

## Out of scope

- Marketing/landing copy (unless the OIDC card added a landing FAQ entry — mirror only if trivial).

## Acceptance criteria (testable)

- `SELF_HOSTING.md` SAML section is complete and matches the shipped field names, ACS path, and error codes.
- Tracking + CHANGELOG updated with accurate, non-overclaiming scope.
- Any repo honesty-grep gates (as used by prior cards) pass on the diff.

## Dependencies & sequencing

- **Depends on:** all functional aspects (documents shipped behavior).
- **Blocks:** nothing.

## Open questions / risks

- Keep scope claims aligned with what actually shipped; if a nice-to-have (SP metadata endpoint) slipped,
  document it; if not, don't mention it.
