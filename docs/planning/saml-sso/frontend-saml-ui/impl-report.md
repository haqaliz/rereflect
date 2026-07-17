# Implementation Report — frontend-saml-ui

**Aspect:** `frontend-saml-ui` (sequence 5) · **Branch:** `feat/saml-sso` · **Service:** `services/frontend-web`
**Method:** strict TDD (RED → verify-fail → GREEN → REFACTOR) with Vitest, phase-by-phase per the plan.

## Environment note

`npm run test` / `npx vitest` are intercepted by the user's `rtk` shell hook and silently return 0
suites (a proxy artifact, not a project issue). All commands below were run with the vitest binary
directly (`./node_modules/.bin/vitest run <paths>`), which is what the numbers reflect — behaviorally
identical to `npm run test -- --run <paths>`.

## Pre-flight baseline (before any change)

```
./node_modules/.bin/vitest run lib/api/__tests__/oidc.test.ts lib/__tests__/oidcErrors.test.ts \
  components/__tests__/OidcSignInButton.test.tsx "app/(dashboard)/settings/sso/__tests__/page.test.tsx"
```
→ 4 test files, **23 tests passed**.

```
./node_modules/.bin/eslint .
```
→ 53 pre-existing problems (34 errors, 19 warnings), all unrelated to SSO (e.g.
`contexts/UrgentFeedbackPageContext.tsx`, `hooks/useRealtimeEvents.ts`).

```
./node_modules/.bin/vitest run   # whole repo
```
→ 14 failed test files / 26 failed tests (pre-existing: WebhooksSettings, SalesforceTile, and a
handful of others tripping a known jsdom/undici `UND_ERR_INVALID_ARG` fetch-mock issue — unrelated to
SSO) / 125 passed files / 1291 passed tests.

## Contract lock (read before writing code)

Read the shipped backend directly (all backend aspects already merged):
- `services/backend-api/src/api/routes/saml_config.py` — confirmed `SamlConfigResponse` returns
  `cert_fingerprint` (SHA-256, colon-hex) and **never** `idp_x509_cert`; `idp_x509_cert` optional on
  PUT (omit to keep existing PEM); 422 on PEM validation, SSRF/https, D5 same-provider, and
  cross-provider (`assert_no_other_provider_enabled`) guards.
- `services/backend-api/src/api/routes/auth.py` — confirmed `GET /api/v1/auth/saml/status` and
  `GET /api/v1/auth/saml/login` (SP-initiated start, not `/start`), and the `sso_error=<code>` redirect
  pattern shared with OIDC.

This confirmed the plan's primary branch (§5 option A: fingerprint-only, write-only cert textarea).

## Phase-by-phase (RED → GREEN, one commit per phase)

| Phase | Files | Test run before impl (RED) | Test run after impl (GREEN) | Commit |
|---|---|---|---|---|
| A | `lib/api/saml.ts` + test | module-not-found | 5/5 pass | `384214d` |
| B | `lib/samlErrors.ts` + test | module-not-found | 13/13 pass | `ab0c020` |
| C | `components/SamlSignInButton.tsx` + test | module-not-found | 4/4 pass | `19e7547` |
| D | `app/login/page.tsx` (mount button + merge error map) | n/a — no new test file (plan explicitly defers to shared callback/AuthContext coverage) | full targeted set (45 tests) still green | `13b12f3` |
| E | `components/settings/SamlConfigCard.tsx` + `app/(dashboard)/settings/sso/page.tsx` + extended page test | `saml-config-card` testid not found (5 new tests failed for the right reason; 5 pre-existing OIDC tests already passing) | 10/10 pass | `060eb7b` |

Final targeted run (all 7 SSO-related frontend test files):

```
./node_modules/.bin/vitest run \
  lib/api/__tests__/saml.test.ts lib/__tests__/samlErrors.test.ts \
  components/__tests__/SamlSignInButton.test.tsx lib/api/__tests__/oidc.test.ts \
  lib/__tests__/oidcErrors.test.ts components/__tests__/OidcSignInButton.test.tsx \
  "app/(dashboard)/settings/sso/__tests__/page.test.tsx"
```
→ **7 files passed, 50 tests passed** (23 baseline OIDC + 27 new/added SAML/merged tests).

Full-repo run after all changes:
→ 14 failed test files / 26 failed tests (**identical** to baseline — confirmed by exact arithmetic:
128 passed files = 125 + 3 new files; 1318 passed tests = 1291 + 27 new tests). No regressions.

