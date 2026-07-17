# Understanding — `oidc-sso` (Phase 2 dig)

**Date:** 2026-07-16 · **Branch:** `feat/oidc-sso` · **Source card:** `docs/planning/_card/card.md`

All paths below are in the worktree. Every claim is cited; where I could not verify something, it is
listed as an open question rather than asserted.

---

## 1. What the task is really asking

Let an operator of a **self-hosted** Rereflect deployment plug their own identity provider (Okta,
Azure AD, Google Workspace, Keycloak) into login via **OIDC**, without disturbing the two auth paths
that already work (password, Google). SAML is explicitly out of slice 1.

---

## 2. The headline finding — the "reuse the existing seam" premise is only half right

The handoff brief (and my own `rereflect-next` recommendation) said to reuse the Google OAuth seam at
`auth.py:179-278`. The dig shows that seam splits cleanly into two halves, and only one is reusable:

| Half | Reusable? | Evidence |
|---|---|---|
| **Identity → User → JWT** (find-or-create user, pick org, assign role, mint token) | **Yes** — near-exact template | `auth.py:191-236` (signup), `:251-280` (login) |
| **Transport** (how the identity arrives) | **Not from the *Google* path** — but a precedent exists elsewhere (see correction below) | Google is *token-based*: the frontend gets an access token via `@react-oauth/google` (`package.json:33`) and POSTs it; `verify_google_access_token(data.access_token)` (`auth.py:184`) verifies it by calling Google's userinfo endpoint (`google_auth.py:70-100`). No auth-code exchange, no redirect URI. |

### ⚠️ CORRECTION (2026-07-16, after the dig agents reported)

An earlier revision of this note claimed *"the transport half has no precedent — a redirect/callback
surface this app has never had."* **That is wrong.** The app already runs full OAuth
authorization-code flows with **backend** callbacks for integrations (Slack, Intercom, Linear,
Salesforce). The frontend hard-navigates to a backend-issued `auth_url`
(`settings/integrations/new/page.tsx:86,104`; `linear/page.tsx:343`; `salesforce/page.tsx:104`), the
IdP redirects to a **backend** callback, and the backend redirects back to a client page.

**`salesforce_integration.py:104-120` is the closest analogue and a direct template for OIDC:**
- `_app_secret()` (`:109-111`) reuses the app-wide `JWT_SECRET` to sign a **stateless `state`** param —
  the comment at `:106-108` explains the rationale (no server-side session; works across worker processes).
- `STATE_TTL_SECONDS = 600` (`:114`).
- `SF_OAUTH_NONCE_COOKIE` (`:117-120`) — an **HttpOnly cookie scoped to the callback path**, binding
  `state` to the initiating browser. Tagged **SEC-1**.
- `_frontend_url()` (`:102-103`) — redirect target from the `FRONTEND_URL` env var.

**Consequence (revised):** D3 (backend callback) is **not** novel — copy the Salesforce state/nonce
pattern. What remains genuinely new is narrower: (a) the callback must hand a **token** back to an
**unauthenticated** browser (the integration flows all run with an existing Bearer session, so they only
pass an error code back), and (b) there is **no OIDC discovery/JWKS client** anywhere
(`google_auth.py` delegates all of that to `google-auth`).

Still true: **no Next.js route handler exists** — `find app -name "route.ts*"` → zero matches.
`middleware.ts` does **no auth work** (`:5-30`). The JWT lives in `localStorage`
(`contexts/AuthContext.tsx:53,100,106`), so a backend callback **cannot write it** — the token must
cross back through the URL to client JS. A **fragment** avoids history/referrer leakage that a query
param would cause.

---

## 3. What is already in our favour (no blocker found)

- **`password_hash` is already nullable** — `user.py:12`, commented *"Nullable for Google-only users"*.
  A password-less SSO user is already a supported shape. **No migration fight.**
- **An external-identity pattern already exists** — `user.py:18-19`: `google_id` (unique, nullable,
  indexed) + `auth_provider` (`String(50)`, default `"email"`, values `email | google | both`).
  OIDC plausibly adds an `oidc_sub` column and an `"oidc"` value, mirroring rather than reshaping.
