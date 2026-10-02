# PRD: Mutation-route RBAC

**Slug:** `mutation-route-rbac` · **Branch:** `feat/mutation-route-rbac` · **Source:** `rereflect-next` pick 2026-10-02 + dig (`docs/planning/_card/understanding.md`). Based on discussion and code dig, not a GitHub issue.

## Problem Statement
Of 190 in-scope mutation routes in `services/backend-api/src/api/routes/`, 64 carry no role check. Where a `require_feature(...)` gate exists it is not a role gate and always passes under `SELF_HOSTED` (the default). So in a multi-seat self-hosted install a `member` can create/edit/delete/run churn playbooks (which send customer email and notifications), mark customers churned (feeds calibration labels), change org-wide workflow assignment rules, bulk-delete feedback, and queue org-wide LLM analysis. Three shipped PRDs deferred this as out of scope (`copilot-suggested-actions/prd.md:252`, `crm-churn-labels/prd.md:385`, `usage-decline-churn-labels/prd.md:375`); no one owns it. Precedent: `integration-routes-rbac` (2026-08-09) and `customers.py`.

## Goals & Success Metrics
- G1. Every mutation route is either role-gated or on an explicit, reasoned allowlist. **Metric:** a sweep test enumerates all mutation routes and fails on an unlisted ungated one (0 today-unlisted).
- G2. The policy table below is enforced server-side; a member gets 403 on every admin/owner route.
- G3. The UI does not offer members controls that will 403.
- Non-goal metric claims: none. This is access control, not an accuracy or product-quality change.

## Personas
- **Owner / Admin:** unchanged capabilities.
- **Member:** keeps everyday triage (status, assign, notes, tags, feedback create/update/urgent/CSV import, pending-feedback review, personal prefs); loses org-config, destructive and outbound-action routes.

## Policy (locked by the user 2026-10-02)
| Area | Routes | Policy |
|---|---|---|
| playbooks | create, update, delete, run, run-batch | admin/owner |
| churn_events | bulk mark, create, CSV import, recover | admin/owner |
| churn_events | delete | keep author-within-24h and system-admin rules; **add org admin/owner as an alternative** (no blanket gate) |
| workflow | assignment-rules CRUD, auto-assignment settings | admin/owner |
| workflow | assign, status, notes | member-open |
| feedback | delete, bulk-delete | admin/owner |
| feedback | create, update, urgent, CSV import | member-open (CLAUDE.md matrix: CSV import is member-allowed) |
| analyze | `POST /analyze/batch` (analyze-all-unanalyzed, org-wide LLM spend) | admin/owner |
| analyze | `POST /analyze/` (single item) | member-open |
| pending_feedback | approve, reject, bulk-approve, bulk-reject | member-open |
| everything else ungated | notifications, dashboard_layout, saved_views, shared_links, conversations, conversation_folders, account, auth prefs, ai_corrections, anomalies resolve, customers analyze / action-item, ai_settings test-model + keys/validate, response_templates `/suggest`, feedback_responses generate/send, copilot_actions execute (own `min_role`) | member-open, each on the allowlist **with a one-line reason** |

Gate = `require_admin_or_owner`, applied per route.

