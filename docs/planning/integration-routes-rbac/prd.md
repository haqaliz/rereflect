# PRD — Enforce RBAC on integration routes

**Slug:** `integration-routes-rbac`
**Branch:** `bug/integrations-routes-missing-rbac`
**Status:** Draft (post-interview, pre-review-gate)
**Date:** 2026-08-09
**Traces to:** DEV-TRACKING P1 `integrations-routes-missing-rbac` (DEV-TRACKING.md:520-529)
**Decisions locked in interview:** scope = three modules · reads gated on integrations/linear
(sibling pattern) · feedback-sources writes only · backend-only (UI guards deferred) ·
template-variables gated.

---

## Problem Statement

The RBAC matrix (CLAUDE.md) grants "Manage integrations" to **Owner / Admin only**.
The backend enforces this for every integration router — **except three**:

- `src/api/routes/integrations.py` (Slack / Discord / Intercom-OAuth) — 14 routes,
  **0 role checks** (only `get_current_org`, which validates the JWT but never the role).
- `src/api/routes/linear_integration.py` — 17 routes, **0 role checks** (only the inert
  `require_feature` plan gate).
- `src/api/routes/feedback_sources.py` — 8 routes, **0 role checks**.

Consequence: a `member`-role user can, via the API, create/delete/test Slack and Discord
integrations, edit integration config, drive both OAuth connect flows, create Linear
issues, and create/edit/delete feedback sources — all of which the matrix says they
cannot do. The frontend hides the Integrations tab from members, so the gap is invisible
in manual testing — the exact "classic access-control gap" shape the triage named
(DEV-TRACKING.md:526-527).

For a product whose acquisition hook is trust ("your data never leaves your box",
"zero telemetry" — named independently by 4 of 7 post-1.0.0 user comments,
DEV-TRACKING.md:553-564), a documented-but-unenforced permission guarantee is a
credibility and security liability.

## Goals & Success Metrics

- **Goal:** every integration-management route in `integrations.py`,
  `linear_integration.py` and `feedback_sources.py` enforces the role the RBAC matrix
  assigns it.
- **Measured by:** a member-role test asserting `403` on every write route and every
  gated read route; admin/owner tests asserting `200`/expected status on the same
  routes. The existing admin-role test suite (conftest `auth_headers` = admin) passes
  unchanged — **zero behavior change for admin/owner and unauthenticated callers**.
- **Consistency check:** grep in CI-adjacent terms — after this branch, the set of
  integration/OAuth/webhook-config route modules with zero `require_admin_or_owner` /
  `require_owner` occurrences is **empty** (except the documented JWT-less callbacks).

## User Personas & Scenarios

- **Member (CSM/support)** — today: can drive OAuth connects and mutate integrations
  via API. After: gets `403 This action requires admin or owner privileges` on every
  gated route; nothing they can legitimately do (view feedback, import CSV, view team)
  is affected. They never see the Integrations tab in the UI.
- **Admin / Owner** — after: byte-identical behavior. All 12 non-callback routes in
  `integrations.py` and all Linear/feedback-source routes keep working exactly as
  today (existing tests run as admin pin this).
- **No-auth callers** — the two OAuth callbacks (`/slack/oauth/callback`,
  `/intercom/oauth/callback`) and Linear's `/callback` remain JWT-less browser-redirect
  endpoints (provider redirects carry no `Authorization` header); they stay
  state-verified exactly as today.

## Requirements

### Must-have

1. **`routes/integrations.py`** — add `require_admin_or_owner` to **all 12
   JWT-authenticated routes**, including the reads (`GET /`, `GET /{id}`,
   `GET /{id}/logs`) — sibling pattern (jira/asana/zendesk/hubspot/salesforce gate
   everything). Includes `GET /slack/template-variables`, which currently has **no auth
   dependency at all** (interview decision: gate it — no legitimate unauthenticated
   consumer exists; the frontend calls it via the authed client).
2. **`routes/linear_integration.py`** — add `require_admin_or_owner` to all 14
   JWT-authenticated routes (connect, disconnect, config, test, issues, mappings,
   reads). Keep `GET /callback` JWT-less (OAuth redirect).
3. **`routes/feedback_sources.py`** — add `require_admin_or_owner` to the **write**
   routes only: `POST /`, `PATCH /{source_id}`, `DELETE /{source_id}`. All GET routes
   stay member-visible (the `/feedback-sources` pages are top-level and member-reachable
   today; closing the exploit is the priority, member views are not the bug).
