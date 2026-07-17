# PRD — SAML 2.0 Single Sign-On (self-hosted)

**Slug:** `saml-sso`
**Branch:** `feat/saml-sso`
**Type:** feat (freeform; no GitHub issue)
**Status:** Draft — awaiting review gate
**Author:** Rereflect begin-fast pipeline, 2026-07-17
**Sibling of:** `oidc-sso` (shipped, merged at `c6d80da`)

---

## Problem Statement

Rereflect's self-hosted edition shipped **OIDC** SSO (`feat/oidc-sso`). A large share of enterprises
that self-host internal tools standardize on **SAML 2.0** IdPs (Okta, Azure AD / Entra, OneLogin, ADFS,
Google Workspace, Keycloak) and cannot use an OIDC-only integration. For those operators, SSO is a hard
adoption gate: without SAML, their only options are password or Google login, which many security teams
disallow for internal deployments.

This is the explicitly deferred second half of the M3.6 SSO milestone:
- `DEV-TRACKING.md:234`: `[ ] SAML 2.0 integration (Okta, Azure AD, Google Workspace) — deferred (separate, heavier slice)`
- `DEV-TRACKING.md:168-169`: `SSO — OIDC shipped … SAML deferred. Plan gate void (OSS, all unlocked).`

**Evidence it's real:** SAML remains the dominant enterprise SSO protocol for on-prem/self-hosted
software; the milestone already committed to it; the OIDC card was scoped explicitly to leave SAML as a
follow-on.

## Goals & Success Metrics

**Goal:** A self-hosting operator can configure a single SAML 2.0 IdP and have their users sign in via
SP-initiated SSO, with the same JIT-provisioning and account-linking behavior as OIDC — securely.

**Success criteria (testable):**
- An admin/owner can configure a SAML IdP (Entity ID, SSO URL, X.509 signing cert, allowed email
  domains, button label, enable) at `/settings/sso` and see it reflected in a status probe.
- A user clicks "Sign in with SSO", is redirected to the IdP, authenticates, and lands authenticated in
  the dashboard via the existing `/login/callback#token=` handoff.
- A **new** user is JIT-provisioned as `member` in the configured org; an **existing** verified-email
  user is linked (never a duplicate).
- Security: unsigned/incorrectly-signed assertions, wrong audience/recipient, expired
  (`NotOnOrAfter`)/not-yet-valid (`NotBefore`), replayed assertions, and unsolicited responses
  (unknown `InResponseTo`) are all **rejected** with a friendly `?sso_error=` code — proven by tests.
- No regression to password / Google / OIDC login (characterization-covered).

**Non-metric (honesty):** this does not claim IdP-initiated flow, SLO, or SCIM — those are out of scope
(below).

## User Personas & Scenarios

- **Operator / IT admin (owner or admin role):** configures the deployment's SAML IdP once. Wants
  copy-paste fields (Entity ID, SSO URL, cert) and a clear enable switch, mirroring the OIDC page.
- **End user (any role):** clicks one "Sign in with SSO" button on the login page; never sees SAML
  internals.

## Requirements

### Must-have (slice 1)
- **M1 — SAML config model + CRUD** (`saml_configs`, one row/org) with `require_admin_or_owner`,
  org-scoping, write-only masking pattern, and a **cross-provider single-enabled guard** (see M6).
- **M2 — SP metadata + SP-initiated AuthnRequest** (`GET /api/v1/auth/saml/login`): build an
  **unsigned** AuthnRequest (HTTP-Redirect binding) to the IdP SSO URL; carry a signed `RelayState`
  (HMAC, nonce-hash only) and persist the request ID for `InResponseTo` matching.
- **M3 — ACS endpoint** (`POST /api/v1/auth/saml/callback`): consume `SAMLResponse` + `RelayState`
  form-POST; validate XML signature against the configured IdP cert; enforce `Audience` (SP Entity ID),
  `Recipient`/`Destination` (ACS URL), `NotBefore`/`NotOnOrAfter` (with bounded clock skew),
  `InResponseTo` (known + unconsumed), and assertion-ID replay; extract NameID/subject + email attribute.
- **M4 — Identity resolution reuse**: subject → verified-email link → JIT-provision-as-`member` → mint
  JWT → 302 `{FRONTEND_URL}/login/callback#token=<jwt>`. Reuse the OIDC block verbatim in shape; keep the
  **null-subject rejection**. Add `users.saml_subject`.
