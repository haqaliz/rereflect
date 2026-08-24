# PRD — Scheduled & Emailed AI Reports

**Slug:** `scheduled-ai-reports`
**Status:** Draft — for review gate
**Date:** 2026-08-24
**Source:** freeform task (rereflect-next handoff) + Phase 2 dig + requirements interview

## 1. Problem Statement

Rereflect's On-Demand AI Reports (M2.4, `COMPLETE`) require a user to open the Copilot
(Cmd+K) and ask for a report each time. The only recurring communication today is the
weekly **digest** — a small summary email, not a full report. Operators who want the
board/leadership/CS to receive a real report (executive summary, customer health, churn
risk, feature prioritization) on a fixed cadence must either manually regenerate or accept
the shallow digest.

The PRD that shipped M2.4 explicitly deferred this: `PRD-ON-DEMAND-AI-REPORTS.md:37-38`
Non-Goals — *"No scheduled/recurring reports (manual trigger only)"* and *"No email
delivery of reports"*. This feature closes those two deferred items.

## 2. Goals & Success Metrics

**Goal:** let an org configure a report schedule (type + cadence + recipients) that a Celery
beat task materializes into a `Report` on cadence, with optional email delivery via BYOK
Resend, with in-app availability always and zero dependency on a key.

**Success (honest, measurable, self-host-appropriate) — verifiable acceptance thresholds:**
- **Schedule CRUD:** create/edit/delete/toggle all work and are RBAC-correct (member=403 on
  writes; cross-org=404). Verified by backend pytest.
- **Exactly-one-per-window:** for a given schedule + cadence window, the beat task persists
  exactly one `Report` (tagged `report_metadata.source="scheduled"` + `schedule_id`) and never
  double-runs a window under overlapping beats (atomic-claim rowcount). Verified by worker
  tests incl. a double-invocation test.
- **No-key resilience:** with no `RESEND_API_KEY`, generation still persists in-app and the
  task returns success (email skipped). Verified by a worker test.
- **Email path:** with a key, each non-empty `recipients` entry receives the report email.
  Verified by a worker test (mocked Resend client).
- **Narrative fallback:** with an LLM configured the report carries narrative; with none (or
  on LLM failure) it degrades to data-only — never fails the run. Verified by worker tests.
- **Frontend:** Scheduled tab lists/toggles/deletes and creates schedules end-to-end. Verified
  by vitest page tests + `pnpm lint`.
- **Integrity:** one Alembic head; new beat entry auto-covered by
  `test_beat_schedule_integrity.py`.
- No plan gates; all unlocked OSS posture.

## 3. User Personas & Scenarios

- **Founder/CEO (owner):** wants a weekly executive-summary emailed every Monday 09:00 UTC.
- **CS lead (admin):** wants a daily customer-health report for the at-risk list; creates a
  schedule with `customer_health`, cadence `daily`, hour `08:00 UTC`, recipients = self.
- **Product manager (member):** can *view* schedules and the reports they produce, but
  cannot create/edit/delete them (admin/owner-only, matching reports DELETE + integration RBAC).

## 4. Requirements

### Must-have
1. **Schedule CRUD (backend)** — `ReportSchedule` model (org-scoped) + REST API
   `GET/POST/PATCH/DELETE /api/v1/report-schedules` + `POST .../{id}/toggle`.
- Fields: `report_type` (fixed 4: `executive_summary` | `customer_health` |
      `feature_prioritization` | `churn_risk`), `date_range_days` (7|30|90, default 30 —
      added beyond the PRD draft so the schedule explicitly chooses the window instead of
      inventing a cadence→range mapping; flagged assumption, see §6), `cadence` (`daily` |
      `weekly` | `monthly`), `hour_utc` (0-23), `day_of_week` (0-6, required for weekly),
      `day_of_month` (1-31, required for monthly), `recipients` (JSON list of emails, max 20,
      deduped/trimmed, default `[creator_email]`), `enabled` (bool), `last_run_at`
      (nullable), `created_by_user_id` (nullable FK).
   - RBAC: list/get = feature-gated member; create/update/delete/toggle =
     `require_admin_or_owner` (mirrors `reports.py` DELETE + integration routes).
   - Validation errors → 422; cross-org → 404.
   - **Narrative format (decided):** scheduled-report narrative is a **concise data-led
     summary** (a few short paragraphs citing the section data), not a re-streamed on-demand
     essay — written for a reader who opens it in email/on a schedule, not interactively.
     It is data-first: sections render their data regardless, narrative is added on top only
     when an LLM resolves.