4. **Tests** (strict `== 403` — do not copy the loose `in [200, 403]` legacy style):
   - member → 403 for each gated route, across all three modules;
   - admin (conftest `auth_headers`) → unchanged behavior on the same routes;
   - owner → 200 on a representative sample (e.g. one write per module);
   - OAuth connect endpoints: member → 403;
   - callbacks remain reachable without auth (pin with an existing-pattern test where
     one exists; at minimum assert no regressions in `test_intercom.py` /
     `test_integrations.py`).
5. **Helper contracts frozen:** `send_slack_message` / `send_discord_message`
   (imported by `automation_engine.py:649`, patched by tests by module path) and
   `oauth_states` (seeded directly by `tests/test_intercom.py:153-157`) keep their
   names, signatures and module locations.

### Should-have

- One negative test per module proving a `member` cannot reach the OAuth **connect**
  step (the state-minting endpoint), since the callback itself cannot be gated.
- **Sweep-guard test** — a static test asserting every integration/OAuth/config router
  module (`integrations.py`, `linear_integration.py`, `feedback_sources.py`, plus the
  already-gated siblings: zendesk, jira, asana, intercom, hubspot, salesforce, oidc,
  saml, api_keys, webhooks-writes) contains a role dependency or an explicit named
  exemption — mirroring the "enumerate every instance" convention of
  `tests/test_webhook_verifiers_fail_closed.py`, so a future module can't silently
  regress into this class.

### Nice-to-have

- A one-line doc note in `docs/SELF_HOSTING.md` or the module docstring stating that
  OAuth callbacks are intentionally unauthenticated (provider-redirect, state-guarded).

## Technical Considerations

### Services changed

- `services/backend-api` only. No worker, no analysis-engine, no frontend, no DB.

### The pattern to copy (do not invent)

```python
@router.post("/slack/webhook", dependencies=[Depends(require_admin_or_owner)])
```

- Deps: `require_admin_or_owner` (403 `"This action requires admin or owner
  privileges"` when `role == 'member'`) and `require_owner` (`dependencies.py:255-288`).
- Imports: add `require_admin_or_owner` to `integrations.py:21` import line,
  `linear_integration.py`, `feedback_sources.py` imports.