- **M5 — Public status probe** (`GET /api/v1/auth/saml/status`) → `{enabled, button_label}` (leaks
  nothing else, never 500s).
- **M6 — Cross-provider single-SSO guard**: at most one of {OIDC, SAML} enabled per deployment. Enabling
  SAML fails (422) if an OIDC config is enabled, and the OIDC route gains the reciprocal check.
- **M7 — Frontend**: SAML config section on `/settings/sso`; a `SamlSignInButton` (self-probing, renders
  only when SAML enabled — so exactly one SSO button ever shows); SAML-specific `sso_error` codes; a
  `lib/api/saml.ts` client.
- **M8 — Security hardening (explicit, tested)**: reject unsigned assertions and XML Signature Wrapping
  (XSW); require assertion signature (not just response); SSRF-gate the IdP SSO URL (reuse
  `assert_host_not_ssrf` / `_require_https_public`); ACS route is auth-exempt but CSRF-safe by design
  (SAML binding, signature + `InResponseTo` are the anti-forgery controls).
- **M9 — Deps + Docker**: add `python3-saml` (+ `xmlsec`) to `requirements.txt`; add `libxmlsec1` /
  `libxml2` (+ `pkg-config`) system packages to `services/backend-api/Dockerfile`.
- **M10 — Docs**: `SELF_HOSTING.md` SAML section (register SP with IdP, ACS URL, cert, allowed domains,
  one-protocol-per-deployment, Keycloak-SAML testing, troubleshooting codes); `.env.example` notes
  (reuse `LLM_ENCRYPTION_KEY` only if we store an SP key — we don't in slice 1; `FRONTEND_URL`/`BACKEND_URL`
  document the ACS URL).

### Should-have
- Configurable **email attribute name** (default: NameID when `Format=emailAddress`, else a common
  attribute such as `email` / the standard `.../claims/emailaddress`), so operators with non-standard
  IdP attribute maps can adapt without a rebuild.
- Clear inline validation of the pasted X.509 cert (PEM parse) at save time (422 on garbage).

### Nice-to-have (may defer within slice 1 if time-boxed)
- Copyable **SP metadata XML** endpoint (`GET /api/v1/auth/saml/metadata`) so admins can import the SP
  into their IdP instead of hand-entering the ACS URL / SP Entity ID.

## Technical Considerations

**Services changed:** `backend-api` (primary) + `frontend-web` + docs. **Not** worker/analysis.

**Decisions locked (interview, 2026-07-17):**
1. **Library:** `python3-saml` (OneLogin) — SP-focused, XSW-protected, "don't hand-roll auth" precedent.
2. **IdP config input:** **manual fields only** (Entity ID, SSO URL, X.509 cert). Metadata-URL import deferred.
3. **Coexistence:** **one SSO protocol per deployment** — cross-provider single-enabled guard; one SSO button.
4. **Request signing:** **unsigned AuthnRequest, require signed assertions** — no SP private key in slice 1.

**Reuse (from OIDC, present at c6d80da):** identity-resolution block (`auth.py` L492-552), `/login/callback`
`#token=` handoff (already public in both frontend allowlists), `assert_host_not_ssrf` /
`_require_https_public`, `sign_state`/`verify_state`/`hash_nonce` (for RelayState), config-CRUD pattern
(`require_admin_or_owner`, org-scope, domain deny-all normalization, D5 guard), `/settings/sso` UI kit,
`OidcSignInButton` pattern, `?sso_error=` map, dev Keycloak (`--profile dev-idp`, also speaks SAML).

**Multi-tenancy:** `saml_configs.organization_id` scoped like `oidc_configs`; JIT users attach to the
config's org. Same as OIDC.

### Data Model (SQLAlchemy / Alembic)

New table `saml_configs` (mirrors `oidc_configs`):

| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | |
| `organization_id` | Integer FK→organizations, CASCADE, unique (`uq_saml_configs_org_id`) | one row/org |
| `idp_entity_id` | String(255) | IdP EntityID |
| `idp_sso_url` | String(512) | IdP SingleSignOnService (HTTP-Redirect) URL — SSRF-gated on save + use |
| `idp_x509_cert` | Text | PEM signing cert (**public** — not encrypted); PEM-validated on save |
| `email_attribute` | String(255) nullable | override for the email attribute/NameID mapping |
| `enabled` | Boolean, default/server_default false | |
| `allowed_email_domains` | JSON | empty = **deny-all** (same as OIDC) |
| `button_label` | String(255), default "Sign in with SSO" | |
| `created_at` / `updated_at` | DateTime | |

