# Spec — playbook-editor-email-config

**Feature:** `customer-outreach-email-actions`
**PRD:** `../prd.md` (approved 2026-08-12)
**Aspect boundary:** the frontend half of PRD must-haves #1, #4 and #6 — per-step
`send_email` config in `PlaybookEditor`, the `send_email` action type/labels in the
frontend playbook API client, correct render of the seeded templates' steps through the
clone flow, and the per-customer outreach opt-out toggle on the Customer 360 profile.
**Consumes:** `outreach-core/spec.md` (AC2 registry endpoint, AC9 opt-out PATCH) — its
contracts are fixed and already planned; nothing in this aspect may change them.

## Problem slice

The playbook editor ships today with type-select-only actions (`PlaybookEditor.tsx:23-69`
— no per-step config fields anywhere), yet the seeder already ships two templates whose
first step is `send_email` with real config (`playbook_seeder.py:110-113` — At-Risk
Outreach, `weekly_digest_entry`/`cs_assignee`; `:214-217` — Silent-Churn Watch,
`re_engagement`/`customer`). An operator cloning either template today gets the step but
cannot see or edit what it sends. Simultaneously the engine rejects every `send_email`
step (`playbook_engine.py:177-182`) — that fix is the separate
`playbook-send-email-step` aspect (backend/worker), which this aspect must stay in
exact shape-agreement with. And the profile has no way to set `outreach_opt_out`, the
flag both send paths must honor (`prd.md:108-110`).

## In-scope requirements

### 1. `send_email` step config in `PlaybookEditor` (PRD #6, #1)

- For a step whose type is `send_email`, `ActionCard` (`PlaybookEditor.tsx:23-69`) renders
  two `<Select>`s below the type row:
  - **Template** — populated from `GET /api/v1/outreach/templates` via a new client
    function; registry item shape `{key, label, description}`
    (`outreach-core/spec.md` AC2, `prd.md:164`).
  - **Recipient** — `customer` (default) and `cs_assignee`.
