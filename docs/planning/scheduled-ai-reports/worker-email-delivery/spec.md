# Aspect spec — worker-email-delivery

**Feature:** scheduled-ai-reports · **Aspect:** `worker-email-delivery`
**Source:** `docs/planning/scheduled-ai-reports/prd.md` §4.3, §5

## Problem slice & user outcome

When a scheduled report is generated and the operator has configured a BYOK `RESEND_API_KEY`,
each recipient on the schedule receives the report by email. With no key (or empty
recipients) nothing is sent and nothing fails — the in-app report is always produced.

## In-scope requirements

1. **HTML renderer** `services/worker-service/src/services/scheduled_report_email.py`:
   - `render_scheduled_report_email(report) -> dict` producing `{subject, html}`.
   - Subject: e.g. `[<org name>] <Report type label> report (<date range label>)`.
   - HTML: report title, narrative paragraphs (when present), then each section rendered
     as a table/list from its `data` (charts degrade to their underlying data — state
     "view the full report for charts" in the footer), footer links: `Reports` page
     (`{APP_URL}/reports`) and `/settings/notifications` (weekly-digest precedent).
   - Plain `_send_email` raw-HTML path (`src/email.py:65`) — **no new Resend template**
     (mirrors `send_deletion_request_email`; the operator's template registry is not
     required to change).
2. **Sender** in `services/worker-service/src/email.py`:
   - `send_scheduled_report_email(to_email, organization_name, subject, html) -> bool`
     delegating to `_send_email`; `_send_email` already skips when `RESEND_API_KEY` unset.
3. **Type labels** shared with the frontend vocabulary:
   `executive_summary → Executive Summary`, `customer_health → Customer Health`,
   `feature_prioritization → Feature Prioritization`, `churn_risk → Churn Risk`;
   date-range labels: `7 → Last 7 days`, `30 → Last 30 days`, `90 → Last 90 days`.

## Out-of-scope boundaries

- No scheduling/generation (aspect `worker-scheduled-generation` calls this).
- No per-recipient opt-out tokens; no template CRUD; no attachments.
- Backend `email_service.py` is untouched (worker-only aspect).

## Acceptance criteria (testable)

- Worker `pytest tests/test_scheduled_report_email.py`:
  - renderer produces subject + HTML with title/narrative/section tables/footer links;
  - every section data shape (`type: table` / `series`) renders without raising;
  - sender returns False and does NOT call Resend when `RESEND_API_KEY` unset (monkeypatch
    `requests.post` → assert not called); returns True on mocked 200; False on mocked 5xx.
- Full worker suite green: `cd services/worker-service && pytest tests/ -v` (baseline ~1700).

## Dependencies & sequencing

- Standalone; depends on nothing. Build before or in parallel with
  `worker-scheduled-generation` (which imports the sender).
- Expose the exact function signature above so the generation aspect can depend on it.

## Open questions / risks

- None. Note: worker `src/email.py` is the *worker* mirror (already diverged slightly from
  backend for the digest) — this aspect adds to the worker copy only; keep the `# DUPLICATED`
  awareness but do not attempt to sync the digest divergence.