# PRD — PATCH /organizations/me accepts owners

## Problem
`update_my_organization` (`services/backend-api/src/api/routes/organizations.py:57`) gates on
`current_user.role != "admin"`, so an **owner** receives 403 when updating the organization name
or plan. Every other admin-level mutation route uses `require_admin_or_owner`, and the permission
matrix says owners outrank admins.

Found during `mutation-route-rbac`; recorded as `organizations-patch-rejects-owner` in
`DEV-TRACKING.md` and left unfixed because it was outside that branch's scope.

## Requirements
- R1: owner → 200, update applied.
- R2: admin → 200 (unchanged).
- R3: member → 403.
- R4: unauthenticated → 401/403 (unchanged).
- R5: use the shared `require_admin_or_owner` dependency, not another inline role string, so the
  route is covered by the RBAC sweep guard.

## Out of scope
- Any other route's role policy.
- Plan validation / billing semantics.

## Acceptance
- New tests for owner and member on `PATCH /api/v1/organizations/me`.
- Backend organisation + RBAC sweep tests green.

## Risks
- The 403 message changes from "Only organization admins…" to the shared
  "This action requires admin or owner privileges". No test or client depends on the old text.