- Config shape stored/serialized MUST match the seeder's shipped shape byte-for-byte:
  `{type: "send_email", config: {template: <key>, recipient: "customer"|"cs_assignee"}}`
  (`playbook_seeder.py:110-113, 214-217`) and the `{type, config}` consumption contract
  of the engine (`playbook_engine.py:133-136` — `_run_actions` reads
  `action.get("type")` / `action.get("config", {})`; `_dispatch_action` branch is the
  sibling aspect's job).
- Switching an existing step's type to `send_email` via the type `<Select>`
  (`onValueChange` at `PlaybookEditor.tsx:40`) initializes `config` with defaults
  (template = first registry item, fallback `re_engagement`; recipient = `customer`).
  Switching away keeps the config object (harmless — the backend stores
  `action_sequence` as free-form `List[Dict[str, Any]]`, `churn_playbook.py:20-22`,
  `:50`; the engine passes `config` only to the matching handler).
- Read-only mode (template detail view, `[id]/page.tsx:139-144` passes `readOnly`) renders
  a text summary of the config ("Email template: re_engagement → Customer"), never
  selects (mirrors the existing readOnly label at `PlaybookEditor.tsx:35-36`).

### 2. `PlaybookAction` type + labels (`lib/api/playbooks.ts`)

- Add `'send_email'` to the `PlaybookAction` type union (`playbooks.ts:6-9`) and a
  `SendEmailConfig` interface (`{template: string; recipient: 'customer' | 'cs_assignee'}`);
  the existing `[k: string]: unknown` index signature means old/stale config already
  round-trips through save/load — do not narrow it away.
- Add `send_email: 'Send Email'` to `ACTION_TYPE_LABELS` (`playbooks.ts:160-165`) so
  existing and new playbooks display the label everywhere
  (`PlaybookEditor.tsx:36` readOnly fallback, `PlaybookTemplateCard.tsx:21` badge).
- Add `send_email: <Mail />` to `ACTION_ICONS` in `PlaybookTemplateCard.tsx:13-18`.

### 3. Seeded templates render correctly through the clone flow

- Clone path: `settings/playbooks/page.tsx:175-177` → `/settings/playbooks/new?template=`
  → `new/page.tsx:18-29` fetches the template, `:47-49` spreads it into
  `defaultPlaybook` (action_sequence included), `:75-79` hands it to `PlaybookEditor`,
  whose `actions` state seeds from `playbook?.action_sequence` (`PlaybookEditor.tsx:85`).
- Because the editor state holds the seeder's raw `{type, config}` objects and
  `handleSave` serializes `action_sequence: actions` verbatim (`PlaybookEditor.tsx:111`),
  the cloned step's config pre-populates and re-saves unchanged provided the selects
  initialize from `action.config` (requirement 1). No page-level changes needed — verify
  with tests only.

### 4. Customer-profile outreach opt-out toggle (PRD #4)

- New small component `components/customers/OutreachOptOutToggle.tsx`, mounted in the
  profile header Card's action row (`customers/[email]/page.tsx:821-840`).
- Renders a shadcn `Switch` ("Send outreach emails") bound to `outreach_opt_out`.
  Toggling calls `customersAPI.updateOutreachOptOut(email, bool)` →
  `PATCH /api/v1/customers/{email}` with body `{"outreach_opt_out": bool}` only
  (`outreach-core/spec.md` #6 + AC9: admin/owner, org-scoped 404, extra fields 422,
  member 403). URL-encodes the email (`customers.ts:304` precedent).
- Initial checked state from `profile.outreach_opt_out ?? false` — see Open Questions
  for the GET-profile contract gap; the component keeps local state so it works
  regardless, optimistic on toggle, revert + `toast.error` on failure, query invalidation
  via `['customer-profile', email]` prefix (page key at `customers/[email]/page.tsx:656`;
  invalidation precedent at `:289-291`).
- **Hidden for members** (not just disabled): the codebase convention is to hide
  admin-only affordances behind `isAdminOrOwner` (`customers/page.tsx:143`,
  `{isAdminOrOwner && ...}` at `:583`, `:676`; `LinearSettings.tsx:307`). Disabled-only
  would be a new pattern and members would see a control that 403s.
- Mirror the existing toggle pattern: `Switch` + `checked` + `onCheckedChange` +
  `disabled={saving}` (`HubSpotWritebackCard.tsx:131-143`; also
  `PlaybookTemplateCard.tsx:56-60`).

## Out-of-scope boundaries

- No backend/worker changes (migration, registry, PATCH route, engine branch are
  `outreach-core` / `playbook-send-email-step` aspects — read them when they land).
- No `BulkOutreachDialog` / campaign list surface (`bulk-campaign-ui` aspect).
- No changes to `app/(dashboard)/settings/automations/**` — the automations settings
  pages are separate future work; the editor touched here is
  `settings/playbooks/**` only.
- No plan gates, no RBAC changes, no changes to the `action_sequence` backend schema
  (it is already free-form).
- No new env vars, no migration, no new packages.

## Acceptance criteria (testable, vitest)

- AC1: `PlaybookEditor` renders template + recipient selects for a `send_email` step and
  seeds both from `action.config` when present.
- AC2: saving a playbook whose first step is `send_email` serializes
  `{type: "send_email", config: {template: "weekly_digest_entry", recipient: "cs_assignee"}}`
  (exact seeder shape, `playbook_seeder.py:112`) — asserted on the `onSave` payload.
- AC3: editing an existing playbook with a `send_email` step round-trips the config
  through load → save without loss (any unknown keys preserved).
- AC4: switching a step's type to `send_email` initializes a default config; switching
  away and back preserves it.
- AC5: unknown template key (old/hand-edited playbook) renders the raw key with a warning
  and stays in state on save — never blanked.
- AC6: `GET /outreach/templates` failure degrades to the two built-in keys
  (`re_engagement`, `weekly_digest_entry`) with a visible warning — the editor remains
  fully usable and saves do not drop config.
- AC7: `ACTION_TYPE_LABELS`/`PlaybookAction` include `send_email`; the template card
  badge shows the Mail icon + "Send Email".
- AC8: clone-flow round trip: a playbook built from the "At-Risk Outreach" template
  renders its send_email step config pre-populated.
- AC9: `OutreachOptOutToggle` calls `PATCH /api/v1/customers/{email}` with
  `{"outreach_opt_out": <bool>}` on toggle; on failure the switch reverts and a toast
  fires.
- AC10: the toggle is absent from the profile for member role, present for admin/owner.

## Edge cases

- **Unknown template key**: registry-driven list can't contain an old/cloned playbook's
  key (registry is new). Show the raw key as a non-interactive/`disabled` SelectItem
  (or select-value) with a warning line; keep it in config on save. Same idiom as the
  action-type label fallback (`PlaybookEditor.tsx:36`,
  `PlaybookTemplateCard.tsx:21`).
- **Templates endpoint failing**: fall back to the two built-in keys hardcoded in
  `lib/api/outreach.ts` (they are contract-pinned: `playbook_seeder.py:111,215` and PRD
  must-have #1 names them as the minimum registry). Rationale: a transient 5xx must not
  brick editing/saving of playbooks that already contain send_email steps — data loss >
  stale label. Warn via `toast.error`.
- **`send_email` step with no config at all** (hand-crafted JSON): selects render
  defaults; save writes the resolved config — the operator sees exactly what saves.
- **Member role**: toggle hidden; PATCH would 403 anyway (backend-enforced).
- **`outreach_opt_out` missing from GET profile**: treat as `false`
  (see Open Questions).

## Dependencies & sequencing

- `outreach-core` must be merged (or its endpoint/route stubs live) for the toggle and
  the template select to work end-to-end; component tests mock the clients, so work can
  proceed in parallel — but manual verification and the final PR need the backend.
- `playbook-send-email-step` does not exist in this worktree yet (only `outreach-core/`
  and `prd.md` under `docs/planning/customer-outreach-email-actions/`) — the config
  shape here is pinned by the seeder + engine consumption contract, which is all that's
  needed. When that aspect's spec/plan land, consume them (they must not change the
  shape; if they do, flag immediately).

## Open questions / risks

- **GET-profile contract gap (flag):** `CustomerProfileResponse` (`customers.py:106-150`)
  and the serializer (`customer_profile_serializer.py:28-101`) have no
  `outreach_opt_out` field, and `outreach-core` AC9 only promises PATCH returns an
  "updated profile". The toggle renders `?? false` until the GET profile carries the
  field. Recommend (this plan): surface this to the `outreach-core` implementer so they
  add `outreach_opt_out: bool` to the serializer + `CustomerProfileResponse` and the
  frontend `CustomerProfileData` (`customers.ts:104-160`). Not a blocker — the toggle
  works optimistically either way.
- **Sibling aspect mismatch risk:** if `playbook-send-email-step` validates
  `recipient`/`template` more strictly than the editor's UI allows (or adds new
  recipients), the editor must follow. Keep the recipient list a single exported
  constant in `lib/api/playbooks.ts` so one edit updates both.
- **Radix Select in jsdom** needs the pointer-capture polyfills already in
  `vitest.setup.ts:13-16`; interact via `user.click(getByRole('combobox'))` then
  `getByRole('option', {name})` (precedent `ChurnEventsPage.test.tsx:162-187`,
  `BulkRunPlaybookDialog.test.tsx:75`).