- **A shared secret-storage helper exists and is the obvious home for `client_secret`** —
  `src/utils/encryption.py`: Fernet `encrypt_api_key` / `decrypt_api_key` / `get_key_hint`, keyed off
  the `LLM_ENCRYPTION_KEY` env var (`encryption.py:11-35`). Already used by `org_api_key`,
  `jira_integration`, `zendesk_integration`, `hubspot_integration`, `salesforce_integration`,
  `asana_integration`, `linear_integration`, `webhook_endpoint`. **Reuse, do not invent.**
- **`httpx==0.25.2` is present** (`requirements.txt`) and the Google path is already `async def`
  (`auth.py:180,240`) — discovery + JWKS fetches fit the existing style.
- **Alembic is single-head**: `alembic heads` → **`b8c9d0e1f2a3 (head)`** (run live, 2026-07-16).
  Any static claim of multiple heads is the known parse artifact — ignore it.
- **`authlib` is absent** — confirmed `grep -ic '^authlib' requirements.txt` → `0`. Present and
  relevant: `python-jose[cryptography]==3.3.0`, `passlib[bcrypt]==1.7.4`, `cryptography>=43.0.0`
  (whose own comment reads *"Fernet symmetric encryption for LLM API keys"*).

---

## 4. Contradictions between the brief and the code (flagged, not papered over)

1. **"Reuse the seam at auth.py:179-278" understates the work.** The transport half has no precedent
   (§2). The brief's framing implies a smaller change than reality. Not a blocker — but the PRD must
   own the callback design rather than treat it as inherited.
2. **The brief says "no OIDC library is installed → add authlib or hand-roll".** True, but it missed
   that `python-jose` is *already* the JWT library in use for our own tokens, and it can verify a
   third-party ID token against a JWKS. So "hand-roll" is less exotic than it sounds — the real
   question is auth-code exchange + state/PKCE plumbing, not signature verification.
3. **The org-mapping question has a strong existing precedent the brief did not know about.**
   `google_login` **does not auto-provision**: unknown email → `404 "No account found with this email.
   Please sign up first."` (`auth.py:257-261`). Only `google_signup` creates a user, and it creates a
   **brand-new Organization** with `role="owner"` (`auth.py:207-224`). So today's answer to "which org
   does an external-identity user land in?" is *"one they were already invited into, or a new org they
   own."* Enterprise SSO normally expects **JIT provisioning**, which this codebase has never done.
   This sharpens Q2 rather than answering it.

---

## 5. Account linking — ⚠️ CORRECTED, no vulnerability exists

An earlier revision of this note claimed `google_login` *"silently links accounts on email match…
without consulting an `email_verified` claim"* and called it an account-takeover shape. **That was
wrong, and the claim is withdrawn.**

`auth.py:264-268` does link on email match — but `email_verified` is enforced **upstream, inside the
verifier**: `verify_google_access_token` returns `None` when the userinfo response lacks
`email_verified` (`google_auth.py:92-94`), and `auth.py:185-189` turns `None` into a 401. An unverified
identity therefore never reaches the linking code. `google_auth.py:26-52` (the `id_token` path) checks
`email_verified` at `:52` as well.

**Revised bearing on D6:** requiring `email_verified: true` for OIDC linking is **matching the existing
precedent**, not closing a hole. It remains the right call — an arbitrary operator-configured issuer is
a weaker guarantee than Google, so the check must be explicit in *our* code rather than inherited from
a vendor library — but the PRD must not claim it fixes a bug. It does not.

---

## 6. Open questions the dig cannot answer — these are for the interview

**Q1 (design, load-bearing). Where does the OIDC callback land?**
No callback surface exists (§2). Options: (a) a Next.js client page `/login/callback` that reads
`?code` and POSTs it to the backend, closest to today's "frontend obtains credential → POSTs it"
shape; (b) a backend `GET /auth/oidc/callback` that completes the exchange and redirects to the
frontend with the JWT — safer (secret + code never touch the browser) but introduces the app's first
server-side redirect handoff, and the JWT lands in a URL fragment. Needs a decision.

