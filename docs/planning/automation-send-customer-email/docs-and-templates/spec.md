# Spec — docs-and-templates (seeded shadow template + documentation)

**Aspect:** `docs-and-templates` · **Slug:** `automation-send-customer-email`
**Plan output:** `docs/planning/automation-send-customer-email/docs-and-templates/plan_20260819.md`

## Problem slice

The feature is invisible without an in-product example and operator docs. This aspect
seeds a shadow-mode template that uses the action, and updates all operator-facing docs
and tracking markers so the feature is discoverable and the deferral is closed.

## In-scope

- **Seeded template (backend-api)** `config/automation_templates.py` += "At-Risk
  Customer Outreach": trigger `churn_probability_threshold`
  (`{threshold: 0.6, direction: above}`), action `send_customer_email`
  (`{template: "re_engagement", recipient: "customer"}`), `mode: "shadow"`. Seeding is
  idempotent at startup (existing mechanism). A test pins: template exists, is shadow,
  and its action type is valid.
- **Docs:**
  - `docs/SELF_HOSTING.md`: new "Automation email" section — the `send_customer_email`
    action, rule `mode` gating (shadow never sends), `RESEND_API_KEY` no-key behavior
    (loud skip, never silent success), opt-out (`CustomerHealth.outreach_opt_out`) +
    tokenized unsubscribe honored, shared `outreach_cooldown` (no double-email via
    automation + bulk within the window).
  - `docs/API.md` (+ OpenAPI docstrings): `send_customer_email` action config; the
    deliveries endpoint `GET /api/v1/automations/{rule_id}/deliveries`.
  - CHANGELOG: entry for the feature (behavior-change note: a rule with this action
    emails a customer when active).
- **Tracking markers:**
  - `AI-TRACKING.md`: M4.4 automation row / capability table — add the action to the
    automations capability + note.
  - `DEV-TRACKING.md`: decisions or recent-completions row.
  - `docs/planning/customer-outreach-email-actions/prd.md:239`: mark the deferral
    closed (note pointing at this feature's docs/planning dir).
- **README** Highlights (only if the automations row needs it — optional).

## Out-of-scope boundaries

- Backend action/enqueue/model → `action-core`.
- Worker task/mirrors → `worker-mirrors`.
- Frontend → `frontend-editor`.
- New outreach templates in the registry (reuse `re_engagement` / `weekly_digest_entry`).

## Acceptance criteria (testable)

1. On startup the seeded template exists, `mode="shadow"`, with a valid
   `send_customer_email` action; re-running the seeder is idempotent (existing
   behavior, pinned by the seeder test).
2. `docs/SELF_HOSTING.md` documents the action + no-key + opt-out + cooldown semantics.
3. `docs/API.md` documents the action config + deliveries endpoint.
4. CHANGELOG has an entry; `AI-TRACKING.md` / `DEV-TRACKING.md` rows updated; the
   deferral at `customer-outreach-email-actions/prd.md:239` marked closed.
5. Backend `pytest tests/ -v` green (seeder/template tests); no frontend/worker changes
   in this aspect.

## Dependencies & sequencing

- Depends on `action-core` (the seeded template's action type must be valid/executable)
  and `worker-mirrors` (the template's action must actually send) for a truthful
  "shipped" claim. Docs can be drafted in parallel; the tracking markers land last.

## Open questions / risks

- Confirm the `churn_probability_threshold` trigger config shape used by the existing
  templates/`seed_churn_cooldowns` (the `{threshold, direction}` convention) before
  pinning the seeded template's trigger config.