2. **Scheduled generation (worker)** — a Celery beat task that runs hourly, filters
   due schedules by cadence + `hour_utc`, and for each due schedule:
   - Generates the report body by **reusing the report generator logic** (mirrored into
     worker-service — see Technical Considerations), producing the same data sections as
     on-demand, plus an **LLM narrative when the org has an LLM configured** (reusing the
     worker's existing LLM resolution + non-streaming completion, e.g. the insights-task
     pattern); data-only when no LLM.
   - Persists a `Report` row (`organization_id`, `report_type`, `date_range_days`,
     `sections`, `report_metadata` incl. `schedule_id` + `source="scheduled"`,
     `created_by_user_id` = schedule creator if still a user, `conversation_id` = NULL).
   - Atomic dedup: `UPDATE ... SET last_run_at=now WHERE id=? AND (last_run_at < cutoff)`
     claim-by-rowcount so overlapping beats never double-generate a window.
   - Per-schedule `try/except` with `db.rollback()` in the handler (one failure must not
     abort the batch — `classifier_training.py:425-472` pattern).
3. **Email delivery (worker)** — when `RESEND_API_KEY` present and `recipients` non-empty, send
   each recipient the generated report (HTML rendering of the report's sections — tables
   and lists; charts degrade to their underlying data). No key / empty recipients → skip
   email silently, generation unaffected. Use the worker's own `src/email.py` raw `_send_email`
   path (BYOK; mirrors `send_deletion_request_email`). Footer link to the org's Reports page.
   **Recipient semantics (decided):** `recipients` defaults to `[creator_email]` and may be
   emptied by the creator — empty list means **in-app generation only, no email**; the UI
   seeds the creator's email on create. Recipients are the operator's own team (BYOK on their
   infra), so no per-recipient opt-out token in slice 1 — the email footer links to
   `/settings/notifications` (weekly-digest precedent) for users, and to the Reports page
   otherwise.
4. **Frontend** — on the existing `/reports` page add a **Scheduled** tab (shadcn Tabs):
   list of schedules (type badge, cadence, hour, recipient count, last run, enabled `Switch`
   → toggle, delete with confirm), and a "New schedule" dialog form (type select, cadence
   select + conditional day/hour fields, recipients input). No new top-level nav item
   (avoids `AppSidebar.isActive` prefix churn).
5. **Migration + integrity** — one Alembic migration (`report_schedules` table), exactly one
   alembic head; new beat entry covered by `test_beat_schedule_integrity.py` automatically.

### Should-have
- Scheduled reports appear in the normal My Reports list (they are real `Report` rows), with a
  subtle "scheduled" indicator via `report_metadata.source` if cheap.
- "Sync now" / manual run per schedule (dispatch the same worker task for one schedule).

### Nice-to-have
- Per-recipient opt-out link pointing at `/settings/notifications` (weekly-digest precedent).
- Next-run preview text in the UI ("Next: Mon 09:00 UTC").

## 5. Technical Considerations

### Services changed
| Service | Change |
|---|---|
| `services/backend-api` | `ReportSchedule` model + migration; `report_schedules` API + RBAC; schemas; tests |
| `services/worker-service` | mirrored `ReportSchedule` + `Report` models; mirrored report-generator (data-only) + narrative writer; `src.tasks.scheduled_reports` task + beat entry + `include`; email sender; tests |
| `services/frontend-web` | `/reports` Scheduled tab + dialog + `lib/api/scheduled-reports.ts`; tests |
| `services/analysis-engine` | none |

### The architecture constraint (non-negotiable)
**The worker image ships only `worker-service/src` + `analysis-engine/src/analyzer`
(`celery_app.py:10-12`) and cannot import backend-api.** All beat tasks run in the worker;
backend-api only has a `send_task` client (`background/celery_client.py`). Therefore the
report-generation logic **must be mirrored into worker-service** — the established,
documented `# DUPLICATED` pattern (usage_score_service, segment_service, automations engine).
The worker already mirrors the two tables the generator queries (`FeedbackItem` →
`feedback_items`, `CustomerHealth` → `customer_health_scores`; `worker/src/models/__init__.py:87,430`),
so a mirrored data-only generator is feasible without touching backend.

- **Mirror scope:** the data-only `ReportGenerator` (raw-SQL builders, 4 types, 7/30/90
  ranges) + `Report` + `ReportSchedule` model mirrors in worker, kept in sync via
  `# DUPLICATED` headers and covered by worker tests.
- **LLM narrative in worker:** the worker already generates LLM text (weekly insights,
  `tasks/insights.py`) and has `src/llm/org_resolver.py`; a non-streaming completion call for
  narrative is the established path. Data-only fallback on any LLM failure (copilot parity).
