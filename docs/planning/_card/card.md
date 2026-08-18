# Card — chore/frontend-cleanup-smalls (freeform, no GitHub issue)

Source: two recorded DEV-TRACKING items: `signup-promo-banner-vestigial` (:489-494)
and `frontend-integration-role-guards` (:612-615). Branch
`chore/frontend-cleanup-smalls`, worktree `.claude/worktrees/frontend-cleanup-smalls`.

## Items (both frontend-web)

1. **`signup-promo-banner-vestigial` (cleanup).** `app/signup/page.tsx` renders an
   invite banner gated on a hardcoded `VALID_PROMO_CODES` list read from a `?promo=`
   query param. There is no promo backend and no billing (Stripe removed in the OSS
   pivot), so it can neither grant nor withhold anything. Delete the banner + the
   promo-code machinery.
2. **`frontend-integration-role-guards` (chore).** 3 member-reachable surfaces now
   403 after the backend RBAC gating (`integrations-routes-missing-rbac`, 2026-08-09):
   `settings/integrations/[id]` + `new` pages, the Linear branch of
   `feedbacks/[id]/create-issue` (Jira/Asana already 403 for members), and
   `feedback-sources/*` write buttons. Add member-facing UI guards (hide/disable +
   honest copy) matching the existing patterns (isAdminOrOwner checks elsewhere).

## Caveats (carried into the PRD)

- The promo banner's removal must not break the signup page's layout/tests — the
  banner may be referenced in signup tests.
- The role-guard surfaces must keep admin/owner UX identical; only member UX
  changes (hidden/disabled controls). Check how the existing guarded surfaces
  (e.g. integrations page) handle members for consistency.

## Deliverables (proposed, refine in PRD)

1. Promo banner + `VALID_PROMO_CODES` machinery deleted; signup tests updated.
2. Member guards on the 3 surfaces with tests.
3. DEV-TRACKING markers for both.

## Out of scope (guardrails)

- No backend changes (the 403s are the enforcement; this is UI-only).
- No plan gates.
