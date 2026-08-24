# Card — Scheduled & Emailed AI Reports (freeform task)

> Freeform task (no GitHub issue). Source brief: the `rereflect-next` recommendation handoff,
> validated against the repo's own tracking + PRD files on 2026-08-24.

## The task in one line

Turn Rereflect's shipped **on-demand AI reports** (M2.4) into **recurring / scheduled reports**
with optional **email delivery**, reusing the existing report generator, the BYOK Resend email
service, and the Celery beat scheduler.

## Why now (grounding)

- `PRD-ON-DEMAND-AI-REPORTS.md` §3 Non-Goals explicitly lists:
  - *"No scheduled/recurring reports (manual trigger only)"* (line 37)
  - *"No email delivery of reports"* (line 38)
  - *"No custom report builder (fixed 4 types)"* (line 39)
  - *"No custom date ranges (3 predefined only)"* (line 43)
- M2.4 On-Demand AI Reports is `COMPLETE` (`AI-TRACKING.md:51`): reports live in code —
  `Report` model, `GET/POST/DELETE /api/v1/reports`, `ReportGenerator`, My Reports page, PDF export.
- Email infrastructure already exists and is BYOK: weekly digest, team invites, password reset,
  and the automation `send_customer_email` action (M4.4, shipped 2026-08-20). No `RESEND_API_KEY`
  → sends are skipped (established skip pattern).
- Cadence/recurrence scheduling already exists elsewhere (weekly digest day/hour on user,
  Celery beat tasks) — the machinery to schedule is present.

## Scope intent (first slice, per the recommendation)

1. Schedule CRUD (per org): report type (one of the fixed 4), cadence (daily/weekly/monthly),
   day-of-week + hour (UTC), enabled/disabled.
2. A Celery beat task that generates scheduled reports on cadence, reusing `ReportGenerator`
   with the existing predefined date ranges.
3. Optional email delivery via `email_service` (BYOK Resend; no key → generate in-app only, never
   fail the schedule). Recipient: the schedule owner (or org recipients) — exact rule to be
   decided in the PRD.
4. Frontend: "Scheduled Reports" surface on the My Reports page (list, create, toggle, delete).

## Non-goals for this slice (candidates, confirm in PRD)

- No custom report builder (fixed 4 types stay).
- No custom date ranges beyond the existing 3 predefined.
- No plan gates (all unlocked, OSS posture).

## Caveats flagged at handoff

- Email delivery is **BYOK and optional** — generation must never depend on a key.
- Keep the fixed report types + predefined ranges; do not build a builder.
- Scheduled runs reuse the existing `ReportGenerator` — no new LLM feasibility question, just
  recurrence CRUD + beat + delivery.

## Verification plan (how this slice is considered done)

- Backend pytest: schedule CRUD + beat task + email path (with/without key) + auth/RBAC.
- Worker pytest where the beat task lives (or backend if it runs there).
- Frontend `npm run lint` + `npm run test`.
- One alembic head; migration for the schedule table.