`users` gains `saml_subject` String(255), unique, nullable, indexed (mirrors `oidc_sub`/`google_id`);
`auth_provider` gains `"saml"` (and `"both"`-style combinations as OIDC does).

**Replay store:** new table `saml_used_assertions` (or `saml_auth_requests` + consumed flag): store
issued AuthnRequest IDs (for `InResponseTo`) and consumed assertion IDs with a `NotOnOrAfter`-derived
expiry; conditional-insert / mark-consumed to reject replays; opportunistic cleanup of expired rows.
(DB-backed for durability + SQLite-testability; Redis is the noted alternative — see Risks.)

Migrations chain from current head **`n8o9p0q1r2s3`** (verify live with `alembic heads` before authoring).

### API Contracts (FastAPI)

- `GET  /api/v1/auth/saml/status` → `{enabled, button_label}` (public).
- `GET  /api/v1/auth/saml/login` → 302 to IdP (SP-initiated AuthnRequest, RelayState, request-id persisted).
- `POST /api/v1/auth/saml/callback` (ACS) → validate → 302 `{FRONTEND_URL}/login/callback#token=…` or
  302 `{FRONTEND_URL}/login?sso_error=<code>`.
- `GET/PUT/DELETE /api/v1/settings/saml` (admin/owner) → config CRUD, `SamlConfigResponse` never returns
  private material.
- *(nice-to-have)* `GET /api/v1/auth/saml/metadata` → SP metadata XML.

**New `sso_error` codes:** `signature`, `assertion`, `audience`, `recipient`, `expired`, `replay`,
`unsolicited`, plus reused `disabled`, `unverified`(→ no email), `domain`, `config`.

### Non-Functional
- **Security first** (this is the whole risk of the feature): XSW resistance, mandatory assertion
  signature, strict conditions, replay + unsolicited rejection, SSRF-gated IdP URL. Security-review the
  ACS + provider before merge (apply the OIDC card's discipline).
- **TDD**: mirror `test_oidc_config/provider/login` → `test_saml_config/provider/login`, including the
  no-takeover cases and every rejection path. Frontend mirrors the 5 OIDC test files.

## Risks & Open Questions

- **R1 — Native dependency weight (highest-effort risk).** `python3-saml`→`xmlsec`→`libxmlsec1`/`libxml2`
  need OS packages in the backend image and CI. If the Docker/CI base lacks them, the whole test suite
  can't import. *Mitigation:* land the Dockerfile/requirements + a trivial import test FIRST (RED→GREEN)
  before any SAML logic; document air-gapped install in `SELF_HOSTING.md`.
- **R2 — XSW / signature-validation correctness.** The class of SAML bug that matters. *Mitigation:* rely
  on `python3-saml`'s validated path (don't post-process the XML ourselves), require signed assertions,
  and add explicit XSW/unsigned/wrong-cert rejection tests.
- **R3 — Replay store backing (open).** DB table (durable, SQLite-testable) vs Redis (TTL-native, already
  present for Celery). PRD assumes **DB-backed**; revisit in tech-plan if there's a strong reason for Redis.
- **R4 — Email attribute variance across IdPs (open).** Default mapping may miss some IdPs; the
  configurable `email_attribute` is the mitigation. Confirm the default chain (NameID emailAddress →
  `email` attr → standard claim URI).
- **R5 — Clock skew** on `NotBefore`/`NotOnOrAfter`. Use a small bounded tolerance (e.g. ±60s), tested.
- **R6 — Base branch.** OIDC (`c6d80da`) is on local `master`, not `origin/master` (`aabcf07`); this
  branch was cut from local master. Reconcile at PR time (push oidc-sso first or land together).

## Out of Scope (explicit)

- **IdP-initiated** SSO (only SP-initiated in slice 1).
- **Single Logout (SLO)**.
- **SCIM / directory provisioning** (JIT only).
- **Signed AuthnRequests / SP private key** (require signed assertions instead).
- **Encrypted assertions** (signed-only; encryption deferred).
- **Multiple SAML IdPs per org / per deployment** (one config, and one SSO protocol total).
- **Metadata-URL auto-import** (manual field entry only; SP-metadata *export* is a nice-to-have).
- **Any plan gating** — OSS self-hosted, all unlocked (CLAUDE.md's Enterprise/SSO-SAML tier table is
  pre-pivot and stale).