- **Dedup:** single hourly beat entry (`crontab(minute=15)`; avoid the crowded top-of-hour and
  the Monday 06:00-08:30 cluster) that filters schedules by cadence + hour, then atomic
  claim via rowcount on `last_run_at < cutoff`. Daily cutoff = today; weekly = last
  `day_of_week` occurrence; monthly = last `day_of_month` occurrence.
- **Multi-tenancy:** every query scoped by `organization_id`; worker task iterates orgs/schedules
  with per-item `db.rollback()`.

### Data Model (draft)
```
report_schedules
  id                  BIGINT PK
  organization_id     FK organizations.id, ON DELETE CASCADE, NOT NULL, index
  created_by_user_id  FK users.id, ON DELETE SET NULL, nullable
  report_type         String(50) NOT NULL   -- 4 fixed types
  cadence             String(20) NOT NULL   -- daily | weekly | monthly
  hour_utc            Integer NOT NULL      -- 0-23
  day_of_week         Integer NULL          -- 0-6, required when cadence=weekly
  day_of_month        Integer NULL          -- 1-31, required when cadence=monthly
  recipients          JSON NOT NULL         -- [email,...], deduped, max ~20
  enabled             Boolean NOT NULL default True
  last_run_at         DateTime NULL
  created_at          DateTime NOT NULL
  updated_at          DateTime NOT NULL
  Index (organization_id, enabled)
```

### API Contracts (draft)
```
GET    /api/v1/report-schedules            -> list (feature-gated, member)
POST   /api/v1/report-schedules            -> create (admin/owner)
PATCH  /api/v1/report-schedules/{id}       -> update (admin/owner)
DELETE /api/v1/report-schedules/{id}       -> delete (admin/owner)
POST   /api/v1/report-schedules/{id}/toggle -> enabled flip (admin/owner)
POST   /api/v1/report-schedules/{id}/run   -> manual "sync now" (admin/owner) [should-have]
```
All org-scoped (cross-org → 404). Request/response via Pydantic schemas; unknown fields →
422 (`extra="forbid"` precedent).

## 6. Risks & Open Questions

1. **Mirror divergence (highest risk):** a duplicated `ReportGenerator` in worker can drift
   from backend. Mitigation: copy verbatim + `# DUPLICATED` headers + a worker-side
   characterization test on a fixed dataset; the data-only generator is deterministic.
2. **Email rendering fidelity:** chart sections render as data tables/lists in email, not
   charts. State this honestly in the email copy ("view the full report for charts").
3. **Exact-once:** the atomic-claim dedup gives at-most-once per window; a crashed window is
   skipped, not backfilled (accepted for slice 1).
4. **`last_run_at` vs calendar semantics:** DST/timezone edge cases are avoided by storing
   UTC hour and comparing against UTC; month-31 schedule days in shorter months skip that
   month (accepted; document).
5. **Narrative-format parity (open):** whether scheduled narrative should exactly match the
   on-demand narrative style or use the shorter data-led form (PRD now commits to the
   shorter form; revisit if operators want byte-parity with Copilot output).
6. **LLM-failure behavior (open):** narrative falls back to data-only on LLM error — already
   spec'd; confirm during review that a hard `is_configured` gate should also skip narrative
   rather than the whole run (PRD: skips narrative only).
7. **`date_range_days` on the schedule (assumption, implemented):** the schedule carries its
   own `date_range_days` (7|30|90, default 30) instead of deriving the window from cadence.
   This makes the window explicit per schedule and reuses the existing report-generator
   ranges verbatim; the UI select exposes 7/30/90. Backend validation rejects anything else
   (422).

## 7. Out of Scope

- Custom report builder / custom report types beyond the fixed 4
  (`PRD-ON-DEMAND-AI-REPORTS.md:39`).
- Custom date ranges beyond the existing 7/30/90 (`PRD-ON-DEMAND-AI-REPORTS.md:43`).
- Real-time status push for schedule runs (existing `/ws/events` can be wired later).
- Per-recipient tokenized unsubscribe (single settings-link footer only).
- Backfill of missed windows, multi-window reports, report A/B testing, white-labeling.
- Any plan gate / hosted-SaaS / Stripe / Resend-required flows (BYOK, optional, skip-if-no-key).

## 8. Rollout & Documentation (repo conventions)

- `CHANGELOG.md` entry (the repo maintains one; no tags — commit history + changelog are the
  release record).
- `docs/SELF_HOSTING.md`: new "Scheduled reports" section — env note (reuses `RESEND_API_KEY`,
  no new env), cadence semantics (UTC, month-31 skip), and the no-key behavior.
- `README.md` Highlights/Reports row: one-line "recurring scheduled reports with optional
  email delivery".
- Follow the bug-fix convention: any shipped item updates its tracking marker in the same
  commit (per `DEV-TRACKING.md` "Roadmap hygiene").
