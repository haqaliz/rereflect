# Aspect Spec — `oidc-frontend`

**Feature:** `oidc-sso` · **Aspect:** `oidc-frontend` · **PRD:** `../prd.md` (M11, M4-consumer) · **Date:** 2026-07-17
**Status:** Draft → ready to plan

---

## Problem slice & user outcome

Make the backend flow usable from the browser: (1) a "Sign in with SSO" button on the login page that
appears only when the operator enabled SSO, sending the user to the backend `/auth/oidc/start`; (2) a
`/login/callback` page that receives the JWT from the callback's URL fragment, stores it, and lands the
user on the dashboard; (3) an admin/owner settings page to configure the IdP. Existing password + Google
sign-in are untouched.

## Grounding facts (verified in the worktree)

- `AuthContext.tsx:28` `publicRoutes` is an **exact-match** list; `:38` `isPublicRoute` does
  `publicRoutes.includes(path)`. `/login/callback` is **not** an exact match of `/login`, and the only
  prefixes (`:31`) are `/invite`,`/shared`. So **`/login/callback` MUST be added to `publicRoutes`** or
  the provider redirects it to `/login` before the token is stored (dig-flagged).
- The JWT lives in `localStorage['access_token']`; `AuthContext.login(token)` (`:100`) stores it + sets
  state. Four existing call sites write it directly, bypassing `login()` (`login/page.tsx:85,102`;
  `signup/page.tsx:141,175`).
- API base: `NEXT_PUBLIC_API_URL || 'http://localhost:8000'` (`api-client.ts:4`). **`NEXT_PUBLIC_*` is
  build-time inlined** — the SSO button's enabled-state must come from the **runtime** backend
  `GET /api/v1/auth/oidc/status`, not an env var.
- Conditional-mount idiom for an optional auth backend: `app/providers.tsx:28`,
  `GoogleSignInButton.tsx:98`, `login/page.tsx:317` — the SSO button follows this exactly.
- Settings pages live under `app/(dashboard)/settings/<name>/page.tsx`; `integrations` is the closest
  pattern for a token-paste admin/owner-gated card. Role gating: `isAdminOrOwner` from `AuthContext`.

## In-scope (PRD M11)

1. **`/login/callback` page** — client page that reads the JWT from `window.location.hash`
   (`#token=<jwt>`), stores it via `AuthContext.login()` (consolidating, PRD S-2, at least for this new
   path), scrubs the hash, and `router.replace('/dashboard')`. On a `?sso_error=` (the backend error
   redirects land on `/login?sso_error=`, but if any error arrives here) show a friendly message + link
   back to `/login`. **Add `/login/callback` to `AuthContext` `publicRoutes`.**
2. **SSO button on `/login`** — fetches `GET /auth/oidc/status` on mount; if `enabled`, render a button
   labelled with `button_label` that navigates to `{API}/api/v1/auth/oidc/start` (full-page nav, not
   fetch — it's a redirect flow). Hidden entirely when disabled or the probe fails. Follows the
   conditional-mount idiom.
3. **`/login` error surface** — read `?sso_error=` on the login page and show a friendly, generic
   message (map the codes: `disabled`,`state`,`token`,`unverified`,`domain`,`exchange`,`config`,`denied`
   → human text) then scrub the param (mirror the integrations `oauth_error` pattern at
   `integrations/page.tsx:106-110`).
4. **Settings config UI** — `app/(dashboard)/settings/sso/page.tsx`, **admin/owner only** (redirect
   others, mirroring `settings/integrations` role guard). Form over `GET/PUT/DELETE /settings/oidc`:
   issuer, client_id, client_secret (write-only; show `secret_hint` for the stored value, never the
   secret), `allowed_email_domains` (list editor), `enabled` toggle, `button_label`. Surface the D5
   "another config already enabled" 422 and the missing-key 422 as friendly errors.
5. **API client module** — `lib/api/oidc.ts`: `getOidcStatus()`, `getOidcConfig()`, `putOidcConfig()`,
   `deleteOidcConfig()` using the shared `apiClient`.

## Out-of-scope

- Any backend change (done in prior aspects).
- Refactoring all four legacy token-writes to `login()` (only the new callback path uses it; broader
  consolidation is a separate cleanup).
- Docs / Keycloak compose (`oidc-docs-and-compose`).
- A nav entry/tile for the settings page beyond what's needed to reach it (link from integrations or a
  direct route is fine).

## Acceptance criteria (testable, Vitest)

- **AC1** — `/login/callback` extracts the token from `#token=…`, calls `login()` (localStorage set),
  and redirects to `/dashboard`; a callback with no token / an error shows the error state, no redirect
  to dashboard.
- **AC2** — `/login/callback` is in `AuthContext` `publicRoutes` (unit-assert the constant includes it).
- **AC3** — the SSO button renders only when `getOidcStatus()` returns `enabled:true`; hidden when
  `enabled:false` or the probe throws. When shown, it targets `{API}/api/v1/auth/oidc/start`.
- **AC4** — the login page maps a `?sso_error=domain` (etc.) to a friendly message and scrubs the param.
- **AC5** — settings page: non-admin is redirected; admin sees the form; PUT sends the secret and the
  response never exposes it; a 422 (D5 / missing key) renders a friendly error.
- **AC6** — `npm run test` green for the new tests; `npx eslint <touched files>` clean (repo-wide lint
  has ~34 pre-existing unrelated errors — gate is **no new errors on touched files**).
- **AC7** — the existing `auth-test-harness` frontend tests (AuthContext, api-client, GoogleSignInButton,
  login page) still pass (no regression to password/Google paths).

## Dependencies & sequencing

- **Blocked by:** `oidc-login-flow` (done — `/start`, `/callback`, `/status`, `/settings/oidc`).
- **Blocks:** nothing (last functional aspect; docs follow).
- Internal order: API client module → callback page + publicRoutes → login button + error surface →
  settings UI.

## Risks

- **R1 (pnpm workspace).** Tests run under pnpm; node_modules already installed in the worktree; run
  `npx vitest run <path>` / `npx eslint <path>` (not repo-wide `npm run lint`).
- **R2 (fragment timing).** The token is in `window.location.hash`; read it in a client `useEffect`
  after mount (App Router). Scrub via `history.replaceState` before redirect so it never sticks.
- **R3 (App Router client-component test friction).** `useRouter`/`useSearchParams` need mocking under
  jsdom (mirror the `auth-test-harness` tests). `useSearchParams` requires a `<Suspense>` boundary
  (CLAUDE.md FOUC/SSR note).
