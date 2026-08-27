# Aspect — `playbook-tasks`

**Slice:** M3 — `create_task` / `schedule_task` backed by a new internal `playbook_tasks`
table. The only schema change in the card.

**PRD requirements:** M3 (OQ1: `due_in_days` + optional `due_at`).

---

## Problem slice & outcome

Seeded steps like `{"type": "create_task", "config": {"description": "Follow-up check-in",
"due_in_days": 3}}` persist a durable follow-up task for the customer instead of failing
with `unsupported action type`. Tasks are internal (self-host native, offline) — the
provider-dispatch follow-on is v2.

## In scope

1. **`PlaybookTask` model, backend** — new `services/backend-api/src/models/playbook_task.py`:
   - table `playbook_tasks`; id pattern matching `ChurnPlaybook` (`churn_playbook.py:54`)
   - `organization_id` (FK orgs, indexed), `customer_email` (String, indexed),
     `description` (Text, required), `due_at` (DateTime, nullable), `priority`
     (String(10), default `"medium"`), `status` (String(10), default `"open"`),
     `playbook_execution_id` (FK `churn_playbook_executions`, nullable),
     `created_at` (DateTime, default utcnow), `completed_at` (DateTime, nullable)
   - registered in the backend model `__init__` exports + `Base.metadata`
2. **One Alembic migration** — `alembic/versions/*_playbook_tasks.py`: create table +
   indexes. `alembic heads` must print exactly one head (CI asserts).
3. **`PlaybookTask` worker mirror** — `worker-service/src/models/__init__.py`, same columns
   (worker has no alembic; mirrors are column-for-column copies).
4. **`_handle_create_task`** in `worker-service/src/services/playbook_engine.py`:
   - config `{description: str (required), due_in_days?: int (>=0), priority?:
     "low"|"medium"|"high" (default "medium"), due_at?: ISO datetime}`
   - `due_at = config["due_at"] or utcnow() + timedelta(days=due_in_days)`
   - inserts a `PlaybookTask` row (org from the run's health row, status `open`),
     flushed; result `{task_id, description, due_at}`
5. **`_handle_schedule_task`** — same handler path with the same config shape minus
   `priority` (PRD M3); both dispatch branches added.

## Out of scope

- S1 (customer-profile "Playbook tasks" card + read endpoint) — deferred to v2; the
  execution-log surface (aspect `seeder-and-ui`, M7) is the v1 visibility.
- Provider task creation (Jira/Asana/Linear) — v2 (PRD N4).
- Task lifecycle endpoints (list/complete/delete) — the table is write-only in v1.

## Acceptance criteria

- **AC1** — `create_task` persists a row with org/customer/description/due/priority/status
  `open`, linked to the execution; result carries `task_id` + `due_at`.
- **AC2** — `due_in_days: 3` → `due_at == utcnow + 3 days` (calendar days); no
  `due_in_days` and no `due_at` → `due_at = NULL`.
- **AC3** — explicit `due_at` wins over `due_in_days`.
- **AC4** — `schedule_task` persists with priority default `medium`; config without
  `priority` is accepted; invalid priority → `ok: False`.
- **AC5** — missing/empty `description` → `ok: False`.
- **AC6** — a failing `create_task` never blocks sibling actions.
- **AC7** — migration applies cleanly (`alembic upgrade head`), `alembic heads` = 1, and
  the worker mirror has exactly the backend columns (mirror-drift test pattern).
- **AC8** — the full existing playbook-engine suite stays green.

## Dependencies & sequencing

Depends on nothing (aspect 1 is independent). Needed by `seeder-and-ui` only for the
execution-log result rendering (the `task_id` in the action result) — no hard coupling.

## Risks / open questions

- **Mirror drift**: two copies of the model (backend + worker) — follow the existing
  mirror discipline; the drift test convention lives in the worker suite.
- `due_at` vs `due_in_days` precedence is locked by AC3 (OQ1 answer: both allowed,
  explicit `due_at` wins).
- Migration must chain off the live head — verify `alembic heads` before generating.