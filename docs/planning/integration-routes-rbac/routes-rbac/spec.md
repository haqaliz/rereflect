# Spec — `routes-rbac` (single aspect)

**Feature:** `integration-routes-rbac` — enforce the RBAC matrix on integration routes
**PRD:** `docs/planning/integration-routes-rbac/prd.md`
**Date:** 2026-08-09

## Problem slice

Three backend route modules let a `member`-role user manage integrations via the API
(contradicting "Manage integrations: Owner ✅ / Admin ✅ / Member ❌"):
`routes/integrations.py` (14 routes, 0 role deps), `routes/linear_integration.py`
(17 routes, 0 role deps — only inert `require_feature`), `routes/feedback_sources.py`
(8 routes, 0 role deps). Fix by adding `require_admin_or_owner` per the approved
interview decisions, pinning with member→403 tests, and adding a sweep-guard test so
the class cannot silently recur.

## In-scope requirements

- **integrations.py:** gate all 12 JWT-authenticated routes (incl. reads + the
  currently-unauthenticated `GET /slack/template-variables`); keep the 2 OAuth
  callbacks JWT-less (provider redirect, state-guarded).
- **linear_integration.py:** gate all 16 JWT-authenticated routes; keep
  `GET /callback` JWT-less.
- **feedback_sources.py:** gate only the 3 write routes (`POST /`, `PATCH /{id}`,
  `DELETE /{id}`); all 5 GETs stay member-open.
- Helper contracts frozen: `send_slack_message`, `send_discord_message`,
  `oauth_states` — names/signatures/locations unchanged.
- Tests: strict `== 403` for member on every gated route; admin behavior unchanged
  (conftest `auth_headers` = admin); owner 200 on a representative sample.
- Sweep-guard test enumerating every integration/config router module's role-deps.

## Out-of-scope boundaries

- No frontend changes (follow-up chore `frontend-integration-role-guards`).
- No changes to `webhooks.py` GET reads, `notifications.py`, or the JWT-less
  webhook receivers.
- Sibling P1 `oauth-tokens-stored-plaintext`, P3 `oauth-state-in-process-dict`,
  `require_owner`-level gating — separate items.

## Acceptance criteria (testable)

1. `member_headers` → `403 {"detail": "This action requires admin or owner
   privileges"}` on every route listed in the plan's per-module tables.
2. `auth_headers` (admin) → same behavior as before the change on every route
   (existing suite green, no assertions modified except the template-variables
   contract change if a public-access test exists).
3. OAuth callbacks respond without auth exactly as before (no new 401/403 on the
   callback paths; `test_intercom.py` / `test_integrations.py` callback coverage green).
4. Sweep-guard test green: zero integration/config route modules without a role dep.
5. Backend suite fully green; single alembic head untouched (no migration).

## Dependencies & sequencing

- A (integrations) / B (linear) / C (feedback-sources) are independent — parallelizable.
- D (sweep-guard) depends on A+B+C — runs last (a sweep test listing the offenders
  would be RED until they are gated).
- No DB, worker, analysis-engine, or frontend dependency.

## Open questions / risks (from PRD, unchanged)

- Linear `POST /issues` member 403 is an accepted behavior change (matches Jira/Asana);
  UI follow-up chore covers the member-visible 403 surfaces.
- `GET /slack/template-variables` gains auth — contract change, no unauthenticated
  consumer known; verify no test asserts public access before editing.
