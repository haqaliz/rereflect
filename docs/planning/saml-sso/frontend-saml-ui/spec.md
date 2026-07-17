# Aspect Spec — frontend-saml-ui

**Parent PRD:** `../prd.md` · **Aspect:** `frontend-saml-ui` · **Sequence:** 5

## Problem slice & outcome

An admin configures SAML at `/settings/sso`, and end users get one "Sign in with SSO" button that starts
the SAML flow. Mirrors the OIDC frontend surface; exactly one SSO button ever shows (one-protocol guard).

## In scope (`services/frontend-web`)

- **API client** `lib/api/saml.ts` mirroring `lib/api/oidc.ts`: `getSamlStatus()` →
  `GET /api/v1/auth/saml/status`; `getSamlConfig()`/`putSamlConfig()`/`deleteSamlConfig()` →
  `/api/v1/settings/saml`. Types: `SamlStatus{enabled, button_label}`, `SamlConfig{configured,
  idp_entity_id, idp_sso_url, idp_x509_cert|cert_fingerprint, email_attribute, enabled,
  allowed_email_domains, button_label}`, `SamlConfigUpdate`.
- **Config UI on `/settings/sso`.** The page is currently single-provider (OIDC-hardwired). Add a
  **SAML section/card** below the OIDC card (no tabs needed) OR a lightweight two-section layout. Fields:
  IdP Entity ID, IdP SSO URL, IdP X.509 Certificate (textarea, PEM), Email attribute (optional),
  Allowed email domains (chips), Button label, Enable switch. Reuse the OIDC page's kit, save/delete
  flow, deny-all warning, and error surfacing. Surface the **cross-provider 422** ("disable OIDC first")
  as a friendly inline message.
- **`components/SamlSignInButton.tsx`** — clone `OidcSignInButton`: runtime-probe `getSamlStatus()`,
  render only when enabled, full-page nav to `${NEXT_PUBLIC_API_URL}/api/v1/auth/saml/login`, label from
  status. Mount on the login page next to the OIDC button (only one will render since only one protocol
  can be enabled).
- **`lib/samlErrors.ts`** — `getSamlErrorMessage(code)` for SAML codes (`signature`, `assertion`,
  `audience`, `recipient`, `expired`, `replay`, `unsolicited`, `disabled`, `unverified`, `domain`,
  `config`, `denied`). Login page maps `?sso_error=` through both OIDC and SAML maps (or a merged lookup).
- **Sidebar:** unchanged — the existing `SSO → /settings/sso` entry (admin-gated) already covers it.
- **Tests** mirroring the 5 OIDC frontend test files: `saml.ts` client paths; SAML config section
  (member redirect already covered by page; save incl. cert + friendly 422; deny-all warning; delete
  404); `SamlSignInButton` (renders label when enabled, nav to `/saml/login`, hidden when disabled, fails
  open); `samlErrors` map. The `/login/callback` page + `AuthContext` public-route tests already cover the
  shared handoff — **no change** needed there.

## Out of scope

- Backend (prior aspects); SP metadata display (nice-to-have); tabs refactor (a second card suffices).

## Acceptance criteria (testable)

- `npm run test` green for new SAML frontend tests; `npm run lint` clean.
- With SAML enabled + OIDC disabled, exactly one SSO button renders and navigates to `/saml/login`.
- Config save/enable/delete round-trips against the API contract; cross-provider 422 shown friendly.

## Dependencies & sequencing

- **Depends on:** `config-model-and-crud` + `login-routes-and-identity` (API contracts + status/login/ACS).
- **Blocks:** nothing (last functional aspect).

## Open questions / risks

- Whether to show full PEM back or a fingerprint in the config form (match whatever the backend returns).
- Keep the OIDC and SAML sections visually parallel; do not regress the OIDC section.
