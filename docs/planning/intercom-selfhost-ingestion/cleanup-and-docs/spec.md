# Aspect Spec — `cleanup-and-docs`

**Feature:** `intercom-selfhost-ingestion` · **PRD:** `../prd.md` (R8, R10, S1, S3) · **Date:** 2026-08-01

## In scope

**R8 — delete the dead connector layer.** `worker-service/src/tasks/integrations.py` held
`BaseConnector` / `IntercomConnector` / `ZendeskConnector`, all `return []` stubs carrying
"TODO: implement in Month 2", plus `sync_all_integrations`, which was **on the daily beat**
dispatching them. Dead for *both* providers; the real pull paths are `intercom_sync.py` and
`zendesk_sync.py`. Only `celery_app.py` referenced it — no tests, no other callers.

**R10 — docs truth-up.** `SELF_HOSTING.md` (rewritten around the token-paste path, with the
OAuth flow kept as legacy), `CHANGELOG.md`, `AI-TRACKING.md` (new Intercom row),
`DEV-TRACKING.md` (P1 at :252 closed; the follow-up at :293 corrected — it proposed the
wrong fix). `README.md` needed no change; Part A already listed Intercom.

**S3 — stale plan-tier copy** at `signup/page.tsx` ("3 months of Pro free", "2,500
feedback/mo") corrected; there are no plans and no billing, so that offer could never be
honoured or withheld.

## What the guard test found

`tests/test_beat_schedule_integrity.py` resolves every scheduled task name to a real
function. It immediately caught a **pre-existing, unrelated defect**:
`purge-playbook-executions` referenced `tasks.churn_playbooks.purge_old_executions`, missing
the `src.` prefix, so the 90-day purge had never run.

Fixed here rather than deferred, on a timing argument: churn playbooks shipped 2026-07-19,
so on 2026-08-01 nothing is 90 days old and the first run deletes nothing. Deferring three
months would mean the first successful run purges a real backlog unannounced — the hazard
migration `12a1003fbfe0` was written to avoid for automation rules.

**A first draft of the guard was wrong** and is documented as such in the test: it read
`celery_app.tasks`, which is populated lazily by import order, and reported a dozen false
positives including tasks that demonstrably run. Resolving module + attribute directly is
order-independent.

## Deliberately not done

`signup-promo-banner-vestigial` — the invite banner's whole mechanism (a `?promo=` param
against a hardcoded code list, with no backend and no billing) is vestigial. Copy corrected
because it was misleading; removing the surface is outside this card and is filed in
DEV-TRACKING instead.

## Acceptance criteria

| # | Criterion | Result |
|---|---|---|
| C1 | Dead connector module and its beat entry deleted, no references remain | ✅ |
| C2 | Every beat entry resolves to a real task | ✅ guard test, 32 passed |
| C3 | SELF_HOSTING documents token-paste, pull, and manual webhook subscription | ✅ |
| C4 | No doc claims Intercom cannot produce feedback items | ✅ |
| C5 | No doc or UI claims a plan tier | ✅ |
| C6 | Worker / frontend / backend suites green, single alembic head | ✅ 1504 / 1536 / 133, head `8114adde5d96` |
