# Understanding — `customer-outreach-email-actions` (Phase 2 dig)

Worktree dig on 2026-08-12, four parallel agents (email+drafting / automation+playbook
engines / cohort bulk API / frontend). All claims verified against code; file:line cites
are relative to this worktree.

## What the feature really is

The product's flagship loop (churn prediction with actionable reasons, `AI-TRACKING.md:5`)
dead-ends inside the app: every playbook/automation action is internal-only. Two shipped
plans deferred customer-facing email as a "separate slice" (`segment-actions/prd.md:170`,
`churn-triggered-playbooks/prd.md:247-249`).

**The dig sharpened this into a shipped-broken feature, not just a deferred one:**
`playbook_seeder.py:109-113` ("At-Risk Outreach") and `:213-217` ("Silent-Churn Watch")
ship `send_email` steps, and `playbook_engine.py:177-182` rejects every `send_email` with
`{"ok": False, "error": "unsupported action type"}` — **those template steps always fail
at runtime today** while the UI shows them as part of active playbooks (the same
delivery-integrity trap class as the automations bare-`except` bug, per
`docs/planning/automations-delivery-integrity/`). Also: 6 of 11 action types the seeder
uses (`notify`, `send_email`, `tag`, `create_task`, `schedule_task`, `trigger_automation`)
are unimplemented in the playbook engine.

## Affected areas

- **Backend-api**
  - `src/services/email_service.py` — Resend-only (plain HTTP POST, no SDK), BYO-key
    (`RESEND_API_KEY` = the enable switch), `_send_with_template` + `{{{VAR}}}` regex
    rendering, **no HTML escaping**, no rate limiting, no SMTP path anywhere in the repo.
    Skip semantics when key unset: `logger.warning` + return False — quiet.
  - `src/services/response_sender.py:159-202` `send_via_email` — the one existing
    **customer-facing** email path (plain text, from `org.support_email_display`, subject
    `Re: {original}`) — precedent for customer addressing.
  - `src/services/automation_engine.py` — action dispatch `_execute_actions` (407-438);
    `_execute_notify` email branch (589-604) logs-only, never feeds `channel_errors`
    (unlike Slack); `KNOWN_NOTIFY_CHANNELS = {dashboard, email, slack}`.
  - `src/services/issue_drafter.py` — the AI-draft pattern to copy: `resolve_generation_llm`
    (BYOK + local), `LLMNotConfiguredError` → 409, `<feedback>` injection delimiter +
    "untrusted data" hardening, `LLMUsageLog(task_type="issue_draft")`, tone fallback.
  - `src/api/routes/customers.py` — bulk endpoints (`/bulk/tags` 677, `/bulk/assign-owner`
    720) with `require_admin_or_owner`, `Cohort` schema (`schemas/cohort.py:27-41`,
    emails XOR filter), `resolve_cohort` (`services/cohort_service.py:18-65`, emails from
    `customer_health_scores.customer_email`, skip-with-count), `BulkActionSummary`
    `{matched, updated, skipped, errors[]}`; static `/bulk/*` must stay above `/{email}`
    (449-452).
  - `src/services/playbook_seeder.py` — `VALID_ACTION_TYPES` (24-36) already includes
    `send_email`; seeded `send_email` config shape is `{template, recipient}` where
    recipient ∈ `cs_assignee | customer` (111-113, 215-217).
- **Worker-service** (cannot import backend-api — everything mirrored)
  - `src/services/playbook_engine.py` — `_dispatch_action` (152-182) implements only
    `assign / change_status / send_notification / draft_response`; 60-min (playbook,
    customer) rate-limit → cancelled; requires a `CustomerHealth` row or the run fails.
  - `src/services/automation_feedback_trigger.py` — actions `auto_assign/change_status/
    send_notification/draft_response`; worker-local `_send_email_notification` (617-638)
    via `src/email.py` sharing env var names with the backend.
  - `src/services/automation_churn_trigger.py` + `automation_usage_trend_trigger.py` —
    run_playbook-only, **silently `continue`** past other action types (224, 272-273) — a
    new email action added only to the feedback mirror would be inert on the churn/usage
    paths.
  - Cooldowns: Redis DB 1, `automation_cooldown:{rule_id}:{customer_email}`, TTL
    `cooldown_hours * 3600`, 4 copies, must not drift.