**Q2 (product, load-bearing). Does SSO auto-provision (JIT), and into which org, at what role?**
Precedent says no auto-provision (§4.3). Choices: invite-only (safest, matches precedent, but every
SSO user still needs a manual invite — arguably defeating the point); JIT into a *designated* org at a
default role; or email-domain → org match. Note the hard constraint: `email` is **globally unique**
(`user.py:11`) and `organization_id` is a **non-null FK** (`user.py:13`) — **a user belongs to exactly
one org**, so "which org" has exactly one answer per user and cannot be deferred to runtime choice.

**Q3 (scope). Per-org config or per-deployment config?**
Multi-tenancy is explicitly preserved (`PRD-OSS-SELF-HOSTED-PIVOT.md:43`, D6), and every existing
integration is per-org (`*_integration` tables). But a self-hosted deployment usually has one IdP for
the whole instance. Per-org (a table, following precedent) vs env-var (simpler, matches "one
deployment, one IdP"). Precedent favours per-org; simplicity favours env.

**Q4 (security). Can an operator require SSO / disable password login?**
Enterprise operators expect it; it conflicts with the additive-only constraint unless opt-in and
lockout-guarded (disabling passwords with a misconfigured IdP bricks the deployment).

**Q5 (integration). How does SSO interact with the invite flow** in `routes/team.py`? If invite-only
(Q2), an invited-but-never-logged-in user must be matchable by email at first SSO login.

**Q6 (dependency).** `authlib` vs hand-rolled on `httpx` + `python-jose`. Adding a dep to an auth path
deserves an explicit call; hand-rolling PKCE/state deserves one too.

**Q7 (SSRF) — RESOLVED by the dig, but it surfaces a choice.** The issuer/discovery URL is
**operator-supplied and fetched server-side** — the exact shape Jira/Zendesk hardened against. There
is **no shared helper**: `_assert_host_not_ssrf(host: str) -> None` is **duplicated** as a private
function in `routes/jira_integration.py:195` **and** `routes/zendesk_integration.py:185`. So OIDC
would be the **third** copy. The PRD should decide: add a third copy (consistent with precedent, more
duplication) or extract a shared helper (better, but touches two shipped integrations — scope creep on
an auth PR). **Lean: extract, with characterization tests on both existing call sites.**

---

## 7. Affected areas (services)

- **`services/backend-api`** — primary. `routes/auth.py` (additive endpoints), `models/user.py` (+`oidc_sub`?),
  a new config model/table or env, `alembic/` (one migration off head `b8c9d0e1f2a3`),
  reuse `utils/encryption.py`.
- **`services/frontend-web`** — login page button, possibly a new callback route (Q1), `AuthContext`,
  `lib/api/`. `middleware.ts` currently does no auth work and may or may not need to.
- **`services/worker-service`, `services/analysis-engine`** — **not affected**.

## 8. Testing notes

- Backend tests: `pytest tests/ -v` in `services/backend-api`. Known repo gotcha: a pre-existing
  full-suite segfault (`test_report_ws.py`) — **scope test runs; do not trust bare full-suite green.**
- An IdP under test is needed. **`docker-compose.yml` and `docker-compose.prod.yml` both exist at the
  repo root** (verified), so adding a Keycloak service for integration tests is viable. For unit tests,
  mocking `httpx` against a fake discovery/JWKS is lighter and likely the right default — reserve live
  Keycloak for one end-to-end happy-path test.
- Frontend: `npm run test` + `npm run lint` in `services/frontend-web`.

---

## 9. Additional findings from the dig agents (2026-07-16)

**Conventions to follow (from `dig-secrets-config`, verified against the cited files):**
- **Encrypt in the ROUTE layer, never the model** — stated at `models/zendesk_integration.py:6-8`.
- **A missing `LLM_ENCRYPTION_KEY` → HTTP 422, never a 500** — `routes/jira_integration.py:373,398-400`;
  documented at `routes/asana_integration.py:23-25`. Secrets are never echoed in responses
  (`jira_integration.py:376`).
- Ciphertext lives in a `Text` column beside an optional `String(8)` hint (`get_key_hint`), e.g.
  `models/org_api_key.py:12-13,19`, `models/salesforce_integration.py:27,30`.
- **No pydantic Settings layer exists** — config is bare `os.getenv` at module scope with an inline
  default (84 occurrences); canonical: `api/auth.py:11-12`. `SELF_HOSTED` is read in exactly one place,
  `config/plans.py:21-22`, defaulting to `true`.
- Routes are **overwhelmingly sync `def`**; `httpx.Client` (sync) dominates outbound calls. `auth.py`'s
  Google endpoints are among the rare `async def`.

**Risks raised (from `dig-secrets-config`):**
- Both `_assert_host_not_ssrf` copies derive much of their safety from a **hardcoded vendor host suffix**
  (`*.atlassian.net`, `*.zendesk.com`, asserted client-side in `services/jira_client.py:76-94`). **An OIDC
  issuer is arbitrary operator input, so the suffix half has no analogue** — the DNS/private-IP half must
  carry the whole load.
- The existing gate resolves DNS, then `httpx` **independently re-resolves on connect** — a **TOCTOU
  window**; nothing is pinned. Pre-existing, inherited by any third copy.
- **Dev `docker-compose.yml` sets neither `LLM_ENCRYPTION_KEY` nor `SELF_HOSTED`** (`:45-53`), so any route
  calling `encrypt_api_key` returns 422 in dev compose today. Affects local testing of D4.

**Risks raised (from `dig-frontend-auth`):**
- **There are zero tests for login, signup, `AuthContext`, `api-client`, or `GoogleSignInButton`** —
  `contexts/__tests__/` holds only `ThemeContext.test.tsx`. The "strictly additive / don't break password
  login" constraint has **no characterization tests protecting it**. Under the pipeline's TDD rule these
  must be written **first**. This is the single biggest execution risk.
- **Token writes are duplicated in 4 places and all bypass `AuthContext.login()`** (`login/page.tsx:85,102`;
  `signup/page.tsx:141,175`). A new auth path becomes a fifth unless consolidated.
- **`AuthContext` route lists are hardcoded** (`:28-34`) — a `/login/callback` page **must** be added to
  `publicRoutes` or the provider bounces it to `/login` before the token is ever stored.
- **`NEXT_PUBLIC_*` is build-time inlined**, which conflicts with a self-hoster configuring OIDC at runtime
  without rebuilding. **D4 (config in the DB) sidesteps this**: the frontend must learn "is SSO enabled?"
  from a backend endpoint at runtime, not from a `NEXT_PUBLIC_` var. Note `NEXT_PUBLIC_GOOGLE_CLIENT_ID`
  is used in 4 files yet is **absent from `.env.example`** — do not repeat that for OIDC.
- Conditional-mount is an established idiom for an optional auth backend (`app/providers.tsx:28`,
  `GoogleSignInButton.tsx:98`, `login/page.tsx:317`) — an OIDC button should follow it exactly.
- Naming trap: the existing prop is called `credential` but carries an **OAuth access token, not an OIDC
  `id_token`** (`GoogleSignInButton.tsx:7`). Do not let the name imply the shapes already match.

## 10. Process note (honesty)

Phase 2 was dispatched to three read-only agents per the pipeline's agents-team requirement. They
initially appeared to return nothing and an earlier revision of this note recorded that *"all three idled
without returning any findings… the agent fan-out contributed nothing."* **That was wrong and is
withdrawn.** All three had completed their research and emitted it as plain text rather than via the
message channel, so it did not route; on re-request they resent in full. Their reports **corrected two
substantive errors** in the lead's own dig (§2 transport precedent, §5 the withdrawn vulnerability claim)
and supplied §9 wholesale. Facts in §§1-8 were verified first-hand by the lead; §9 is the agents' work,
spot-checked against the cited files.
