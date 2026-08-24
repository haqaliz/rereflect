# Aspect spec — backend-schedule-crud

**Feature:** scheduled-ai-reports · **Aspect:** `backend-schedule-crud`
**Source:** `docs/planning/scheduled-ai-reports/prd.md` §4.1, §5 (Data Model, API Contracts)

## Problem slice & user outcome

An org must be able to create, read, update, enable/disable and delete a report schedule
through the backend API. Without this aspect nothing can be configured; the worker task
(aspect `worker-scheduled-generation`) and the UI (aspect `frontend-scheduled-reports-ui`)
depend on this contract.

## In-scope requirements

1. `ReportSchedule` SQLAlchemy model (`services/backend-api/src/models/report_schedule.py`):
   - `id` PK indexed · `organization_id` FK `organizations.id` ON DELETE CASCADE, NOT NULL, index
   - `created_by_user_id` FK `users.id` ON DELETE SET NULL, nullable
   - `report_type` String(50) NOT NULL — one of `executive_summary | customer_health |
     feature_prioritization | churn_risk`
   - `date_range_days` Integer NOT NULL default 30 — one of `7 | 30 | 90`
     (added beyond the PRD draft so the schedule explicitly chooses the window instead of
     inventing a cadence→range mapping; flagged assumption)
   - `cadence` String(20) NOT NULL — `daily | weekly | monthly`
   - `hour_utc` Integer NOT NULL 0-23
   - `day_of_week` Integer NULL 0-6 (required when cadence=weekly)
   - `day_of_month` Integer NULL 1-31 (required when cadence=monthly)
   - `recipients` JSON NOT NULL (list of emails, deduped, max 20)
   - `enabled` Boolean NOT NULL default True
   - `last_run_at` DateTime NULL
   - `created_at` / `updated_at` DateTime NOT NULL
   - Index `(organization_id, enabled)`
   - Register in `src/models/__init__.py` (import + `__all__`).
2. Alembic migration `add_report_schedules_table` chained to the current single head
   (verify with `alembic heads` before writing; CI asserts exactly one head).
3. API router `services/backend-api/src/api/routes/report_schedules.py`, prefix
   `/api/v1/report-schedules`, registered in `api/main.py`:
   - `GET /api/v1/report-schedules` — list org schedules (newest first), member, feature-gated
   - `POST /api/v1/report-schedules` — create (admin/owner); `recipients` omitted →
     `[creator.email]`
   - `PATCH /api/v1/report-schedules/{id}` — partial update (admin/owner)
   - `DELETE /api/v1/report-schedules/{id}` — 204 (admin/owner)
   - `POST /api/v1/report-schedules/{id}/toggle` — flip `enabled` (admin/owner)
   - Cross-org id → 404. Unknown fields → 422 (`extra="forbid"`).
4. Pydantic schemas: `ReportScheduleCreate` (validates enum membership, hour/day bounds,
   cadence-conditional day fields, recipients list of `EmailStr`, max 20, deduped/trimmed),
   `ReportScheduleUpdate` (all optional, same validators), `ReportScheduleResponse`
   (includes `last_run_at`, `created_at`, `updated_at`).

## Out-of-scope boundaries

- No worker task, no beat entry, no email (other aspects).
- No `POST /{id}/run` here — it lives in the worker aspect (it dispatches the worker task).
- No pagination (schedule lists are small; matches reports.py precedent).

## Acceptance criteria (testable)

- Backend `pytest tests/test_report_schedules.py` (or co-located) covers: create/list/get-by-id/
  patch/delete/toggle happy paths; member→403 on every mutating route; cross-org→404; invalid
  report_type/cadence/hour/day/recipients→422; weekly requires day_of_week, monthly requires
  day_of_month; recipients default to creator email; recipients dedupe + cap at 20; toggle
  flips enabled; delete 204 + row gone.
- `alembic heads` prints exactly one head; `alembic upgrade head` applies cleanly.
- Full backend suite green: `cd services/backend-api && pytest tests/ -v` (baseline ~4900 tests).

## Dependencies & sequencing

- First aspect to build (nothing depends on it; everything else does).
- Produces the table + API contract the worker task and frontend consume.

## Open questions / risks

- None blocking. Assumption flagged: `date_range_days` added to the schedule (default 30)
  so the window is explicit; the UI select exposes 7/30/90.