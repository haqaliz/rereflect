# PRD — OIDC Single Sign-On (self-hosted)

**Slug:** `oidc-sso` · **Branch:** `feat/oidc-sso` · **Type:** feat
**Status:** Draft — pending review gate
**Date:** 2026-07-16
**Source:** freeform — `rereflect-next` handoff. **No GitHub issue** (`gh issue list --search "sso OR oidc OR saml"` → No Issues).
**Inputs:** `docs/planning/_card/card.md` (brief), `docs/planning/oidc-sso/understanding.md` (Phase 2 dig).

---

## 1. Problem Statement

An operator running a self-hosted Rereflect instance cannot connect their identity provider to login.
Their team authenticates with per-user passwords (`auth.py:61`) or Google (`auth.py:239`) — neither of
which an enterprise IT function will accept as the access path to an internal analytics tool. There is
no way to centralise account lifecycle, enforce the IdP's MFA, or de-provision a departing employee.

**Evidence it's real — stated honestly, because it is thin:**

| Signal | Reality |
|---|---|
| A user asked for it | **No.** No GitHub issue exists. |
| A PRD scoped it | **No.** grep `SSO\|SAML\|OIDC\|single sign\|SCIM` across all 17 root `PRD-*.md` + all 25 `docs/planning/*/prd.md` → **zero hits**. |
| The roadmap names it | **Yes**, unchecked: `DEV-TRACKING.md:168` — "SSO/SAML (Okta, Azure AD, Google Workspace)". |
| Users are blocked today | **No.** `PRD-OSS-SELF-HOSTED-PIVOT.md:45` (D8): **"Pre-launch, no real users."** |

**This is a bet on future self-host evaluators, not a response to reported demand.** It was challenged
on exactly that basis during the interview and the decision to proceed was taken with the challenge
visible (§9, D1). The argument for building it now: SSO is a table-stakes checkbox an enterprise
evaluator looks for on day one, and for an MIT-licensed self-hosted tool, shipping it **unlocked** is
the "no SSO tax" posture — the opposite of the open-core norm. The counter-argument, recorded rather
than buried: it serves nobody today, and the nearest alternative (the M5.3 label-gate re-derivation)
defends the product's actual killer feature.

**Cost of the status quo:** zero today; a lost evaluation later, at the moment we can least afford one.

---

## 2. Acceptance Criteria (correctness-only — see the honesty note)

**Goal:** an operator can point a self-hosted deployment at their OIDC IdP and have their team log in,
without either of the existing auth paths changing behaviour.

**Honesty note (from the self-critique):** every item below is a **correctness** test — it proves the
feature *functions*, not that it *mattered*. §1 already establishes there is no user and no way to
measure value without fabricating a number. **This feature ships on faith.** We deliberately set no
adoption target. The one honest **tripwire** (a signal, not a KPI): the first external operator who
configures SSO against a real IdP. Until that happens, "success" means only "correct and additive."

| # | Acceptance criterion | Verified by |
|---|---|---|
| S1 | An operator configures issuer + `client_id` + `client_secret` and enables SSO | Integration test: `PUT` config → `GET` status returns `enabled: true`, secret never echoed |
| S2 | A first-time SSO user reaches the dashboard with no prior invite | E2E: unknown email **within an allowed domain** → user created in the configured org, `role="member"`, valid JWT |
| S3 | A returning SSO user logs in and is matched by stable subject, not email | Test: same `sub`, changed email → same `User` row |
| S4 | **Password login and Google login remain byte-for-byte unchanged** | **Characterization tests written FIRST** (RED) and green throughout |
| S5 | An IdP asserting `email_verified: false` cannot take over an existing account | Test: existing password user + unverified SSO identity → 403, no link |
| S6 | A malicious/hostile issuer URL cannot reach internal network | Test: issuer resolving to loopback/private/link-local → 422 |
| S7 | An identity **outside** the configured domain allowlist is never provisioned | Test: verified identity, out-of-list domain → 403, no `User` created (M12) |

