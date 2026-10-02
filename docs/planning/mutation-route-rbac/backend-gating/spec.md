# Aspect: backend-gating (PRD R1, R2, R4)
**Outcome:** members get 403 on every admin/owner row of the PRD policy table; owner/admin unchanged.
**In scope:** `require_admin_or_owner` on playbooks (5 mutations), churn_events (bulk mark, create, CSV import, recover), workflow (assignment-rules create/update/delete, auto-assignment-settings), feedback (delete, bulk-delete), analyze (`POST /analyze/batch`); `delete_churn_event` gains org admin/owner as a third allowed path; shared `member_user`/`member_headers` test fixtures.
**Out of scope:** guard test (sweep-guard), UI (frontend-gating), docs, anything member-open.
**Acceptance:** per gated route: owner 2xx, admin 2xx, member 403 (RED first); cross-org unchanged; member non-author delete of churn event still 403, admin/owner non-author delete succeeds, author within 24h still succeeds.
**Dependencies:** none; runs first.
**Open:** none (O1 resolved: no frontend caller of `/analyze/batch`).
