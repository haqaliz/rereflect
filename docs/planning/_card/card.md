# Card: mutation-route-rbac (freeform, no GitHub issue)

Source: `rereflect-next` pick, 2026-10-02.

Add role enforcement to backend mutation routes that currently have none, starting with the
churn/playbook loop: `playbooks.py` (5 mutations, 0 role deps), `churn_events.py`, `workflow.py`
(9, 0), `feedback.py` (6, 0). Reuse `require_admin_or_owner` / `require_owner` and the
`customers.py` / `integration-routes-rbac` precedent. Deferred as out of scope by
`copilot-suggested-actions/prd.md:252`, `crm-churn-labels/prd.md:385`,
`usage-decline-churn-labels/prd.md:375`.

Dig first; write the policy as a table in the PRD before any code: which mutations stay
member-open (everyday triage: status, tags) vs admin/owner (playbook edit/run, churn labels,
bulk actions).

Known caveats: existing member-token tests will break; frontend needs matching conditional UI;
fix stale `plan === 'business'` gate in `RunPlaybookDropdown.tsx:26,47`. Add a sweep-guard test
(like `test_credential_encryption_sweep.py`) that fails when a new mutation route has no role
dependency and is not on an explicit allowlist.
