# Understanding: mutation-route-rbac

## What is really being asked
Backend mutation routes carry no role check, so a `member` can do admin things. 190 in-scope
mutation routes under `api/routes/`: 126 role-gated, **64 ungated**. Scope is wider than the
four files in the card (also `pending_feedback`, `analyze`, `feedback_responses`,
`conversation_folders`, `anomalies`, `response_templates /suggest`).

## Findings that change the brief
- **`require_feature(...)` is not a role gate.** `playbooks` (router-level) and `churn_events`
  (per-route) have only a feature gate, which is always-true under `SELF_HOSTED`. They are
  effectively open to every member.
- **Router-level deps hide gates from a text grep.** `churn_suggestions` is gated only via
  router-level `dependencies=[require_admin_or_owner, ...]`. The existing
  `test_integration_rbac_sweep.py` checks "any marker anywhere in the module", so it cannot catch
  an ungated route inside a gated module. The new guard must be per-route (AST over decorator
  `dependencies=` + handler argument defaults + router-level deps).
- **Role comes from the DB user row**, not the JWT claim (`dependencies.py:255`). Tests need a
  real member row. Default `test_user` and all per-file `_make_user` helpers are `admin`;
  owner/member fixture templates exist in `test_churn_backfill_routes.py`.
- **Test breakage looks small.** No test found that authenticates as member and expects success
  on the target modules. Watch `test_churn_events_api.py:361` (member DELETE expects 403: would
  still pass but for the wrong reason, and the 24h author rule implies members may delete their
  own event). Unchecked: `test_customers_bulk.py`, `test_team.py`, `test_outreach_bulk.py`.
- **Frontend has no shared role hook.** `isAdminOrOwner` is re-derived inline in ~20 files from
  `useAuth().user.role`. Playbook/churn/workflow-settings/feedback-delete controls are all
  ungated in the UI. `RunPlaybookDropdown.tsx:26,47` has the stale `plan === 'business'` gate and
  no role check; `settings/playbooks/*` gate on plan only. Frontend tests mock role with a
  hoisted mutable `authMock` (`ChurnSuggestionsPage.test.tsx:12-30`).
- **CLAUDE.md contradiction to respect:** the permission matrix says *Import feedback (CSV)* is
  open to Members. The proposed policy keeps it open.
- **Adjacent, not in scope:** `organizations.py` PATCH `/me` checks `role != "admin"`, so an
  owner cannot update their own org. Likely a bug; record in PRD, fix separately.

## Proposed policy (needs sign-off)
| Area | Routes | Proposed |
|---|---|---|
| playbooks | create / update / delete / run / run-batch | **admin/owner** (outbound email, notifications) |
| churn_events | bulk mark, create, CSV import, recover | **admin/owner** (feeds calibration labels) |
| churn_events | delete | keep author-within-24h rule; add admin/owner as the alternative, no new blanket gate (OPEN) |
| workflow | assignment-rules CRUD, auto-assignment settings | **admin/owner** (org config) |
| workflow | assign, status, notes | member-open (everyday triage) |
| feedback | create, update, urgent, CSV import | member-open (matches CLAUDE.md matrix) |
| feedback | delete, bulk-delete | **admin/owner** (destructive) (OPEN) |
| analyze | `/analyze/batch`, analyze-all | **admin/owner** (org-wide LLM spend) (OPEN) |
| pending_feedback | approve/reject (+bulk) | member-open (OPEN) |
| feedback_responses | generate, send | member-open generate; send open (OPEN) |
| conversation_folders, notifications, dashboard_layout, saved_views, account, auth prefs, ai_corrections, anomalies resolve, customers analyze/action-item | personal/triage | member-open, on an explicit allowlist with a reason |

Mechanism: `require_admin_or_owner` per-route; sweep guard with a pinned `(module, handler)`
allowlist carrying a reason per entry, plus an "entry still exists" check.
Frontend: one shared `useRole()` hook (new), applied to the newly gated controls only; do not
mass-refactor the ~20 inline derivations.
