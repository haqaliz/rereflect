# Aspect — `automations-frontend`

**Slice:** the operator-facing half — create/edit a `usage_trend` rule, default it to shadow,
and stop misreporting shadow executions as failures.

**PRD requirement:** M6 (frontend half), M7, M8.

---

## Problem slice & outcome

An operator can build a usage-trend rule in the UI, it starts in shadow, and the execution log
tells the truth about what shadow did.

## In scope

1. **Register the trigger type**
   - `TriggerType` union — `lib/api/automations.ts:5-10`
   - `TRIGGER_TYPE_LABELS` — `:134-140`
2. **Config form, twice** (the two pages hand-duplicate their `TriggerConfigFields`):
   - `app/(dashboard)/settings/automations/new/page.tsx:98-194` + defaults at `:343-350`
   - `app/(dashboard)/settings/automations/[id]/page.tsx:78-236` + defaults at `:611-619`,
     including the `disabled={!isAdminOrOwner}` wiring the edit page applies to every control
   - Form shape: multi-select / checkboxes over `declining` + `sharp_decline`; default
     `["declining", "sharp_decline"]`; empty selection must be prevented client-side (the API
     422s on it)
3. **Shadow default for this trigger only (M7)** — selecting `usage_trend` sets `mode` to
   `shadow`; every other trigger type keeps defaulting to `active`
   (`new/page.tsx:319`). Must apply on the create page and when switching trigger type on edit.
4. **Shadow badge fix (M8)** — add `'shadow'` to `AutomationExecution['status']`
   (`lib/api/automations.ts:50`) and a distinct non-destructive branch in `StatusBadge`
   (`[id]/page.tsx:59-67`), which currently falls through to a red "failed" badge for it.
5. **Test-mock upkeep** — `TRIGGER_TYPE_LABELS` is hand-copied into each test file's
   `vi.mock`; the new option is invisible in mocked renders until every affected file is
   updated (`__tests__/settings/AutomationForm.test.tsx`,
   `__tests__/settings/AutomationsList.test.tsx`, and the three
   `app/(dashboard)/settings/automations/__tests__/*.test.tsx`).

## Out of scope

- Deduplicating the two `TriggerConfigFields` implementations — tempting, but a refactor of
  shipped code inside a feature branch. File it.
- Rendering `trigger_snapshot` in the execution log (PRD V4) — never rendered for any trigger.
- The list page — `TriggerBadge` is label-driven and needs no change.

## Acceptance criteria

- **AC1** — The trigger appears in the type selector on **both** create and edit pages with its
  label.
- **AC2** — Selecting it renders the states control with both states pre-selected, and the
  submitted payload is `{type: "usage_trend", config: {states: [...]}}`.
- **AC3** — Deselecting all states blocks submission client-side.
- **AC4** — Creating a `usage_trend` rule submits `mode: "shadow"`; creating any other trigger
  type still submits `mode: "active"` (explicit negative test — this is the divergence).
- **AC5** — On the edit page, switching *to* `usage_trend` seeds the default config; switching
  *away* seeds the other trigger's defaults (existing behavior preserved).
- **AC6** — A `member`-role user sees the controls disabled and no Save button (existing
  gating unchanged).
- **AC7** — An execution with `status: "shadow"` renders a distinct, non-destructive badge —
  explicitly **not** the red "failed" badge — and this is asserted by a test that would fail
  today.
- **AC8** — All pre-existing automations frontend tests stay green.

## Dependencies & sequencing

Depends on `trigger-registration` only for the config contract (`states`), not for code — can be
built in parallel against the agreed shape. Best sequenced after it so the payload can't drift.

Precedent for every step: the M4.1.5 `churn_probability_threshold` rollout, whose test files
(`new-churn-playbook.test.tsx`, `id-churn-playbook.test.tsx`, `list-shadow-badge.test.tsx`) are
the closest working examples.

## Risks / open questions

- AC4's divergence is a genuine special case in a shared form. If it turns out to need more than
  a small per-trigger default map, prefer a per-trigger `defaultMode` lookup beside the existing
  `triggerDefaults` map over scattering conditionals.
- M8 fixes shipped M4.1.5 behavior. It is in scope deliberately (PRD M8) but should be a
  separate commit so it can be reverted independently of the feature.
