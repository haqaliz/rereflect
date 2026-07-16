# Aspect Spec — `auth-test-harness`

**Feature:** `oidc-sso` · **Aspect:** `auth-test-harness` · **PRD:** `../prd.md` (M1)
**Status:** Draft → ready to plan · **Date:** 2026-07-16

---

## Problem slice & user outcome

The OIDC feature's load-bearing constraint is **strictly additive — password login and Google login
must not change behaviour** (PRD S4). Before any OIDC production code is written, we need a green,
trustworthy characterization net around the **current** auth behaviour, so that any regression
introduced by the OIDC work fails a test loudly. Outcome: a developer (or agent) building the OIDC
flow gets an immediate RED if they perturb the existing paths.

## ⚠️ Reality correction (verified 2026-07-16, supersedes PRD R3)

The PRD's R3 says *"no tests exist for login, signup, AuthContext, api-client, or GoogleSignInButton."*
**That is true only for the frontend.** The backend is already well-covered — R3 over-generalised a
frontend-only dig finding. Verified in the worktree:

- `services/backend-api/tests/test_auth.py` — **21 tests**: `TestSignup`, `TestLogin`, `TestGetMe`,
  `TestGoogleSignup`, `TestGoogleLogin`. The email-linking path is **already** covered
  (`test_google_login_links_email_account:322` asserts `auth_provider == "both"` at `:345`), as is the
  different-Google-account rejection (`:382`).
- `services/backend-api/tests/conftest.py` — full harness already exists: `client`, `db` (SQLite,
  `create_all`/`drop_all` per function), `test_organization`, `test_user`, `auth_headers`,
  `test_user_token`, autouse `_disable_emails`.
- `services/frontend-web/vitest.config.ts` + `vitest.setup.ts` exist; `contexts/__tests__/` holds only
  `ThemeContext.test.tsx` — **no auth tests**.

**Net:** backend M1 is *verify + fill small gaps*, not *build a harness*. The frontend is the real
work, but the Vitest infra already exists — this is writing tests, not standing up infrastructure.
The PRD's "M1 may dwarf the feature" sizing worry is **materially reduced** and should be treated as
resolved-downward.

## In-scope

**Backend (fill the specific gaps only):**
1. Characterize the **password-null branch**: a Google-only user (`password_hash IS NULL`) attempting
   password login → 401 with the "uses Google Sign-In" message (`auth.py:74-78`). Confirm/​add.
2. Characterize **`email_verified` enforcement** in `verify_google_access_token` /
   `verify_google_token` (`google_auth.py:92-94`, `:52`): unverified userinfo → `None` → the route
   returns 401. This is the invariant D6 relies on — pin it explicitly at the service level.
3. Confirm the JWT claim shape `{user_id, organization_id, role}` is asserted somewhere; if only
   implicitly, add one explicit assertion (OIDC will mint the same shape — M8).

**Frontend (the actual work — all new):**
4. `contexts/AuthContext.tsx`: token read from `localStorage` on mount (`:53`), `login()` stores +
   sets state (`:100`), `logout()` clears (`:106`), invalid-token path clears + redirects (`:82-90`),
   unauthenticated `(dashboard)` access pushes to `/login` (`:60-62`). Use the `ThemeContext.test.tsx`
   pattern as the template.
5. `lib/api-client.ts`: the `Authorization: Bearer` interceptor (`:19-21`), and the 401 interceptor's
   `window.location.href = '/login'` with its skip-list (`:41-46`).
6. `components/GoogleSignInButton.tsx`: self-hides when unconfigured (`:14,96-100`); on success passes
   `access_token` to its caller (`:29`).
7. `app/login/page.tsx` + `app/signup/page.tsx`: the password submit path and the Google callback path
   (`login/page.tsx:85,101`; `signup/page.tsx:141,171`) — enough to catch a regression, not exhaustive.

## Out-of-scope

- Any OIDC production code or OIDC tests (later aspects).
- Refactoring the 4 duplicated `localStorage` writes into `AuthContext.login()` (that's PRD S-2, done
  in `oidc-frontend` where the 5th write would otherwise appear).
- Backend fixture/harness changes — it already exists and works.
- Exhaustive coverage of every login-page branch — this is a regression net, not a coverage push.
- Fixing the pre-existing `test_report_ws.py` segfault (PRD R7) — just scope around it.

## Acceptance criteria (testable)

- **AC1** — `pytest tests/test_auth.py -v` (and any new backend auth test file) is **green**, and
  includes explicit tests for: password-null → 401 Google message; `email_verified: false` → rejected.
- **AC2** — `npm run test` in `services/frontend-web` is **green** with new tests for `AuthContext`
  (login/logout/mount-restore/invalid-token-redirect), `api-client` (Bearer attach + 401 redirect),
  and `GoogleSignInButton` (hide-when-unconfigured + success-passes-token).
- **AC3** — `npm run lint` is clean.
- **AC4** — Every new test asserts **current** behaviour and passes on `HEAD` **before** any OIDC code
  exists (true characterization — no test depends on unbuilt OIDC).
- **AC5** — The plan explicitly names which backend gaps were already covered (skip) vs newly added, so
  no effort is spent re-testing what `test_auth.py` already asserts.

## Dependencies & sequencing

- **Blocks:** every other `oidc-sso` aspect (this is the safety net; PRD makes it a hard prerequisite).
- **Blocked by:** nothing. Can start immediately.
- Runs entirely on existing infra (backend `conftest.py`, frontend `vitest.config.ts`).

## Open questions / risks

- **OQ1** — Does `test_auth.py` already assert the password-null branch? The plan's first step is to
  read it fully and mark each backend gap **covered/absent** before writing, per AC5. (I saw the
  branch in `auth.py:74-78` but did not confirm a matching test.)
- **R1** — Frontend tests for Next.js App-Router client components under Vitest/jsdom can be fiddly
  (`useRouter`, `window.location`). Mitigation: follow `ThemeContext.test.tsx`; mock `next/navigation`.
  Budget iteration here — it's the one genuinely uncertain part.
- **R2** — `window.location.href` assignment (api-client `:46`) is hard to assert in jsdom. Mitigation:
  spy on a wrapper or stub `window.location`; if it proves brittle, assert the interceptor's decision
  (skip-list membership) rather than the navigation side-effect, and note the limitation.
