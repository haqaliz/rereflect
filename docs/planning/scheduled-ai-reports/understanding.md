# Understanding note — scheduled & emailed AI reports (Phase 2 dig)

## What this feature really is

A follow-on slice of shipped M2.4 On-Demand AI Reports (`AI-TRACKING.md:51`; non-goals at
`PRD-ON-DEMAND-AI-REPORTS.md:37-38`): let an org configure a **report schedule** (type +
cadence + recipients + enabled) that a **Celery beat task** materializes on cadence into a
`Report` row, optionally **emailed** via BYOK Resend. Mirrors the weekly-digest mechanics but
at org level and for full AI reports instead of a summary digest.

## Shipped pieces we reuse (verified)

| Piece | Location |
|---|---|
| `Report` model (org-scoped, `sections` + `metadata` JSON, `pdf_generated` unused) | `services/backend-api/src/models/report.py` |
| `ReportGenerator.generate()` — **data-only, keyless** raw-SQL builder, 4 fixed types, 7/30/90 ranges | `services/backend-api/src/services/copilot/report_generator.py:132-153` |
| Reports API (list/get/delete; GET feature-gated, DELETE admin/owner) | `services/backend-api/src/api/routes/reports.py` |
| BYOK email: `_send_email` raw-HTML path + skip-if-no-key + `_send_with_template` | `services/backend-api/src/services/email_service.py:91-207, 416-430` |
| Weekly-digest cadence precedent (day/hour/enabled columns + validation) | `services/backend-api/src/models/user.py:36-39`, `api/schemas/__init__.py:57-75` |
| Beat entry + `include` list + registration convention | `services/worker-service/src/celery_app.py:45-72, 111-309` |
| Per-org iteration + mandatory `db.rollback()` in per-org except | `services/worker-service/src/tasks/classifier_training.py:425-472` |
| Worker email mirror (raw `_send_email`, template sender) | `services/worker-service/src/email.py:65-120` |
| Worker LLM org resolution (for narrative, optional) | `services/worker-service/src/llm/org_resolver.py` |
| Frontend My Reports page + automations three-route list/new/[id] UI pattern + Switch toggle + nav | `services/frontend-web/app/(dashboard)/reports/page.tsx`, `settings/automations/*`, `components/AppSidebar.tsx:98-102` |
| Reports page tests pattern | `services/frontend-web/__tests__/reports/ReportsPage.test.tsx` |

## The architecture constraint that shapes everything

**The worker image ships only `worker-service/src` + `analysis-engine/src/analyzer`
(`celery_app.py:10-12`). It cannot import backend-api.** All beat tasks run in the worker,
and `ReportGenerator` + `Report` live only in backend-api. So a scheduled-reports beat task
**must** either (a) mirror a report generator + a `Report` model into worker-service (the
established, documented `# DUPLICATED` pattern: usage_score_service, segment_service,
automation engine), or (b) run generation in a backend-api process — but backend-api does not
run Celery beat (only a `send_task` client; `background/celery_client.py`). **Option (b) is not
viable without new infra; option (a) is the consistent choice.**

The worker already mirrors the two tables the generator queries (`FeedbackItem` →
`feedback_items`, `CustomerHealth` → `customer_health_scores`, `worker/src/models/__init__.py:87,430`),
so a mirrored data-only generator is feasible. LLM narrative would reuse
`worker/src/llm/org_resolver.py` (also feasible), else ship data-only for the first slice.

## Ambiguities / open questions for the PRD

1. **Where the generator lives in the worker**: mirror the full 648-line `ReportGenerator`, or
   a leaner data-only builder (`# DUPLICATED`)? Mirror-full risks divergence; lean risks a second
   implementation. Decision needed.
2. **LLM narrative**: include narrative for scheduled reports (parity with on-demand, "better as
   base models improve") or data-only first slice?
3. **Recipients**: schedule-level email list (default = creator)? Org members? Must email respect
   an opt-out/unsubscribe (→ `/settings/notifications`, like weekly digest)?
4. **Cadence model**: daily/weekly/monthly + day-of-week + hour UTC; `last_run_at` dedup guard so a
   late/overlapping beat run never double-generates.
5. **RBAC**: mirror reports.py — create/update/delete/toggle admin/owner, list/get member.
6. **Beat cadence**: hourly `crontab(minute=...)` entry that filters schedules by hour/day (like
   `send_weekly_digests` filters users), vs one entry per cadence.
7. **Scheduled runs vs `conversation_id`/`created_by_user_id`**: scheduled `Report` rows have
   `conversation_id=NULL`; creator = schedule creator (or `NULL` on delete — FK is `SET NULL`).
8. **No plan gate** (OSS all-unlocked); no Stripe/residency/benchmark baggage.

## Deferred / out of scope (candidates)

- Custom report builder, custom date ranges, custom branding — PRD non-goals, stay out.
- Backfill of missed runs beyond `last_run_at` guard (out of first slice).
- Real-time WS for schedule status (existing `/ws/events` can be reused later, not now).
