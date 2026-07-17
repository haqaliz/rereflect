# Aspect Spec — `oidc-config`

**Feature:** `oidc-sso` · **Aspect:** `oidc-config` · **PRD:** `../prd.md` (M2, M3, M4, M12)
**Status:** Draft → ready to plan · **Date:** 2026-07-17

---

## Problem slice & user outcome

Give an operator a place to store their IdP connection — issuer, client id, client secret, the domain
allowlist, and an on/off switch — and give the rest of the system two read paths: an admin-only config
read/write, and a public "is SSO enabled?" probe the login page needs before it can show a button.
This aspect writes **no auth flow** — just the data foundation the `oidc-login-flow` aspect will read.

## In-scope (PRD M2/M3/M4/M12)

1. **`OidcConfig` model + migration** (M2). Per-org table, mirroring `ZendeskIntegration` exactly:
   - `id`, `organization_id` (FK `organizations.id` `ondelete=CASCADE`, unique per org),
   - `issuer_url` (String, operator-supplied discovery base),
   - `client_id` (String),
   - `client_secret` (Text, **Fernet-encrypted in the route layer**, never plaintext),
   - `secret_hint` (String(8), last chars of plaintext for display),
   - `enabled` (Boolean, default False, server_default false),
   - `allowed_email_domains` (JSON list of lowercased domain strings) — M12,
   - `button_label` (String, default "Sign in with SSO"),
   - `created_at` / `updated_at`.
   - **Migration chains off head `b8c9d0e1f2a3`** (verified live 2026-07-16). Verify upgrade **and**
     downgrade on a **scratch Postgres** DB (`createdb` + `DATABASE_URL=...`), never `-x sqlalchemy.url`
     (memory: it's ignored and once dropped real columns), never the dev DB.
2. **`D5` one-enabled-per-deployment guard.** At most one row may have `enabled=true` across the whole
   deployment. Enforce in the **route layer** (a write that would enable a second config → 422), because
   a Postgres partial unique index `WHERE enabled` is not enforced by the SQLite test DB (state the
   divergence in the plan; the route check is the real gate, the index is defense-in-depth on Postgres).
3. **Config CRUD API** (M3): `GET/PUT/DELETE /api/v1/settings/oidc`, `require_admin_or_owner`,
   `organization_id`-scoped. Encrypt in the route; **missing `LLM_ENCRYPTION_KEY` → 422, never 500**;
   **client_secret is NEVER returned** in any response (return `secret_hint` only).
4. **`allowed_email_domains` validation** (M12): each entry a plausible domain, lowercased/stripped;
   an empty or absent list is **stored as-is and means deny-all** at provisioning time (the login-flow
   aspect enforces the deny; this aspect must not silently coerce empty→allow-all).
5. **Public status endpoint** (M4): `GET /api/v1/auth/oidc/status` (unauthenticated) →
   `{enabled: bool, button_label: str}`. Leaks nothing else — no issuer, no client id, no domains.
6. **Router registration** in `src/api/main.py` for both new routers.

## Out-of-scope

- The auth-code flow, discovery, JWKS, token validation, JIT, SSRF gate on the issuer (all
  `oidc-login-flow`). This aspect stores the issuer string; it does **not** fetch it.
- Any frontend (`oidc-frontend`).
- Docs / compose (`oidc-docs-and-compose`).
- Adding `oidc_sub`/`auth_provider="oidc"` to `users` — that lands with `oidc-login-flow` where it's used.

## Acceptance criteria (testable)

- **AC1** — Migration applies and reverses cleanly on scratch Postgres (`upgrade head` → `downgrade -1`
  → `upgrade head`), and `alembic heads` remains a **single** head afterward.
- **AC2** — `PUT /settings/oidc` with a secret stores it Fernet-encrypted (ciphertext ≠ plaintext in the
  row) and returns `secret_hint` but never `client_secret`. Round-trips via `decrypt_api_key`.
- **AC3** — Missing `LLM_ENCRYPTION_KEY` → 422 (not 500) on write.
- **AC4** — Enabling a second config when one is already enabled → 422 (D5).
- **AC5** — A non-admin (member) is rejected by `require_admin_or_owner` on all `/settings/oidc` verbs.
- **AC6** — `GET /auth/oidc/status` is reachable unauthenticated, returns `{enabled, button_label}` only,
  and reports `enabled:false` when no config exists.
- **AC7** — All new tests green, scoped (`pytest tests/test_oidc_config.py -v`); backend auth suite
  (`test_auth.py`, `test_google_auth.py`) still green (no regression).

## Dependencies & sequencing

- **Blocked by:** `auth-test-harness` (done). **Blocks:** `oidc-login-flow`, `oidc-frontend`.
- Migration must land first within the aspect; CRUD + status routes follow.

## Open questions / risks

- **R1 (SQLite vs Postgres divergence, a repeated PRD risk).** `JSON` column + partial-unique-on-enabled
  behave differently on SQLite (tests) vs Postgres (prod). Mitigation: the D5 guard is a **route check**
  (works on both); tests assert the route behaviour, and the migration is verified on real Postgres (AC1).
- **R2 (issuer validation).** This aspect stores `issuer_url` as a string. It must **not** be trusted or
  fetched here — the SSRF gate lives in `oidc-login-flow`. Store, don't dereference.
