# Aspect spec — `mapping-editor`

Part of PRD `status-sync-realtime-mapping`. Independently shippable; no webhooks.

## Problem slice & user outcome
An operator (admin/owner) can **see and edit** the foreign-status →
Rereflect-state mapping for Jira, Asana, and Zendesk, in-app. Today the mapping
is stored + PATCH-able + serialized by the frontend clients, but no UI exposes
it (only Linear has an editor).

## In scope
- **Frontend**
  - `components/settings/StatusMappingEditor.tsx` — shared, generalized from
    `LinearSettings.tsx` "Status Mapping" tab. Props: `foreignKeys` (ordered list
    of `{ key, label }`), `currentMapping: Record<string,string> | null`,
    `targetStates` (shared `REREFLECT_STATUSES`), `onSave(mapping) => Promise`,
    `disabled`. Renders one row per foreign key, a `Select` of target states per
    row, dirty-tracking, Save button (sonner toast on success/error), and a
    "reset to defaults" affordance (N1 — clears override).
  - Mount it inside `JiraStatusSyncCard`, `AsanaStatusSyncCard`,
    `ZendeskStatusSyncCard` (below the existing toggle). Save via the existing
    `patch{Jira,Asana,Zendesk}StatusSync(enabled, statusMapping)`.
  - Provider foreign-key lists are **hardcoded canonical constants** (no
    discovery endpoint): Jira `["new","indeterminate","done"]` (labelled as
    *status categories*), Asana `["new","done"]`, Zendesk
    `["new","open","pending","hold","solved","closed"]`. Labels must make the
    Jira/Asana "category" nature explicit (G4/M8).
  - Shared `REREFLECT_STATUSES` relocated out of `lib/api/linear.ts` into a
    shared module (e.g. `lib/constants/workflow-status.ts`); Linear import
    updated.
  - `lib/api/jira.ts`, `lib/api/asana.ts`: add `status_mapping:
    Record<string,string> | null` to `JiraConnectionStatus` /
    `AsanaConnectionStatus` (Zendesk already has it) so the editor hydrates.
- **Backend (small)**
  - `JiraStatusResponse` (`api/routes/jira_integration.py`) and
    `AsanaStatusResponse` (`api/routes/asana_integration.py`): add
    `status_mapping` to the GET `/status` response (Zendesk already returns it).
  - Keep existing `_validate_status_mapping` (422 on bad keys/values) unchanged.

## Out of scope
- Any webhook work. Per-raw-status-name granularity for Jira/Asana. Live status
  discovery. Changes to the stored mapping semantics / defaults.

## Acceptance criteria (testable)
- **Backend:** GET `/api/v1/integrations/jira/status` and `.../asana/status`
  include `status_mapping` reflecting the stored value (null when unset). Existing
  route tests extended; `test_jira_status_sync_routes.py` /
  `test_asana_status_sync_routes.py` assert the new field.
- **Frontend:** `StatusMappingEditor` unit test (Vitest + RTL): renders a row per
  foreign key, shows current mapping selected, marks dirty on change, calls
  `onSave` with the full mapping object, toasts on success/failure.
- Each provider card test asserts the editor is rendered with the right foreign
  keys and that saving calls the provider's `patch*StatusSync` with
  `(enabled, mapping)`.
- `REREFLECT_STATUSES` relocation doesn't break Linear (its tests stay green).
- Editor is read-only/hidden for non-admin (mutations already gated; mirror card
  behavior).

## Dependencies & sequencing
- Independent of all other aspects. Can run first / in parallel with
  `status-writer-race-guard`.

## Open questions / risks
- Copy for the Jira/Asana "category" labels — keep honest ("Status category:
  In-progress (indeterminate)"). Decide final labels during implementation.
- Whether to show the effective merged mapping (default+override) as a preview
  (N2) — nice-to-have, only if cheap.