---

## 3. Personas & Scenarios

- **Operator (owner/admin)** — self-hosts Rereflect for their company. Wants their IdP wired in and
  their team logging in with corporate credentials. Configures SSO once in settings.
- **Team member** — clicks "Sign in with SSO", is bounced to their IdP, lands on the dashboard. Has
  never heard of Rereflect's password system and should never need to.
- **Evaluator** — checks whether SSO exists before a pilot. Failing this check is silent and fatal.

**Primary scenario:** operator enables SSO → shares the login URL → a colleague with no Rereflect
account clicks "Sign in with SSO" → authenticates at the IdP → is auto-provisioned into the operator's
org as `member` → lands on the dashboard.

---

## 4. Decisions (locked in the interview)

| # | Decision | Rationale / precedent |
|---|---|---|
| **D1** | Build OIDC SSO now, pre-launch | Table stakes for evaluation; accepted with the "serves no current user" challenge heard (§1) |
| **D2** | **JIT auto-provision**, default role **`member`** | Enterprise SSO means JIT; invite-only would leave operators hand-inviting everyone. **New behaviour** — `google_login` 404s on unknown email (`auth.py:257-261`) |
| **D3** | **Backend** `GET /auth/oidc/callback`, then redirect to the frontend with the JWT in a **fragment** | Secret + code never touch the browser. Direct precedent: `salesforce_integration.py:104-120` |
| **D4** | Config in a **per-org table**; `client_secret` **Fernet-encrypted** | Follows every `*_integration` table; preserves multi-tenancy (`PRD-OSS-SELF-HOSTED-PIVOT.md:43`, D6). Reuses `utils/encryption.py:19-28`. Also dodges the build-time `NEXT_PUBLIC_*` trap (§7.4) |
| **D5** | At most **one *enabled* config per deployment** (slice 1) | `/auth/oidc/start` needs no org hint; **the config row's org IS the JIT target org**, which resolves D2 with no extra mechanism. Relax when a real multi-org operator appears |
| **D6** | Link to an existing account **only if `email_verified: true`**, else **403** | **Matches** existing behaviour (`google_auth.py:92-94` rejects unverified upstream). *Not* a bug fix — see §7.1 |
| **D7** | **Add `authlib`** | No OIDC discovery/JWKS client exists anywhere; `google_auth.py` delegates it to `google-auth`. Hand-rolling PKCE/state/nonce/clock-skew is where auth bugs live |

---

## 5. Requirements

### Must-have

- **M1 — Characterization tests first.** Before any production code: tests pinning the **current**
  behaviour of password login (`auth.py:61`), Google login/signup (`auth.py:179,239`), and
  `AuthContext`. **There are currently zero tests for any of these** (§7.5). This is the RED that
  protects S4 and is a hard gate on everything below.
- **M2 — Config model + migration.** `oidc_config` table, per-org, one migration off head
  **`b8c9d0e1f2a3`** (verified live). `client_secret` Fernet-encrypted with a `secret_hint`.
  A partial unique index enforcing **at most one `enabled=true` row per deployment** (D5).
- **M3 — Config API.** Admin/owner-gated CRUD (`require_admin_or_owner`). Encrypt **in the route
  layer, never the model** (`models/zendesk_integration.py:6-8`). Missing `LLM_ENCRYPTION_KEY` →
  **422, never 500** (`routes/jira_integration.py:373,398-400`). **Never echo the secret**
  (`jira_integration.py:376`).
- **M4 — Public status endpoint.** Unauthenticated `GET /auth/oidc/status` → `{enabled, button_label}`.
  Required because `NEXT_PUBLIC_*` is build-time inlined and cannot carry runtime config (§7.4).
  Must leak nothing beyond whether SSO is on.
