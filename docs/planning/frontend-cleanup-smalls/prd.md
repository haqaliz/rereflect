# PRD — Frontend cleanup smalls (promo banner, integration role guards)

**Slug:** `frontend-cleanup-smalls` · **Branch:** `chore/frontend-cleanup-smalls`
**Type:** chore · **Created:** 2026-08-18
**Card:** `docs/planning/_card/card.md`

---

## Item 1 — signup-promo-banner-vestigial: delete

**Problem.** `app/signup/page.tsx` renders a promo banner gated on a hardcoded
`VALID_PROMO_CODES = ['EARLYPRO3']` (:18) read from `?promo=` + localStorage
(:50-66, banner JSX :332-352). There is no promo backend and no billing — the offer
could never be honoured or withheld. The inline comment already flags it.

**Fix (locked): delete the machinery.**
- Remove: the const (:18), the state + effect (:50-66), the banner JSX (:332-352),
  the `.promo-banner` gsap refs (:82, :100), and the localStorage/trackEvent reads
  on both submit paths (:143-146, :177-180).
- Keep the `Sparkles` import (used by the "Start Your Free Trial" badge :252).
- Also delete the dead analytics helpers `promoSignup`/`promoCheckoutStarted`
  (`lib/analytics.ts:110-115` — zero callers).
- **Tests:** zero tests pin the banner (verified) — deletion is test-neutral; the
  dig's removal-scope list is the spec.

## Item 2 — frontend-integration-role-guards: 3 surfaces

**Problem.** Backend RBAC gating (2026-08-09) left member-visible surfaces that now
403 on submit:
1. `settings/integrations/[id]` + `new` — **the two settings pages missed by the
   member-redirect sweep**; every sibling redirects members to `/settings/preferences`
   (jira:61-65, asana:62-65, hubspot:64, salesforce:66, zendesk:83, intercom:70,
   linear:92, index :107-111). Members currently hit silent 403s + a misleading
   "Integration not found" state.
2. The create-issue wizard (`feedbacks/[id]/create-issue/page.tsx`) — **premise
   correction from the dig: NO branch is role-gated today** (not just Linear). The
   only "guard" is accidental: mount-time status GETs all 403 for members → all
   providers render "Not connected". A deliberate guard must cover the whole page.
3. `feedback-sources/*` write surfaces (list, [id], new) — create/edit/delete/toggle
   are admin-only on the backend; GETs stay member-open by design. The `pending`
   review page is deliberately member-open (no backend role deps) — out of scope.

**Fix (locked):**
1. `[id]` + `new`: the standard house redirect guard
   (`isAdminOrOwner` + `router.replace('/settings/preferences')`, the index-page
   pattern :104-111). Their existing tests render without an AuthContext mock → add
   the `mockUseAuth` treatment (the IntegrationsListPage tests' pattern) + a
   member-redirect test (the SalesforcePage.test.tsx:157-164 pattern).
2. Wizard: **page-level member state** — members see a "Only admins and owners can
   create issues from feedback" card (no redirect; the page is deep-linked from a
   member-visible detail page). Owner/admin UX unchanged. New member-case test
   (createIssueDraft.test.tsx already mocks role: 'owner' — add a member case).
3. feedback-sources: `isAdminOrOwner` gates on the write controls of the 3 pages
   (list Add/Delete/Pause-Play, [id] Delete/inputs/switches/Save, new wizard Create)
   — members keep read-only views; no tests exist → add member + admin cases with
   `mockUseAuth`.
- **Tests:** the IntegrationDetailPage/NewIntegrationPage tests need the
  AuthContext mock; createIssueDraft + feedback-sources gain member cases.

## Out of scope (guardrails)

- No backend changes (the 403s are the enforcement; this is UI-only).
- `feedback-sources/pending` stays member-open.
- No plan gates.

## Honest limits

- The guards are UI affordances; the backend 403s remain the actual enforcement
  (members who bypass the UI still get 403).
- The wizard's member state is a copy-card, not a redirect — deliberate (avoids a
  confusing redirect from a member-visible deep link).
