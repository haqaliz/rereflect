# Aspect Spec — config-model-and-crud

**Parent PRD:** `../prd.md` · **Aspect:** `config-model-and-crud` · **Sequence:** 2

## Problem slice & outcome

An admin/owner can store and manage the deployment's single SAML IdP connection, and the deployment
enforces **one SSO protocol total** (OIDC xor SAML). Mirrors `oidc_config` exactly in shape/security.

## In scope

- **Model** `src/models/saml_config.py` → `saml_configs` (one row/org): `id`, `organization_id`
  (FK CASCADE, `uq_saml_configs_org_id`), `idp_entity_id` String(255), `idp_sso_url` String(512),
  `idp_x509_cert` Text (**public PEM, not encrypted**), `email_attribute` String(255) nullable,
  `enabled` Bool (default+server_default false), `allowed_email_domains` JSON (empty = **deny-all**),
  `button_label` String(255) default "Sign in with SSO", `created_at`/`updated_at`. Export from
  `models/__init__.py`.
- **`users.saml_subject`** String(255), unique, nullable, indexed (`ix_users_saml_subject`); add `"saml"`
  to the `auth_provider` value set (and support the `"both"` combination as OIDC does).
- **Alembic migration(s)** chaining from head — **run `alembic heads` live to confirm** (`n8o9p0q1r2s3`
  inferred): create `saml_configs`, add `users.saml_subject` + index. No partial unique index on
  `enabled` (SQLite parity — guard lives in the route layer).
- **CRUD routes** `src/api/routes/saml_config.py`, `APIRouter(prefix="/api/v1/settings/saml", tags=["saml-config"])`,
  `require_admin_or_owner` on every verb: `GET`/`PUT`/`DELETE ""`. Pydantic `SamlConfigUpdateRequest`
  (idp_entity_id, idp_sso_url, idp_x509_cert, email_attribute?, enabled, allowed_email_domains,
  button_label?) + `SamlConfigResponse` (`configured`, fields, never returns nothing sensitive — cert is
  public so it MAY be returned; decide: return a cert fingerprint/hint rather than full PEM for tidiness).
  Reuse `_normalize_domains` semantics (empty preserved = deny-all). **PEM-validate** `idp_x509_cert` on
  save (parse via cryptography; 422 on garbage). SSRF-validate `idp_sso_url` on save (https + host gate).
- **Cross-provider single-enabled guard (M6):** a shared helper checks BOTH `saml_configs` and
  `oidc_configs` for any other `enabled` row. On enabling SAML → 422 if any OIDC (or other SAML) config
  is enabled. **Edit the shipped `src/api/routes/oidc_config.py`** so enabling OIDC reciprocally checks
  `saml_configs`. Factor the guard so both call it.
- **Status probe** `GET /api/v1/auth/saml/status` (public, in `auth.py`) → `{enabled, button_label}`,
  leaks nothing else, never 500s.
- **Tests** `tests/test_saml_config.py`: model shape/defaults/unique; CRUD happy paths; member 403;
  PEM-invalid → 422; SSRF IdP URL → 422; empty allowlist round-trips (deny-all); status endpoint 2-key
  shape. **Plus a characterization test** that OIDC's own single-enabled behavior is **byte-stable except**
  the new cross-check (gap 3): enabling OIDC still 422s a second OIDC, AND now 422s when SAML is enabled.

## Out of scope

- Provider/assertion logic, login routes, replay store (later aspects).
- SP private key storage (no signed requests in slice 1).

## Acceptance criteria (testable)

- All `tests/test_saml_config.py` cases pass; the OIDC cross-check characterization test passes with
  OIDC's prior behavior otherwise unchanged.
- `alembic upgrade head` then `downgrade` round-trips cleanly on the new migration.
- Enabling SAML while OIDC is enabled → 422 (and vice-versa); one active protocol max.

## Dependencies & sequencing

- **Depends on:** `deps-and-docker` (import), existing `oidc_config` route (to edit), `encryption`/`ssrf` utils.
- **Blocks:** `provider-and-replay-store`, `login-routes-and-identity`, `frontend-saml-ui`.

## Open questions / risks

- Return full cert PEM vs a fingerprint in `SamlConfigResponse` (public info either way; fingerprint is tidier).
- The OIDC-route edit touches shipped auth code — keep the diff minimal and characterization-gated (gap 3).