- **M5 — `GET /auth/oidc/start`.** Builds the authorize URL via discovery; signs a stateless `state`
  with `JWT_SECRET` (`salesforce_integration.py:109-111`), TTL 600s (`:114`); sets an **HttpOnly,
  path-scoped nonce cookie** (`:117-120`, SEC-1); PKCE.
- **M6 — `GET /auth/oidc/callback`.** Validates `state` + nonce cookie, exchanges the code
  server-side, validates the `id_token` (signature via JWKS, `iss`, `aud`, `exp`, `nonce`), then
  redirects to the frontend with the internal JWT **in a URL fragment** (never a query param —
  fragments stay out of history, referrers, and server logs).
- **M7 — Identity resolution.** Match on **`oidc_sub` first** (stable), then email. New columns on
  `users`: `oidc_sub` (unique, nullable, indexed) + `"oidc"` as an `auth_provider` value, mirroring
  `google_id`/`auth_provider` (`user.py:18-19`). `password_hash` is **already nullable** (`user.py:12`).
- **M8 — JIT provisioning (D2).** Unknown verified identity **that passes M12** → create `User` in the
  enabled config's org, `role="member"`, `auth_provider="oidc"`, `joined_at=utcnow()`. Mint the JWT with
  the existing claim shape `{user_id, organization_id, role}` (`auth.py:230-234`).
