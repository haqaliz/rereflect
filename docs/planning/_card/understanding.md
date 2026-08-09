# Phase 2 — Understanding: `integrations-routes-missing-rbac`

**Dug:** 2026-08-09, against the worktree `bug/integrations-routes-missing-rbac`
(base `2884b870`). Three parallel dig agents (router inventory / RBAC machinery /
sibling-module audit). Premise verified, blast radius expanded — see F1–F3.

---

## What the bug is really asking

`services/backend-api/src/api/routes/integrations.py` has **zero** role checks
(`require_admin_or_owner`/`require_owner`/403 — verified by grep, two "admin/owner"
hits are an Intercom API field name). Every route only requires `get_current_org`
(JWT-valid, no role check). So a `member`-role user can create/delete/test Slack and
Discord integrations, mutate integration config, and drive both OAuth connect flows
via the API — contradicting the RBAC matrix ("Manage integrations: Owner ✅ / Admin ✅ /
Member ❌"). The frontend hides the Integrations tab from members; the backend never did.

## F1 — The named file, exactly (14 routes, 10 gateable)

| Route | Write? | Gate? |
|---|---|---|
| `GET /` list | read | yes (sibling pattern gates reads too) |
| `POST /slack/webhook`, `POST /discord/webhook` | write | yes |
| `POST /discord/test`, `POST /slack/test` | external send | yes |
| `GET /{id}`, `GET /{id}/logs` | read | yes (sibling pattern) |
| `PATCH /{id}`, `DELETE /{id}` | write | yes |
| `GET /slack/template-variables` | static, **zero auth today** | decide (see F4) |
| `GET /slack/oauth/connect`, `GET /intercom/oauth/connect` | mints state | **yes — this is the P1** |
| `GET /slack/oauth/callback`, `GET /intercom/oauth/callback` | creates row | **cannot gate — JWT-less browser redirect, state-verified** |

`send_slack_message` / `send_discord_message` are imported by the automations engine
(`automation_engine.py:649`) and patched by tests by module path — signatures must not
change; only route-level deps are added. `oauth_states` dict is seeded directly by
`tests/test_intercom.py:153-157` — name and location must stay.

## F2 — The audit found TWO more full omissions (same class, same severity)

- **`linear_integration.py` — 17 routes, 0 role deps** (only inert `require_feature`).
  WRITE routes reachable by members: `GET /connect` (OAuth), `DELETE /disconnect`,
  `PUT /config`, `POST /test`, **`POST /issues` (member can create Linear issues)**
  `PUT /team-mappings`, `PUT /status-mappings`. Linear's OAuth callback (`GET /callback`)
  is JWT-less like the others.
- **`feedback_sources.py` — 8 routes, 0 role deps.** WRITE routes: `POST /`,
  `PATCH /{source_id}`, `DELETE /{source_id}`. These back the top-level
  `/feedback-sources` pages, which the frontend does NOT role-gate — so this hole is
  live in the UI, not just the API.

**Partially covered:** `webhooks.py` — all 5 writes gated; 3 GET reads ungated
(webhooks list/get/deliveries) — matches the member-visible Webhooks nav item. **Leave
as-is** unless the matrix is read strictly (recommend: leave, flag in PRD).

**Correct baseline (do not touch):** zendesk (7/7), jira (12/12), asana (12/12),
intercom (3/3), hubspot (11/11), salesforce (11 + JWT-less callback), oidc (3/3),
saml (3/3), api_keys (4/4). **The fix is restoring integrations/linear/feedback-sources
to the pattern every sibling already uses.**

## F3 — Test pattern to mirror

- Dep style: decorator `dependencies=[Depends(require_admin_or_owner)]` (sibling
  integration routers; `integrations.py` already uses that style for
  `require_feature`). Failed check → 403, plain-string detail.
- Fixtures: conftest `auth_headers` = **admin** (existing tests keep passing untouched).
  Add per-file `member_user/member_headers` (+ `owner_*` if needed) minted via
  `create_access_token({"user_id", "organization_id", "role"})` — copy the pattern from
  `tests/test_oidc_config.py:114-159` / `tests/test_jira_connection.py:94-139`.
- Assert member → `== 403` strictly (do NOT copy the loose `in [200, 403]` legacy
  style from `test_team.py:353-371`). Mirror `test_oidc_config.py:298-308` and
  `test_jira_connection.py:550-567`.
- Only `tests/test_integrations.py` (admin-only, keeps passing) and
  `tests/test_intercom.py` (plan-gate 403 with dict body — unchanged) cover the named
  file today. No member/owner role tests exist for it.

## F4 — Decisions the PRD must settle

1. **Scope = three modules** (`integrations.py` + `linear_integration.py` +
   `feedback_sources.py`)? Recommendation: yes — same class, and the triage note
   (DEV-TRACKING.md:528-529) explicitly demanded the audit; the previous hardening
   branch (`integration-auth-tenancy-hardening`) also swept every instance.
2. **Reads**: gate ALL routes including GETs on `integrations.py` and
   `linear_integration.py` (matches every sibling router) vs reads-only-member.
   Recommendation: gate all — consistent, and the matrix grants members no
   integration-status reads. For `feedback_sources.py`: gate writes, leave GETs open
   (its pages are top-level/member-visible today; gating reads would 403 every member
   view with no UI change).
3. **Frontend**: the card said "no frontend changes" but the audit shows three member-
   reachable surfaces would newly 403: `settings/integrations/[id]` + `new` pages,
   the Linear branch of `feedbacks/[id]/create-issue`, and `feedback-sources/*` write
   buttons. Options: (a) backend-only, accept member 403s on those pages (jira/asana
   issue creation already 403s for members today — so linear becoming consistent is a
   fix, not a regression); (b) also add the existing `isAdminOrOwner` redirect pattern
   to those pages. Recommendation: (a) in this branch, (b) as an immediately-following
   chore — or (b) in-branch if the user prefers one PR.
4. **`GET /slack/template-variables`** is fully unauthenticated today. Gate with
   admin/owner (recommended — no legit unauthenticated consumer) or leave public?
5. **OAuth callbacks** stay JWT-less (provider redirect) — gate the *connect* step
   only; document the residual (state-guarded) risk. Matches the Salesforce precedent.

## Contradictions / flags surfaced (do not paper over)

- The card's "the UI already hides integration management from members" claim is
  **false in three places** (F4#3). The `settings/integrations` *hub* page redirects
  members (AppSidebar `requiredRole: 'admin'` at `components/AppSidebar.tsx:142`), but
  `settings/integrations/[id]`, `new`, the `feedbacks/[id]/create-issue` Linear branch,
  and every `feedback-sources/*` page have no role guard. CLAUDE.md's
  `components/SettingsTabs.tsx` reference is stale — the component doesn't exist.
- `webhooks.py` GET reads are deliberately member-visible and match the UI; not part of
  this bug.
- `GET /slack/template-variables` being fully unauthenticated is itself a (minor)
  defect in the "no auth = bug" class — flag, don't silently fix.