## Requirements
**Must**
- R1. Apply `require_admin_or_owner` to every admin/owner row above. Playbooks router keeps its router-level `require_feature`; add the role dep per route (or router-level, either is detected by the guard).
- R2. `delete_churn_event`: allow org admin/owner in addition to author-within-24h and system admin; members who are not the author within 24h still get 403, with the message updated.
- R3. Sweep-guard test: AST over every `@router.post/put/patch/delete` in `api/routes/`, resolving per-route `dependencies=`, handler argument defaults, and router-level `dependencies=` (incl. `APIRouter(dependencies=...)` and `include_router(..., dependencies=...)` in `main.py` if used). Fails on any ungated route not in a pinned `(module, handler) -> reason` allowlist; fails if an allowlist entry no longer exists or is actually gated (stale); excludes public API, auth/signup, inbound webhooks, usage ingest (explicit reasoned exclusion list, also pinned).
- R4. Backend tests per newly gated module: owner and admin succeed, member 403, cross-org unchanged; written RED first. Add a shared `member_user`/`member_headers` fixture rather than a fifth copy.
- R5. Frontend: one new `useRole()` hook (`isOwner`, `isAdminOrOwner`); hide (not disable) the newly gated controls for members: playbook create/edit/delete/toggle/use-template + run dropdown + bulk run; mark-churned (single, bulk, CSV, recover) and single suggestion confirm/reject; workflow settings page (redirect for members, matching settings-page precedent); feedback delete/bulk-delete everywhere they appear (feedbacks, churn-risks, feature-requests, urgent-feedbacks, pain-points, category detail, feedback detail); analyze-all trigger. Pages that are admin-only redirect members to a permitted page.
- R6. Replace the stale `plan === 'business'` gate in `RunPlaybookDropdown.tsx:26,47` and the plan-only gates on `settings/playbooks/{new,[id]}` with the role check (no plan gates, per CLAUDE.md).
- R7. Docs: CHANGELOG behaviour-change entry (members lose these actions on upgrade), extend CLAUDE.md permission matrix, DEV-TRACKING + AI-TRACKING note, tick the three deferral notes.

**Should**
- S1. The 403 detail for newly gated routes names the required role, as `require_admin_or_owner` already does.

## Technical Considerations
- Backend only changes route modules + a test; **no migration, no model change.** Role is read from the DB user row (`dependencies.py:255`), not the JWT claim, so a demoted user is gated immediately.
- Worker/analysis-engine untouched. The automation/playbook engines are server-initiated and not role-bound; only the HTTP entry points are gated. (Automation rules are already admin/owner via `automations.py`.)
- Multi-tenancy unchanged: org scoping stays as is; this adds a role layer only.
- Frontend tests mock role via the hoisted mutable `authMock` pattern (`ChurnSuggestionsPage.test.tsx:12-30`).

## Risks & Open Questions
- **Behaviour change on upgrade.** Members who triage by deleting feedback, running playbooks or marking churn lose that. Mitigate with the CHANGELOG entry; no feature flag (policy is the point).
- **Test fallout.** Dig found no member-success tests on these modules, but `test_customers_bulk.py`, `test_team.py`, `test_outreach_bulk.py` were not read, and frontend tests with `role: 'admin'` default are fine while any with no role may break. Full-suite red is not trustworthy (known `test_report_ws.py` segfault); scope runs to touched modules.
- **O1.** Which frontend control calls `/analyze/batch` vs `/analyze/`? The "Analyze" buttons on list pages may hit the batch route; if so, members lose them. Resolve in the plan; gate the control accordingly.
- **O2.** `feedback_responses` send is member-open per the recommendations (not asked explicitly, `send` emails a customer). Flagged for review: confirm or move to admin/owner.
- **O3.** `conversation_folders` and `shared_links` create: kept member-open as personal/collaboration features; reviewer may disagree for shared links (public analytics URL).
- **O4 (found, out of scope).** `organizations.py` PATCH `/me` inline-checks `role != "admin"`, rejecting owners. Likely a bug; separate fix.
- Allowlist is a hand-maintained list; the stale-entry check keeps it honest but a careless reviewer can still add an entry. Reason strings make that visible in review.

## Out of Scope
- Custom roles / fine-grained permissions; per-org policy configuration.
- Redesigning gates on already-gated routes; the `organizations` PATCH owner bug (O4).
- Public-API (`/api/public`) scope model, WebSocket auth (`copilot_ws`, `events_ws`), inbound webhook auth.
- Refactoring the ~20 inline `isAdminOrOwner` derivations onto `useRole()` (new hook used for new gating only).
- Provider abstraction refactor (P7) and the copilot defect batch.