- Precedent: `salesforce_integration.py:435-437` stacks `require_admin_or_owner` with
  `require_feature(...)` in the same `dependencies=[...]` list — mirror that where a
  feature gate already exists (linear's `require_feature("linear_integration")`).
- No route in scope uses `require_owner` (owner-only) — the matrix gates integration
  management at admin, not owner.

### Endpoint inventory (from the dig, file:line)

**`integrations.py`** (gate all 12 JWT routes; callbacks exempt):
`GET /` :355 · `POST /slack/webhook` :371 · `POST /discord/webhook` :417 ·
`POST /discord/test` :465 · `GET /{id}` :527 · `PATCH /{id}` :548 ·
`DELETE /{id}` :605 · `POST /slack/test` :630 · `GET /{id}/logs` :734 ·
`GET /slack/template-variables` :761 (add auth — was fully public) ·
`GET /slack/oauth/connect` :789 · `GET /intercom/oauth/connect` :972.
Exempt: `GET /slack/oauth/callback` :832, `GET /intercom/oauth/callback` :1012.

**`linear_integration.py`** (gate all 14 JWT routes):
`GET /connect` :298 · `DELETE /disconnect` :470 · `GET /status` :510 ·
`GET /config` :575 · `PUT /config` :592 · `POST /test` :616 ·
`GET /template-variables` :641 · `POST /issues` :655 · `GET /issues` :796 ·
`GET /teams` :823 · `GET /projects` :837 · `GET /labels` :852 ·
`GET /team-mappings` :870 · `PUT /team-mappings` :889 · `GET /status-mappings` :931 ·
`PUT /status-mappings` :950. Exempt: `GET /callback` :335.
(Three routes — `GET /status` :510, `GET /template-variables` :641 — currently have no
deps at all; they gain JWT + role like the rest.)

**`feedback_sources.py`** (gate writes only): `POST /` :280 · `PATCH /{source_id}` :499 ·
`DELETE /{source_id}` :558. GETs (:157, :227, :462, :570, :598) stay member-open.

### Multi-tenancy

Unchanged — `get_current_org` still scopes every route to the caller's organization.
The role check is additive on top of org scoping.

### API contracts

- Failure shape: `403` with plain-string `detail` — `"This action requires admin or
  owner privileges"`. This is NOT the dict shape of the plan-gate 403; existing tests
  asserting the plan-gate dict on the intercom connect route (`test_intercom.py:122-134`)
  are unaffected because those routes keep `require_feature` alongside the role dep.
- No request/response models change. No new endpoints. No migrations.

### Test plan (mirror existing patterns)

- Fixtures: per-file `member_user`/`member_headers` pairs minted via
  `create_access_token({"user_id", "organization_id", "role"})` — copy from
  `tests/test_oidc_config.py:114-159` or `tests/test_jira_connection.py:94-139`.
  conftest `auth_headers` (admin) covers the admin happy paths; add `owner_*` pairs
  where an owner test is needed.
- Mirror `test_oidc_config.py:298-308` (member → 403 per method) and
  `test_jira_connection.py:550-567` (member 403 across a provider's routes).
- New tests live in `tests/test_integrations.py` (add role section), a new
  `tests/test_linear_integration_rbac.py` (or extend the existing linear test file —
  the dig found none; create one) and a new `tests/test_feedback_sources_rbac.py`
  (or extend the existing feedback-sources test file if one exists).
- Sweep guard: grep-style check that no `routes/` module managing integrations has
  zero role deps after the branch (documented in the PRD, enforced by review, not a
  new test).

## Risks & Open Questions

0. **Effort signal (for the gate):** ~39 route decorator additions across 3 modules,
   3 test files (one new role-fixture section + 2 new files), zero DB/worker/frontend
   change. One or two aspects; implementable in a single TDD pass per module.
1. **Linear `POST /issues` behavior change for members** — members can create Linear
   issues from the create-issue UI page today (the page has no role guard). After this
   branch they get 403. This is *intended* (matches Jira/Asana, which already 403 for
   members) — but the UI will show an error until the follow-up frontend chore adds
   guards. Accepted; recorded as a known member-visible change. **Open question:** no
   evidence exists whether a member-side issue-creation workflow is load-bearing; if it
   is, the correct fix is a granular "create issues" member permission, not the blanket
   gate — flag for the user at this gate.
2. **Member-visible 403s on `settings/integrations/[id]` and `new` pages** — same
   accepted consequence; follow-up chore `frontend-integration-role-guards` covers
   `settings/integrations/[id]`, `settings/integrations/new`, the Linear branch of
   `feedbacks/[id]/create-issue`, and `feedback-sources/*` write buttons.
3. **OAuth callbacks stay unauthenticated** — the residual surface is state-guarded
   (single-use unguessable `state` in `oauth_states`); gating is impossible (browser
   redirect carries no JWT). Matches the Salesforce precedent. Not fixable in this
   branch; the related P3 (`oauth-state-in-process-dict`, DEV-TRACKING.md:546-551) is a
   separate tracked item.
4. **`GET /slack/template-variables` gains auth** — a contract change for a route that
   was fully public. Verified no unauthenticated consumer; frontend calls it authed.
   Flagged, not silent.
5. **Reads gated on integrations/linear** — members lose API read access to
   integration lists/status. Matrix-consistent and sibling-consistent; the UI already
   hides the tab. If a member-visible surface ever needs integration reads, that is a
   new feature decision, not this bug.

## Out of Scope

- **`oauth-tokens-stored-plaintext`** (DEV-TRACKING.md:500-518) — sibling P1; separate
  branch with backfill migration.
- **`oauth-state-in-process-dict`** (DEV-TRACKING.md:546-551) — P3; separate item.
- **Frontend role guards** — follow-up chore (see Risk 1/2).
- **`webhooks.py` GET reads** — deliberately member-visible (matches the member-visible
  Webhooks nav item); all its writes are already gated.
- **`notifications.py`** — user-scoped by design; members manage their own preferences.
- **`require_owner`-level gating** — nothing here is owner-only per the matrix.
- No changes to the JWT-less receivers (`source_webhooks.py`, `jira_webhook.py`,
  `asana_webhook.py`, `linear_webhook.py`, `email_webhooks.py`, `usage_webhooks.py`) —
  already fail-closed/API-key-scoped.
