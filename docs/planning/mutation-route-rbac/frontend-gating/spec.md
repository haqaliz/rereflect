# Aspect: frontend-gating (PRD R5, R6)
**Outcome:** members are not offered controls that would 403.
**In scope:** new `hooks/useRole.ts` (`isOwner`, `isAdminOrOwner` from `useAuth().user.role`); hide controls for members: playbook new/edit/delete/toggle/use-template, `RunPlaybookDropdown`, `BulkRunPlaybookDialog` menu item; mark-churned (single, bulk, CSV import, recover) + single suggestion confirm/reject; feedback delete + bulk-delete on feedbacks, churn-risks, feature-requests, urgent-feedbacks, pain-points, categories/[category], feedbacks/[id]; settings/workflow assignment-rule + auto-assign controls (page redirects members). Replace plan gates (`RunPlaybookDropdown.tsx:26,47`, `settings/playbooks/{new,[id]}`) with role checks.
**Out of scope:** refactoring the ~20 existing inline `isAdminOrOwner`; analyze-batch (no UI caller).
**Acceptance:** Vitest per touched component/page with hoisted `authMock` role: member hides/redirects, admin and owner show; existing `RunPlaybookDropdown` plan-based tests rewritten to role-based; `pnpm lint` + touched tests green.
**Dependencies:** backend-gating (policy), independent of sweep-guard.
