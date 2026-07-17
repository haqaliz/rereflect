# Card — feat/saml-sso (freeform, no GitHub issue)

**Type:** feat
**Slug/id:** saml-sso
**Branch:** feat/saml-sso
**Base:** local `master` @ c6d80da (Merge feat/oidc-sso) — see base-branch note below
**Source:** `rereflect-next` handoff (2026-07-17). No GitHub issue; this brief is the source of truth.

## Brief

Add **SAML 2.0 SSO** for self-hosted deployments as the deferred second half of the M3.6 SSO
milestone. The OIDC half shipped as `feat/oidc-sso` (merged at HEAD `c6d80da`); SAML was explicitly
left as "a separate, heavier slice."

- `DEV-TRACKING.md:234` (M3.6): `[ ] SAML 2.0 integration (Okta, Azure AD, Google Workspace) — deferred (separate, heavier slice)`
- `DEV-TRACKING.md:168-169`: `[~] SSO — OIDC shipped … SAML deferred. Plan gate void (OSS, all unlocked).`
- `DEV-TRACKING.md:233-237` (M3.6 block).

## Why this was picked (moat fit)

- Explicit, documented next slice off the card that just merged — a follow-on slice, not an invented feature.
- Deepens the self-hosted / enterprise-adoption story; SAML is the mandatory SSO for a large slice of
  Okta / Azure AD / OneLogin shops. Fits OSS/self-hosted/BYOK (operator configures their own IdP,
  nothing hosted, no plan gate).
- Large reuse of what OIDC just built (see Reuse seams below) → small, testable slice 1.

## Scope

**Slice 1 (this card):** SP-initiated SAML 2.0 login against a **single** operator-configured IdP
(Okta / Azure AD / Google Workspace):
- `saml_config` model + `/settings/sso` SAML tab mirroring the OIDC config UI.
- SP metadata / AuthnRequest redirect (SP-initiated) + ACS (Assertion Consumer Service) endpoint.
- NameID → wire into the **existing** external-identity → verified-email-link → JIT-provision-as-member
  resolver, reusing the `/login/callback#token=` handoff, publicRoutes, and domain allowlist.
- Strictly additive to password + Google + OIDC login.

**Deferred (later slices; name in PRD as out-of-scope):** IdP-initiated flow, Single Logout (SLO),
SCIM provisioning, multiple IdPs per org, encrypted assertions (beyond signed).

## Reuse seams (from OIDC, present at c6d80da)

- Backend: `services/backend-api/src/models/oidc_config.py`, `src/services/oidc_provider.py`,
  `src/api/routes/oidc_config.py`, `src/api/routes/_oidc_state.py`.
- Identity resolution (external subject → link → JIT member) + token handoff: `src/api/routes/auth.py`
  (~L430, L502-558); `users.oidc_sub` linking-column pattern (`src/models/user.py:22`).
- Frontend: `/settings/sso` config UI, SSO sign-in button + login error surface, `/login/callback`
  token handoff; `lib/api-client.ts:42` treats `/login/callback` as public.

## Known caveat (carry into the dig + PRD)

SAML's cost is the **XML security surface**, heavier than OIDC's (why it was deferred):
- Hardened XML-signature validation — guard against XML Signature Wrapping (XSW).
- Assertion replay protection; strict `Audience` / `Recipient` / `NotOnOrAfter` condition checks.
- Pulls in a **native dependency** (`pysaml2` or `python3-saml` → `xmlsec` / `libxml2`) that the
  self-host Docker image must carry and `SELF_HOSTING.md` must document.
- Apply the OIDC card's security-review discipline early.

## ⚠️ Base-branch note (surfaced in Phase 0)

The OIDC merge (`c6d80da`) is committed on **local** `master` but **not yet pushed to `origin/master`**
(origin is at `aabcf07 fix(telemetry)`). The skill's default base is `origin/master`, but SAML depends
on the OIDC code, so this worktree was branched from **local `master`** instead. When this branch is
PR'd/merged, the oidc-sso work must already be on origin (push master first) or land together — flag at
PR time.
