# Aspect Spec — `oidc-docs-and-compose`

**Feature:** `oidc-sso` · **Aspect:** `oidc-docs-and-compose` · **PRD:** `../prd.md` (M13, S-4) · **Date:** 2026-07-17
**Status:** Draft → ready to plan · **Low risk (docs/config), but M13 is a must-have** — a config-driven
feature nobody can find is unbuilt.

---

## Problem slice & user outcome

An operator can discover, configure, and test OIDC SSO without reading source. This aspect makes the
feature real to a human: env docs, a self-hosting guide section, a local IdP to test against, and a
sidebar entry so the settings page is reachable (not URL-only).

## In-scope

1. **`.env.example` (M13).** Add the OIDC-relevant keys with guidance:
   - **`LLM_ENCRYPTION_KEY`** — *currently missing from `.env.example` entirely* (verified). It is the
     Fernet key that encrypts ALL integration secrets incl. the OIDC `client_secret`; without it the
     config CRUD returns 422. Add it with the generate command
     (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
   - Confirm `FRONTEND_URL` (line 10) and `BACKEND_URL` (line 21) are present (they are) — the OIDC flow
     uses both; add a comment noting they define the SSO redirect + callback base.
2. **`docs/SELF_HOSTING.md` OIDC SSO section (M13).** A new section covering:
   - What it is (self-hosted OIDC login alongside password/Google; all features unlocked).
   - Register a client with your IdP (Okta/Azure AD/Google Workspace/Keycloak): redirect/callback URL to
     whitelist = **`{BACKEND_URL}/api/v1/auth/oidc/callback`**; scopes `openid email profile`; response
     type `code`; PKCE (S256).
   - Configure in-app at **`/settings/sso`** (admin/owner): issuer URL, client id, client secret,
     allowed email domains, enable toggle.
   - **`allowed_email_domains` deny-all semantics:** empty list = nobody can sign in; you MUST list at
     least one domain. Warn about over-broad domains (e.g. `gmail.com`) with a multi-tenant issuer.
   - **One enabled config per deployment** (D5).
   - **JIT provisioning:** first SSO login auto-creates a `member` in the configured org; existing
     password/Google users with the same **verified** email are linked.
   - **Known limitation: RS256-only.** ID tokens must be RS256-signed (the common default for Okta/Azure
     AD/Google/Keycloak). An IdP signing with ES256/other is currently rejected — documented honestly.
   - Troubleshooting: the `sso_error=` codes and what each means.
3. **`docker-compose.yml` Keycloak (S-4).** Add a `keycloak` service (dev/test IdP) — a pinned image,
   dev mode, a mapped port, minimal admin creds via env, NOT started by default in prod compose (dev
   file only, or a profile). Enough that `docker compose up keycloak` gives a working local OIDC issuer
   to point `/settings/sso` at. A short note in SELF_HOSTING on using it for a test run.
4. **Sidebar nav link (closes the `oidc-frontend` gap).** Add one entry to `AppSidebar.tsx`'s settings
   list (`:139-150`): `{ title: 'SSO', href: '/settings/sso', icon: <lock/shield>, requiredRole: 'admin' }`.
   Mirrors the `Integrations`/`AI` admin-gated entries. Without this the settings page is URL-only.
5. **Tracking (M13/S-3).** Note the feature in the repo's changelog/AI-TRACKING if that's the convention
   (check how prior features recorded themselves; keep it factual — a self-hosted OIDC SSO login,
   RS256-only, JIT+allowlist).

## Out-of-scope

- Any backend/flow behavior change (done). This aspect documents + exposes what exists.
- Migrating jira/zendesk to the shared SSRF helper (named follow-up from `oidc-login-flow`).
- SAML/SCIM/multi-org (PRD out-of-scope).
- ES256 support (documented as a known limitation; a real follow-up if an operator needs it).

## Acceptance criteria

- **AC1** — `.env.example` includes `LLM_ENCRYPTION_KEY` with a generate command; FRONTEND_URL/BACKEND_URL
  commented as SSO-relevant.
- **AC2** — `docs/SELF_HOSTING.md` has an OIDC SSO section covering: callback URL to whitelist, `/settings/sso`,
  deny-all allowlist, one-enabled-per-deployment, JIT+linking, RS256-only limitation, and the sso_error codes.
- **AC3** — `docker-compose.yml` defines a `keycloak` service that starts a working local OIDC issuer;
  `docker compose config` validates (no YAML/schema error). It must NOT change the default `up` set for
  prod (dev-only / profile-gated).
- **AC4** — `AppSidebar.tsx` shows an admin-gated `SSO` entry linking `/settings/sso`; the frontend still
  builds and the existing sidebar tests (if any) pass; eslint clean on the touched file.
- **AC5** — no code/behavior regression: backend auth suite + frontend auth/OIDC tests still green (this
  aspect shouldn't touch them, but verify the sidebar change didn't break a snapshot/test).

## Dependencies & sequencing

- **Blocked by:** all prior aspects (done). **Blocks:** nothing — this is the last aspect.
- Order: docs + env (independent) → compose → sidebar link. All low-coupling.

## Risks

- **R1 (compose correctness).** A bad Keycloak service could break `docker compose up`. Mitigation:
  dev-file/profile only; validate with `docker compose config`; pin the image tag.
- **R2 (doc drift).** Keep the doc faithful to the shipped behavior (RS256-only, deny-all, D5) — no
  aspirational claims. Cross-check against the code before writing.