Full-repo lint after all changes:
```
./node_modules/.bin/eslint .
```
→ **53 problems (34 errors, 19 warnings)** — byte-identical to the pre-flight baseline. Zero new lint
issues. Targeted lint of every new/changed file individually also came back clean:
```
./node_modules/.bin/eslint "app/(dashboard)/settings/sso/page.tsx" \
  "app/(dashboard)/settings/sso/__tests__/page.test.tsx" \
  components/settings/SamlConfigCard.tsx app/login/page.tsx \
  components/SamlSignInButton.tsx lib/api/saml.ts lib/samlErrors.ts
```
→ no output (clean).

Hardcoded-color grep on all new/changed files (`#[0-9a-fA-F]{3,8}|rgb\(`): no matches.

## Files changed (final inventory)

| File | Action |
|---|---|
| `lib/api/saml.ts` | create |
| `lib/api/__tests__/saml.test.ts` | create |
| `lib/samlErrors.ts` | create |
| `lib/__tests__/samlErrors.test.ts` | create |
| `components/SamlSignInButton.tsx` | create |
| `components/__tests__/SamlSignInButton.test.tsx` | create |
| `components/settings/SamlConfigCard.tsx` | create |
| `app/(dashboard)/settings/sso/page.tsx` | edit (3-line additive diff: import + `<SamlConfigCard isAdminOrOwner={isAdminOrOwner} />` after the OIDC `</Card>`) |
| `app/(dashboard)/settings/sso/__tests__/page.test.tsx` | edit (added SAML mocks/fixtures + 5-case SAML describe block scoped with `within(getByTestId('saml-config-card'))`; scoped the two now-ambiguous OIDC queries — `getAllByRole('switch')[0]` and `getAllByRole('button', {name: /^save$/i})[0]` — to index 0 since the OIDC card renders first in the DOM) |
| `app/login/page.tsx` | edit (mount `<SamlSignInButton />` next to `<OidcSignInButton />`; `sso_error` handler now tries `getSsoErrorMessage` first, falls through to `getSamlErrorMessage` when the code isn't OIDC-known) |
| `components/ui/textarea.tsx` | **not created** — already existed in the tree, reused as-is |

**Confirmed untouched** (verified via `git diff --stat` returning empty for all four):
`lib/api-client.ts`, `contexts/AuthContext.tsx`, `app/login/callback/page.tsx`, `components/AppSidebar.tsx`.

**Confirmed OIDC card byte-identical**: `git diff "app/(dashboard)/settings/sso/page.tsx"` shows a
pure 3-line addition (one import line + one JSX line); zero lines removed or modified inside the
existing OIDC `<Card>` markup or its handlers/state.

## Design notes / deviations from the plan

- Followed plan §5 branch (A): backend returns `cert_fingerprint` only, so the PEM textarea is
  write-only — blank on load, sends `idp_x509_cert` in the PUT only when non-empty, shows
  "A certificate is already stored ({fingerprint})..." helper text otherwise (mirrors OIDC's
  `secret_hint` pattern exactly).
- `SamlConfigCard` is a fully self-contained sibling component (own ~15 pieces of state, its own load/
  save/delete effect and Dialog), exactly as the plan's "strongly preferred" approach — this makes the
  "OIDC card untouched" claim mechanical rather than a careful-diff exercise.
- Page-test scoping: used `within(screen.getByTestId('saml-config-card'))` for all SAML-card
  assertions. Delete-confirm-dialog buttons are portaled (Radix `DialogPortal` → `document.body`), so
  those specific queries stay unscoped (`screen.findAllByRole(...)`) exactly like the pre-existing OIDC
  delete test does — documented inline in the test file.
- Login-page `sso_error` merge implemented inline (the plan's "minimal" option) rather than as a
  separate `resolveSsoError` helper with its own test file, since the plan states either is acceptable
  and no dedicated test file was requested for Phase D.

## Acceptance criteria check

- [x] Targeted `vitest run` green for all 4 new/extended SAML test files (27 new tests, 50 total in the
      SSO-related set).
- [x] `eslint .` clean relative to baseline (53/53, no new problems); all changed files individually
      lint-clean.
- [x] OIDC test count unchanged (23) and all still passing — regression guard confirmed both by direct
      re-run and by full-repo arithmetic (128 = 125 + 3 new files, 1318 = 1291 + 27 new tests).
- [x] Exactly one SSO button logic verified via `SamlSignInButton` test (enabled → renders + navigates
      to `/api/v1/auth/saml/login`; disabled/probe-reject → renders nothing) mirroring `OidcSignInButton`
      — both mounted on `/login`, each self-hides independently.
- [x] Config save/enable/delete round-trip covered against the mocked API contract; cross-provider 422
      renders the backend's detail message inline (with a friendly fallback baked into `handleSave`).
- [x] No hardcoded colors in any new/changed file (grep-verified).
