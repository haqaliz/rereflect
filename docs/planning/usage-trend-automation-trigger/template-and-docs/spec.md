# Aspect — `template-and-docs`

**Slice:** make the feature discoverable and honestly documented — the amendment that came out
of the PRD self-critique.

**PRD requirement:** M10, S0, S1, S3.

---

## Problem slice & outcome

An operator finds the usage-trend trigger without knowing it exists, can see whether it can
fire for them at all, and reads an honest account of its limits.

This aspect exists because M3.2b diagnosed discoverability as its own primary risk and this
feature has the same shape: the trigger is otherwise reachable only by an operator who already
knows to go looking for it.

## In scope

1. **Pre-built template (M10)** — a "Usage Decline Outreach" entry in `AUTOMATION_TEMPLATES`
   (`services/backend-api/src/config/automation_templates.py`, currently 5 entries, static
   dicts keyed by string id).
2. **Template `mode` support** — `enable_template` (`api/routes/automations.py:490-501`) sets
   `is_active=True` and never sets `mode`, which the `@validates` hook promotes to `active`
   (`models/automation_rule.py:117-136`). Add an optional `mode` key to the template dict,
   honored on creation, **defaulting to today's behavior when absent** so the five existing
   templates are byte-identically unaffected. Without this, the template path silently bypasses
   M7's shadow default.
3. **Template action choice** — the template ships a `send_notification` action, **not**
   `run_playbook`: `playbook_id` is a per-install autoincrement integer a static config cannot
   know. Document this in the template's own `description` so the operator knows to add the
   playbook action themselves.
4. **SM1 surface (S0)** — expose a count of customers holding a non-`insufficient_history`
   trend state, so "can this fire for me?" is answerable. Follow the M5.0 readiness-card
   pattern of honest counts with a ready/not-ready flag rather than a bare number.
5. **Docs (S1)** — `docs/SELF_HOSTING.md`: what the trigger fires on; the baseline-seed rule
   (first classification never fires); the ~14-day warm-up; the **permanent** ≥5 active-day
   baseline floor that excludes light users (PRD R4); and why shadow is the default.
6. **Tracking (S3)** — `AI-TRACKING.md` (N1/N2 shipped, M3.2b deferral closed) and
   `CHANGELOG.md`, including the M4.1.5 shadow-badge fix.

## Out of scope

- Changing the baseline floor or the warm-up window (inherited from M3.2b, PRD R4).
- A dashboard widget or notification for the SM1 count — one honest surface is enough.
- Marketing/landing-page copy.

## Acceptance criteria

- **AC1** — `GET /api/v1/automations/templates` returns 6 templates including the new one.
- **AC2** — Enabling it creates a rule with `trigger_type == "usage_trend"`, valid `states`, and
  `mode == "shadow"`.
- **AC3** — Enabling each of the 5 pre-existing templates still produces a rule with
  `mode == "active"` — an explicit regression test for the optional-`mode` change.
- **AC4** — The template's config passes `TriggerSchema` validation (i.e. the template can't
  ship a config the API would 422).
- **AC5** — The SM1 count is correct for a fixture org with a known mix of trend states, and
  reports zero (not an error) for an org with no usage data at all.
- **AC6** — `docs/SELF_HOSTING.md` states the warm-up, the baseline-seed rule, and the light-user
  exclusion in plain language.
- **AC7** — Tracking claims cite what actually shipped; no claim of improved churn prediction
  (PRD explicit non-goal).

## Dependencies & sequencing

**Last.** Depends on `trigger-registration` (the template's config must validate) and on
`automations-frontend` (shadow default should be consistent across both entry paths). The docs
and tracking edits should land after the behavior is final so they describe what was built.

## Risks / open questions

- The template demonstrates the trigger but does not fully wire the save motion (no playbook
  action) — a partial answer to the discoverability gap, and it should be described that way
  rather than oversold.
- SM1's placement is not yet decided. If no existing surface fits cleanly, prefer adding it to
  the readiness endpoint over inventing a new page.