- **Frontend**
  - `settings/automations/new/page.tsx:342-364` + `[id]/page.tsx:428-451` — `ACTION_TYPES`
    + inline per-type config branches (drift: new resets defaults, [id] preserves config).
  - `components/playbooks/PlaybookEditor.tsx:23-69` — type-select-only step editor, **no
    per-step config fields**.
  - `app/(dashboard)/customers/page.tsx` — cohort state (`emails` | `filter`), Bulk
    Actions dropdown (562-610), dialogs mounted at 832-865;
    `components/customers/BulkRunPlaybookDialog.tsx` is the dialog pattern (count-only
    preview, cap guard).
  - `feedbacks/[id]/create-issue/page.tsx:465-499` — Draft-with-AI + overwrite-confirm;
    `components/feedback/ResponseModal.tsx` — tone selector, template browser, variable
    pills, editable textarea, edit-before-send.

## Open questions (feed to the PRD)

1. **Action type naming** — seeder reserves `send_email` with `{template, recipient}`
   config; engines would need a `send_customer_email`-style type. Align with the seeded
   `send_email` taxonomy or rename the seeds (and fix the other 5 unimplemented seeded
   types — out of scope here; note only).
2. **Auto-send vs draft** — product norm is human-confirmed (draft_response, response
   suggestions, churn-label review queue). An automation `send_customer_email` action
   firing automatically is a behavior change the PRD must bless, or the action must
   produce a draft (e.g., a queued draft in a review surface) rather than a send.
3. **Email channel** — Resend-only today; SMTP is greenfield. First slice: Resend BYO-key
   (+ `response_sender`-style plain-text alternative?), SMTP explicitly v2.
4. **Customer opt-out** — no unsubscribe/suppression state for `customer_email` exists;
   automated customer-facing sends need at least an honest opt-out story (compliance +
   the honest-OSS brand). Scope? (e.g., org-level "suppress outreach" list, or per-customer
   flag + `List-Unsubscribe` header).
5. **Which triggers get the action** — feedback mirror only, or also churn/usage mirrors
   (which silently skip non-run_playbook actions today)? The seeded "Silent-Churn Watch"
   and "At-Risk Outreach" are playbook steps → that path is `playbook_engine`, not the
   automation triggers.
6. **Loudness** — email failures currently log-only (never `channel_errors`); a
   customer-facing send should be honest (loud result, `partial_failure` semantics).
7. **No-key behavior** — `RESEND_API_KEY` unset ⇒ skip with warning; the action result
   must say "skipped: no email key" loudly, not silently succeed.
8. **Bulk endpoint shape** — `POST /customers/bulk/outreach` (Cohort + subject/body or
   template), `BulkActionSummary`, `count_only` preview like run-batch, 500 cap,
   blank/malformed emails → skipped-with-count, archived excluded.

## Risks (do not paper over)

- **Two-engine duplication**: any send helper must exist in backend `email_service.py`
  and worker `src/email.py`; a bare `try/except` around a worker import = defect.
- **Churn/usage mirrors silently skip unknown actions** — easy to ship an action that
  "works" only on the feedback mirror while playbook/churn paths stay inert.
- **No HTML escaping in `_render_template`** — LLM-drafted body via `{{{VAR}}}` is raw;
  outreach templates need an escaping decision (or plain-text-only body).
- **No rate limiting** beyond playbook 60-min window + automation cooldowns.
- **Triggered-by string coupling** (`auto_probability`, `auto_usage_trend`) — keep exact.
- **M5.3 / churn computation untouched** — hard scope guard.
