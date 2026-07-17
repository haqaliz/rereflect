# Understanding — feat/saml-sso (Phase 2 dig)

Synthesis of two read-only dig agents (backend; frontend + docs/deps) over the shipped OIDC SSO
implementation, which SAML 2.0 mirrors. Base: worktree on local `master` @ c6d80da.

## What the card is really asking

Add **SP-initiated SAML 2.0 login** against a single operator-configured IdP (Okta / Azure AD /
Google Workspace / Keycloak), as a sibling to the just-shipped OIDC SSO, strictly additive to
password + Google + OIDC. All features unlocked (OSS, no plan gate).

## The reuse map (what OIDC already gives us)

**Reuse directly (generic identity/security plumbing):**
- **Identity resolution** (`auth.py` L492-552): external-subject → verified-email link → JIT-provision
  as `member`, then mint JWT via `create_access_token`, then 302 to `{FRONTEND_URL}/login/callback#token=<jwt>`.
  Transfers to SAML by swapping `sub`→SAML NameID/subject and `email`→mapped email attribute. **Keep the
  null-subject rejection** (prevents the `WHERE saml_subject IS NULL` account-takeover).
- **Frontend token handoff**: `/login/callback` page consumes `#token=`, `AuthContext.login()` stores it.
  Already public in BOTH allowlists (`api-client.ts` L41-45 + `AuthContext.tsx` L28-40) → **no change
  needed** if SAML reuses `/login/callback` (recommended).
- **SSRF gate**: `_require_https_public()` + `assert_host_not_ssrf()` (`utils/ssrf.py`) — reuse for the
  IdP SSO URL / metadata URL / ACS.
- **HMAC state plumbing**: `sign_state`/`verify_state`/`hash_nonce` (`_oidc_state.py`) → reuse for RelayState.
- **Config CRUD pattern**: `require_admin_or_owner`, org-scoping, D5 single-enabled guard
  (`_assert_no_other_enabled`), domain-allowlist normalization (empty = **deny-all**), write-only
  secret + Fernet-at-rest + `secret_hint`. `LLM_ENCRYPTION_KEY`, `FRONTEND_URL`, `BACKEND_URL` env vars reuse.
- **UI patterns**: `/settings/sso` page kit, `OidcSignInButton` runtime-probe pattern, `?sso_error=`
  + `getSsoErrorMessage` map, sidebar entry, dev Keycloak (`docker compose --profile dev-idp`, also speaks SAML).
- **Docs**: `SELF_HOSTING.md` sections for allowed-domains, JIT provisioning, one-enabled-per-deployment,
  testing-against-Keycloak, troubleshooting all translate.
- **Tests**: mirror `test_oidc_config.py` / `test_oidc_provider.py` / `test_oidc_login.py` →
  `test_saml_config.py` / `test_saml_provider.py` / `test_saml_login.py`; frontend mirrors the 5 OIDC test files.

**SAML-specific (net-new, the "heavier slice"):**
1. **XML signature validation** over the SAML Response/Assertion (replaces JWT/RS256 validation). Needs
   a new dependency — `python3-saml` or `pysaml2` — which pulls **native `libxmlsec1`/`libxml2`** system
   packages → **Dockerfile impact** (`services/backend-api/Dockerfile`). This is the biggest delta vs
   Authlib (pure-Python). Guard against **XML Signature Wrapping (XSW)** and reject unsigned assertions
   (the alg-confusion analog).
2. **ACS is an HTTP-POST target**, not a GET callback — different route shape (`POST /api/v1/auth/saml/callback`,
   must be CSRF-exempt / no auth, consumes `SAMLResponse` + `RelayState` form fields).
3. **Server-side replay store** for `InResponseTo` / assertion IDs — the ONE place SAML needs MORE than
   OIDC (OIDC leans on the path-scoped `oidc_session` cookie; a browser POST to the ACS can't rely on it
   the same way). Reject replayed + unsolicited responses. Redis (present) or a small DB table.
4. **Config field shape differs**: IdP entity ID, IdP SSO URL, IdP X.509 signing cert (public — likely
   NOT encrypted), SP entity ID, ACS URL, email-attribute mapping. Only `enabled` / `button_label` /
   `allowed_email_domains` carry over from OIDC's config shape.
5. **Strict condition checks**: `Audience` (SP entity ID), `Recipient`/`Destination` (ACS URL),
   `NotOnOrAfter` / `NotBefore` (clock skew), `InResponseTo`.
6. **`users.saml_subject`** column (separate from `oidc_sub`; `oidc_sub` is per-issuer-scoped and would
   collide) + `"saml"` in `auth_provider`. Migration chains from head `n8o9p0q1r2s3` (verify live with
   `alembic heads`).

## Affected services

- **backend-api** (primary): `models/saml_config.py`, `models/user.py` (+`saml_subject`), a SAML provider
  service, `routes/saml_config.py` (CRUD) + SAML login routes in `auth.py` (or a dedicated router),
  Alembic migration(s), `requirements.txt` + `Dockerfile` (native xmlsec deps), `main.py` registration.
- **frontend-web**: SAML config UI on/near `/settings/sso`, a SAML sign-in button, SAML `sso_error` codes,
  API client `lib/api/saml.ts`.
- **worker-service / analysis-engine**: not involved.
- **docs**: `SELF_HOSTING.md` SAML section, `.env.example` notes, `docker-compose.yml` (Keycloak SAML realm doc).

## Open questions for the interview (code can't resolve these)

1. **SAML library**: `python3-saml` (OneLogin, SP-focused, common) vs `pysaml2` (fuller-featured, heavier)
   vs a `signxml`-based minimal path. Security + Docker weight implications. *Lean: `python3-saml`.*
2. **IdP config input**: metadata-URL/XML-upload auto-parse (friendlier, adds an SSRF-gated fetch/parse)
   vs manual field entry (entity ID + SSO URL + cert; simpler, smaller attack surface). *Lean: support
   both, but manual entry is the safe minimum for slice 1.*
3. **OIDC + SAML coexistence**: may both be enabled at once (two SSO buttons on login), or is it one SSO
   protocol per deployment (cross-provider single-enabled guard)? Affects the login-page button UX and
   the D5 guard scope.
4. **AuthnRequest signing**: sign SP requests (needs SP private key/cert → more config + Fernet-at-rest)
   or send unsigned SP-initiated requests but **require signed IdP assertions**? *Lean: unsigned request,
   require signed assertion — smallest slice-1 surface.*
5. **Email trust**: SAML has no `email_verified`. Treat a validly-signed assertion's email as trusted
   (IdP asserts it) — confirm, and confirm the default email attribute (NameID emailAddress vs a named
   attribute) + whether the mapping is configurable.
6. **Replay store backing**: Redis (present, TTL-native) vs a DB table (durable, easy to test). *Tech-plan
   detail, but affects the model set.*

## Contradiction / risk flags

- **Base branch**: OIDC (c6d80da) is on local master, not on `origin/master` (`aabcf07`). Worktree
  branched from local master; reconcile at PR time (see card).
- **`/settings/sso` is single-provider, not tabbed** — adding SAML forces a UX choice (tabs / second card /
  separate page). See open question 3.
- **CLAUDE.md is stale** (pre-OSS-pivot): its "Enterprise: SSO/SAML" plan-gating table does NOT apply —
  SAML is unlocked like everything else. Don't reintroduce a plan gate.