- **M12 — Domain allowlist on JIT (default-deny).** The config carries `allowed_email_domains` (list of
  strings). JIT provisioning (M8) and linking (M9) proceed **only** if the verified email's domain is in
  the list; otherwise **403, no `User` created, no link**. **An empty list means deny-all**, not
  allow-all — an operator must name at least one domain for SSO to provision anyone. This mirrors the
  repo's own **default-deny** precedent (`crm-churn-labels`, `_card` note: "an org that names nothing
  produces nothing"). Rationale: without it, an operator who points the issuer at a multi-tenant endpoint
  (Google's own OIDC, or an Azure AD app scoped to "any organizational directory") auto-provisions **every
  Google/Microsoft account on earth** into their org — every one satisfies `email_verified: true`. This is
  the M8+D2 mass-provisioning hole (R4) closed at the requirement level, not left to operator vigilance.
- **M9 — Linking (D6).** Existing email + `email_verified: true` → link (`auth_provider="both"`,
  set `oidc_sub`). `email_verified` false/absent → **403, no link, no login**.
- **M10 — SSRF gate on the issuer URL.** Operator-supplied and fetched server-side. **The hardcoded
  vendor-suffix half of the existing pattern has no analogue** — the DNS + private/loopback/link-local
  check must carry the whole load (§7.2).
- **M11 — Frontend.** Conditional "Sign in with SSO" button driven by M4, following the established
  conditional-mount idiom (`app/providers.tsx:28`, `GoogleSignInButton.tsx:98`). A `/login/callback`
  page reads the fragment, stores the token, redirects. **It must be added to `AuthContext`'s
  hardcoded `publicRoutes`** (`:28-34`) or the provider bounces it before the token is ever stored
  (§7.6). Settings page for config (admin/owner).

- **M13 — Operator docs (config-driven feature = docs ARE the surface).** `.env.example` entries and a
  `SELF_HOSTING.md` section: how to register the client with the IdP, the callback URL to whitelist, the
  `allowed_email_domains` semantics (deny-all-when-empty), and a "verify it works" note. **Promoted from
  should-have to must-have in the self-critique**: in a self-hosted product an undocumented config-driven
  feature is undiscoverable, which collapses the entire §1 "evaluator checks on day one" rationale. The
  PRD already notes `NEXT_PUBLIC_GOOGLE_CLIENT_ID` is used in 4 files yet **absent from `.env.example`** —
  proof this exact miss already happened once. Do not repeat it.

### Should-have

- **S-1 — Extract a shared SSRF helper.** `_assert_host_not_ssrf` is already **duplicated** verbatim
  (`jira_integration.py:195-223`, `zendesk_integration.py:185-213`); OIDC makes a **third** copy.
  Extracting to `src/utils/` is right, but it touches two shipped integrations from an auth PR —
  **requires characterization tests on both existing call sites first.** If that cost isn't paid,
  add the third copy and log the debt. Decide in `tech-plan`.
- **S-2 — Consolidate token writes.** Four call sites write `localStorage` directly, bypassing
  `AuthContext.login()` (`login/page.tsx:85,102`; `signup/page.tsx:141,175`). M11 would be a fifth.
- **S-4 — Keycloak in `docker-compose.yml`** for one end-to-end happy-path test.

  *(Former S-3 docs → promoted to M13, must-have.)*

### Nice-to-have

- **N-1** — Group/role claim → Rereflect role mapping (beyond the `member` default).
- **N-2** — RP-initiated logout (would need both logout implementations: `AuthContext.logout` and
  `authAPI.logout`).
- **N-3** — `secret_hint` display + a "test connection" button, mirroring the CRM settings cards.
- **N-4** — Provisioning defence-in-depth: an audit-log entry per JIT-created user + a rate cap
  (deferred from R4; M12 is the primary control).

### Sizing note (from the self-critique)

No formal estimate, but one sequencing call the plan must make: **M1 (characterization tests) may rival
or exceed the OIDC work itself** — it means building a trustworthy test harness around password login,
Google login/signup, and `AuthContext`, all of which have **zero existing tests** (R3). `tech-plan` must
size M1 as its own slice and decide whether it lands as a **prerequisite PR** before any OIDC code, or
as the first phase of this branch. It is a hard prerequisite either way (it is the only thing protecting
S4 / the additive-only constraint).

---

## 6. Technical Considerations

**Services changed:** `services/backend-api` (primary), `services/frontend-web`.
**Not touched:** `services/worker-service`, `services/analysis-engine`.

**Data model** — new `oidc_config` (per-org, D4/D5) and two additive `users` columns (M7). One
migration off `b8c9d0e1f2a3`. **Multi-tenancy:** `email` is globally unique (`user.py:11`) and
`organization_id` is a non-null FK (`user.py:13`) — **a user belongs to exactly one org**, so "which
org" has exactly one answer per user; D5 makes that answer the enabled config's org.

**API contracts (additive; no existing endpoint changes):**

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/auth/oidc/status` | public | `{enabled, button_label}` (M4) |
| GET | `/api/v1/auth/oidc/start` | public | 302 → IdP authorize (M5) |
| GET | `/api/v1/auth/oidc/callback` | public | 302 → frontend `#token=…` (M6) |
| GET/PUT/DELETE | `/api/v1/settings/oidc` | admin/owner | Config CRUD (M3) |

**Conventions (from the dig — follow, don't reinvent):** encrypt in the route layer; ValueError → 422;
config via bare `os.getenv` at module scope (**there is no pydantic Settings layer**;
canonical `api/auth.py:11-12`). Routes are overwhelmingly sync `def` with sync `httpx.Client`, but
`auth.py`'s Google endpoints are `async def` — **follow `auth.py`'s local async style**, since that's
the file being extended.

**Non-functional:** discovery/JWKS responses must be cached with a bounded TTL (an uncached JWKS fetch
per login is a DoS amplifier against the IdP); all failures must be generic at the login surface (no
issuer internals leaked to an unauthenticated caller).

---

## 7. Risks & Open Questions

**R1 — I asserted a vulnerability that does not exist (corrected).** An earlier dig revision claimed
Google login links accounts without checking `email_verified`. **False**: `verify_google_access_token`
rejects unverified identities upstream (`google_auth.py:92-94`), so `auth.py:264` is never reached with
one. D6 **matches** precedent rather than fixing a bug. Recorded so no one re-derives a phantom CVE.

**R2 — The SSRF gate does not transfer cleanly.** Both copies lean on a hardcoded vendor suffix
(`*.atlassian.net`, `*.zendesk.com`; `services/jira_client.py:76-94`). An OIDC issuer is arbitrary, so
only the DNS/private-IP half applies — and it has a **known TOCTOU window** (it resolves, then `httpx`
re-resolves on connect, pinning nothing). **Pre-existing, inherited, not introduced here.** Slice 1
should match the existing bar and log the TOCTOU debt, not silently pretend it's closed.

**R3 — Zero tests protect the constraint this feature is built on (highest execution risk).** No tests
exist for login, signup, `AuthContext`, `api-client`, or `GoogleSignInButton`; `contexts/__tests__/`
holds only `ThemeContext.test.tsx`. "Additive only, don't break password login" is currently guarded by
nothing. **M1 exists to fix this and is a hard gate.**

**R4 — JIT provisioning is new behaviour with no user to validate it against (D1 + D2 compounding).**
Anyone the IdP vouches for could get an account. The mass-provisioning hole — a misconfigured issuer
pointed at a multi-tenant endpoint auto-provisioning every Google/Microsoft account — is **now closed at
the requirement level by M12 (domain allowlist, default-deny)**, added in the self-critique. Remaining
residual: an operator who both misconfigures the issuer *and* lists an over-broad domain (e.g.
`gmail.com`) can still over-provision. That is a genuine operator error the product cannot fully prevent;
M13 docs must call it out. Further defence-in-depth (a provisioning audit log / rate cap) is **N-4**,
deferred. Residual accepted, but no longer resting on operator vigilance alone.

**R5 — Dev compose can't exercise D4 today.** `docker-compose.yml:45-53` sets neither
`LLM_ENCRYPTION_KEY` nor `SELF_HOSTED`, so `encrypt_api_key` returns 422 in dev compose. Must be added
or config tests fail for an unrelated reason.

**R6 — Token-in-fragment is the weakest link.** A backend callback cannot write `localStorage`, so the
JWT must cross through the URL. A fragment is the best available (no referrer/history/server-log
leakage), but it is briefly in the browser URL and readable by any script on the page. Alternative — an
HttpOnly cookie — is a **larger change**: `api-client.ts:19-21` attaches `Authorization: Bearer` from
`localStorage` app-wide. Out of scope; flagged.

**R7 — Full-suite green is not trustworthy.** Known pre-existing segfault in `test_report_ws.py`.
**Scope test runs to the touched areas.**

**Open questions for `tech-plan`:** S-1 (extract vs third copy); JWKS cache TTL + where it lives;
whether the Google path should later be refactored onto the OIDC seam (**not now** — additive only).

---

## 8. Out of Scope

- **SAML** — a separate, heavier slice. OIDC covers Okta, Azure AD, Google Workspace, Keycloak.
- **SCIM / directory provisioning + de-provisioning.**
- **"Require SSO" / disabling password login** — operators will want it, but disabling passwords against
  a misconfigured IdP **bricks a deployment**, and it contradicts the additive-only constraint. Needs its
  own slice with a lockout guard.
- **Multi-org SSO** — deferred by D5 (one enabled config per deployment).
- **Any changes to the Google or password paths** — additive only.
- **Any plan gating** — all features unlocked post-pivot (`AI-TRACKING.md:250-256`). The `sso_saml`
  feature ID at `config/plans.py:203` is a **stale pre-pivot artifact**; do not wire to it.
- **Migrating the JWT off `localStorage`** (R6).

---

## 9. Interview Record

Challenged on "pre-launch, no real users" (`PRD-OSS-SELF-HOSTED-PIVOT.md:45`) and on the opportunity
cost versus the M5.3 gate re-derivation. Both heard; **proceed** chosen (D1). Provisioning, callback
location, config location, org selection, linking policy, and library were each decided explicitly
(D2-D7) rather than inferred.
