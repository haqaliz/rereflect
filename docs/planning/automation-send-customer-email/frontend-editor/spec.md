# Spec — frontend-editor (action editor + labels + deliveries surface)

**Aspect:** `frontend-editor` · **Slug:** `automation-send-customer-email`
**Plan output:** `docs/planning/automation-send-customer-email/frontend-editor/plan_20260819.md`

## Problem slice

Operators can't configure the new action or see its outcome. This aspect adds the
`send_customer_email` action to the automations editor (template + recipient pickers),
the label/icon maps, and the deliveries surface on the rule detail page.

## In-scope (frontend-web only)

- **Types:** `ActionType` += `'send_customer_email'` (`lib/api/automations.ts:14-19`);
  config shape typed like playbooks' `SendEmailConfig` (`lib/api/playbooks.ts:6-9`):
  `{ template: string; recipient: 'customer' | 'cs_assignee' }`.
- **`ACTION_TYPES`** += `'send_customer_email'` in `app/(dashboard)/settings/automations/new/page.tsx:342-348` **and** `[id]/page.tsx:428-434`. Type-switch default config: `{ template: <first registry key>, recipient: 'customer' }`; `[id]` seeds defaults when switching in with an empty/stale config (mirror `PlaybookEditor` lines 62-74, 187-194).
- **Inline editor branch** in both pages (the `run_playbook` picker at `new:398-420` / `[id]:484-507` is the structural precedent): template select fed by `listOutreachTemplates()` with `BUILTIN_OUTREACH_TEMPLATES` fallback (`lib/api/outreach.ts:71-74,154-167`), recipient select (`customer` / `cs_assignee` labels — reuse the playbooks.ts recipient label map or a local copy). Honor the `new`-vs-`[id]` drift by writing the SAME config keys (`template`, `recipient`) in both pages.
- **Labels/icons:** `ACTION_TYPE_LABELS` (`lib/api/automations.ts:146-152`), `ACTION_ICONS` (list page `settings/automations/page.tsx:39-44`, e.g. `Mail`), execution-log badges (detail page `[id].tsx:964-973` uses the same label map).
- **Deliveries surface (PRD S2):** rule detail page "Email deliveries" section — fetches `GET /api/v1/automations/{rule_id}/deliveries` (client fn added to `lib/api/automations.ts`), renders status badges (`queued/sent/skipped/failed`) + reason + timestamp. Minimal.

## Out-of-scope boundaries

- Backend action/enqueue/model → `action-core`.
- Worker task/mirrors → `worker-mirrors`.
- Cooldown column on the rules list (PRD N1) — deferred.
- CS-owner display name in the recipient picker (PRD N2) — deferred.

## Acceptance criteria (testable)

1. Creating a rule with `send_customer_email` on the **new** page submits exactly
   `{ type: 'send_customer_email', config: { template, recipient } }`; edit on the **[id]** page loads and preserves the same keys.
2. Config keys are pinned by a source-assert test (the `CategoryMatchConfigKeys.test.tsx` pattern) so the frontend can never write a key the backend ignores.
3. Editor tests mirror `PlaybookEditor.sendEmail.test.tsx`: template+recipient selects seeded from config, default config on switch-in, save-payload exactness, registry-failure fallback to built-ins.
4. `ACTION_TYPE_LABELS`/`ACTION_ICONS`/execution-log badges render the new type (extend the mocked label maps in existing tests).
5. Deliveries section renders status badges from the endpoint; empty state handled.
6. `npm run test` + `npm run lint` green.

## Dependencies & sequencing

- Depends on `action-core` (config contract + deliveries endpoint). Can be planned/implemented in parallel with `worker-mirrors`; must land after `action-core` for a working end-to-end demo.

## Open questions / risks

- `new` page resets config on type switch; `[id]` preserves — the spec picks ONE contract (`{template, recipient}`, seeded on switch-in, preserved on edit) to apply in BOTH pages. Confirm the seeded default template key comes from the registry fetch (fallback: first `BUILTIN_OUTREACH_TEMPLATES` key).