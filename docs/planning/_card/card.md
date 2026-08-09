# Card — `integrations-routes-missing-rbac`

**Type:** bug (freeform — no GitHub issue)
**Branch:** `bug/integrations-routes-missing-rbac`
**Worktree:** `.claude/worktrees/bug-integrations-routes-missing-rbac`
**Opened:** 2026-08-09
**Traces to:** DEV-TRACKING P1 (`DEV-TRACKING.md:520-529`) — Post-1.0.0 User Feedback Backlog
**Picked by:** `rereflect-next` (previous session) — highest-severity remaining item in
the repo's own highest-priority queue (DEV-TRACKING.md:39-41 says pick here before older
roadmap sections).

## The problem

`services/backend-api/src/api/routes/integrations.py` contains **zero** occurrences of
`403`, `require_admin_or_owner` or `require_owner`. `get_current_org` validates the JWT
but never checks `current_user.role` (DEV-TRACKING.md:521-522).

So a **`member` can drive the OAuth connect flow via the API**, contradicting the RBAC
table in CLAUDE.md ("Manage integrations: Owner ✅ / Admin ✅ / Member ❌"). The frontend
hides the UI; the backend does not enforce it — "the classic shape of an access-control
gap that looks fine in manual testing" (DEV-TRACKING.md:526-527).

Triage also requires: **audit the other integration route modules for the same omission
before assuming it is confined to this file** (DEV-TRACKING.md:528-529).

## The fix (minimal slice)

- Add `require_admin_or_owner` (admin/owner-only) / `require_owner` (owner-only) role
  dependencies to the integration routes in `routes/integrations.py`, mapped per-endpoint
  against the RBAC matrix — not blanket-gated (some routes may be legitimately
  member-accessible, e.g. read-only status checks).
- Audit sibling integration route modules (zendesk, hubspot, salesforce, jira, asana,
  linear, slack, intercom, discord, webhook routes) for the same omission and fix where
  the matrix requires.
- Pin the behavior with tests asserting 403 for `member`, 200 for `admin`/`owner`.

## Scope guards (from DEV-TRACKING + the card, do not expand)

- **No frontend changes** — the UI already hides integration management from members.
- **Do not** bundle the sibling P1 `oauth-tokens-stored-plaintext`
  (DEV-TRACKING.md:500-518) or P3 `oauth-state-in-process-dict` (DEV-TRACKING.md:546-551)
  into this card; if the dig shows they're trivial to ride along, note them but keep this
  branch scoped to role enforcement.
- `send_slack_message()` / `send_discord_message()` helpers in `routes/integrations.py`
  are *called by* automations/alert paths — verify the helpers' callers before touching
  the module's public functions; only the route-level role checks change here.
- A `member` must still be able to do everything the RBAC matrix grants members:
  view feedback, import CSV, view team list/invites. Nothing that reads
  integration *status* in a way the matrix allows may be broken.

## Related context

- RBAC matrix: CLAUDE.md (repo root, "Role-Based Access Control" section).
- Enforcement pattern: `src/api/dependencies.py` — `require_admin_or_owner`,
  `require_owner`; usage precedent in `routes/team.py` (`Depends(require_admin_or_owner)`
  on invite) and billing (owner).
- Prior art: `integration-auth-tenancy-hardening` (2026-07-29) — the same backlog's P0
  webhook-tenancy fix; the branch's own `tests/test_webhook_verifiers_fail_closed.py`
  established the "audit all instances, not one" pattern.
