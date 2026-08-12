# Card — `customer-outreach-email-actions`

**Type:** feat (freeform — no GitHub issue)
**Branch:** `feat/customer-outreach-email-actions`
**Worktree:** `.claude/worktrees/feat-customer-outreach-email-actions`
**Opened:** 2026-08-12
**Picked by:** `rereflect-next` — the single highest-leverage next feature after
`classifier-model-versioning-rollback` / the security-hardening wave (last commits
08-09/08-10) and the Discord/automations delivery work (07-29..08-09).

## The problem

The flagship loop is churn prediction with **actionable** reasons (`AI-TRACKING.md:5`,
"Killer Feature"), and churn-triggered playbooks now auto-run (`M4.1.5`,
`AI-TRACKING.md:365-378`) — but **every** playbook/automation action is SMTP-free. The
predict → act → retain chain dead-ends inside the app: the customer is never reachable.

Two shipped plans deferred exactly this as a deliberate "separate slice":

- `segment-actions/prd.md:170` — "Trigger outreach campaign" / outbound email *(depends
  on operator SMTP/Resend config — separate slice)*.
- `churn-triggered-playbooks/prd.md:247-249` — "Email/outreach-to-customer actions
  (needs operator SMTP; the deferred segment-actions 'trigger outreach campaign'). All
  actions here are SMTP-free."

## What to build (initial scope hypothesis — pressure-test in PRD)

1. **Automations/playbook email action** — a new action (e.g. `send_customer_email`)
   on the automations engine **and** its worker mirrors, plus the churn-playbook
   `action_sequence`, that sends a message to the feedback item's `customer_email`.
2. **"Trigger outreach campaign"** — the deferred `segment-actions` bulk action on
   `/customers` (row-selection or whole-filter cohort) sending a templated message to
   the cohort.
3. **Drafting** — reuse the `issue-draft` AI-drafting pattern (`AI-TRACKING.md:62`,
   "AI-Drafted Issue/Task Content") and the org tone/brand voice: LLM-drafted subject +
   body, editable before sending.
4. **Honest delivery** — reuse `email_service.py` (Resend, BYO-key) + the template
   system (`RESEND_TEMPLATE_*` ids, `templates/email/`). No `RESEND_API_KEY` ⇒ the
   send is skipped loudly (logged), not silently swallowed.

## Known caveats (from the dig in `rereflect-next`, verified in Phase 2)

- **Email infra is Resend-only.** There is no SMTP path in the codebase. The first
  slice should reuse Resend and either scope SMTP out (v2) or add it deliberately —
  a PRD decision, not an accident.
- **Draft, never auto-send.** Product norm (response suggestions copy-to-clipboard,
  AI-drafted issues populate editable fields, churn-label suggestions confirm-in-
  review): an outreach send must be human-confirmed before it goes out. Auto-send
  automation actions are the open question — the PRD must decide.
- **No user-ask grounding.** This is roadmap-grounded (named in two shipped plans),
  not from the 7-comment user backlog (`DEV-TRACKING.md:36-45`, all handled).

## Scope guards (do not expand)

- **Do NOT touch** churn/health computation, `churn_probability`, isotonic
  calibration, or M5.3 (data-gated, `AI-TRACKING.md:521-573`).
- **Do NOT touch** the automation cooldown scheme (Redis DB 1,
  `automation_cooldown:{rule_id}:{customer_email}`) — a new action reuses it, never
  re-keys it.
- **Do NOT add plan gates** — OSS, all unlocked (`CLAUDE.md`, "Plans & Feature
  Gating").
- Worker cannot import backend-api: any engine/action logic needed by the worker
  mirrors is duplicated per the `automation_feedback_trigger.py` precedent — a bare
  `try/except` around an import in worker-service is a defect on sight.
- Keep the two automation engines + the worker mirrors in agreement (change both).

## Related context

- Prior art — AI drafting: `POST /api/v1/feedback/{id}/issue-draft`
  (`AI-TRACKING.md:62`, `docs/planning/ai-drafted-issue-content/`).
- Prior art — email: `src/services/email_service.py`, `templates/email/`,
  `scripts/manage_resend_templates.py`, BYO-key + no-key-skips behavior.
- Prior art — bulk cohort actions: `docs/planning/segment-actions/` (Cohort contract,
  `count_only` preview, 500-cap).
- Prior art — playbook actions: `models/churn_playbook.py:67` (action_sequence reuses
  the automations action schema).
- Prior art — delivery honesty: `automations-delivery-integrity/` (silent-drop bugs;
  every send result must be loud).
