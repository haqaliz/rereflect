# Aspect spec — org-config-api-and-ui

**Parent PRD:** `../prd.md` (M3) · **Slug:** `org-config-api-and-ui` · **Sequencing:** wave 2 (after data-model)

## Problem slice & outcome

The churn rule is **default-deny** (PRD M2): no suggestion is produced unless the lost deal's
HubSpot `pipeline` / Salesforce `Opportunity.Type` is in the org's configured renewal set. Both
fields are per-org CRM modelling with no portable default (`understanding.md` Finding 2), so the
org **must** name them or the feature does nothing — forever, silently. This aspect is the surface
where they do that: two endpoints per provider and one settings card per provider.

**Outcome.** An admin/owner opens Settings → Integrations, flips one Switch, picks their renewal
pipelines from a **live list fetched from their own CRM** (never free-text — PRD R2), and saves.
An org that enables but selects nothing is told plainly why it sees no suggestions.

## In scope

1. **`PATCH /api/v1/integrations/hubspot/churn-labels`** — `dependencies=[Depends(require_admin_or_owner)]`.
   Body `ChurnLabelsUpdateRequest { enabled: bool, config: Optional[Dict] = None }`, mirroring
   `JiraStatusSyncUpdateRequest` (`jira_integration.py:98`). HubSpot config shape:
   `{"renewal_pipeline_ids": ["default", "12345678"]}`.
2. **`PATCH /api/v1/integrations/salesforce/churn-labels`** — same shape; config
   `{"renewal_opportunity_types": ["Renewal", "Existing Business"]}`.
3. **`_validate_churn_label_config(config, provider, live_options)`** — mirrors
   `_validate_status_mapping` (`jira_integration.py:232`): **422** on an unknown key, a
   non-list value, a non-string member, or an id/type absent from live CRM metadata. Validation
   runs against the **live** describe/pipelines call, not a hardcoded list. Reject unknown ids
   loudly — a typo'd pipeline id is a silently-dead feature.
4. **404** if the org has no integration row at all (the setting is persisted on the integration
   row, so one must exist first — Jira precedent). **400** if the row exists but is not active
   (mirrors `/test`, `jira_integration.py:524`), since validation needs a live token.
5. **`GET /api/v1/integrations/{hubspot|salesforce}/churn-labels/options`** —
   `require_admin_or_owner`. Returns `{options: [{id, label}], provider}` for the picker:
   HubSpot `GET /crm/v3/pipelines/deals` → `{id: pipeline.id, label: pipeline.label}`;
   Salesforce `Opportunity` describe → `Type` picklist `activeValues` →
   `{id: value, label: value.label}`. Reuse the token-mint + describe path already proven in
   `services/salesforce_writeback_validation.py`. **404 if no active integration.**
6. **Broker/CRM failure → 502, never 500** (house rule, `jira_integration.py:632`). Applies to
   `/options` (upstream fetch failed) and to the PATCH's live validation call. 401/403 from the
   CRM is **recorded and surfaced, never auto-disconnects** (`is_active` untouched — PRD
   Technical Considerations).
7. **New backend service `src/services/crm_churn_label_options.py`** — one
   `fetch_renewal_options(provider, integration) -> List[Option]` seam with the two provider
   branches, so the route stays thin and the validator and `/options` share exactly one source of
   truth. Never raises; returns `(options, error_reason)` like the writeback validators'
   `(bool, reason)` contract.
8. **Response schemas** `ChurnLabelsResponse { churn_labels_enabled, churn_label_config,
   last_harvest_at, last_harvest_status, last_harvest_error, suggestions_created }` — added to the
   existing `HubSpotStatusResponse` / `SalesforceStatusResponse` too, so the card refetches status
   the way `HubSpotWritebackCard` does. **`access_token` / `refresh_token` are NEVER included**
   (house rule — `JiraStatusResponse:95` `# api_token is intentionally NEVER included`).
9. **`components/settings/HubSpotChurnLabelsCard.tsx`** and
   **`components/settings/SalesforceChurnLabelsCard.tsx`** — copy `HubSpotWritebackCard.tsx`
   structurally: `'use client'`, `if (!status.connected) return null`, shadcn `<Switch
   checked={status.churn_labels_enabled} onCheckedChange={handleToggle} disabled={saving}>`,
   local `saving`/`error` state, **no optimistic latch** (the switch reflects the `status` prop
   only; it flips when the parent refetches — asserted in the writeback test at
   `HubSpotWritebackCard.test.tsx:106`), `await api.updateChurnLabels(...)` then
   `await api.getStatus()` then `onStatusChange(refreshed)`.
10. **Picker locked while enabled** — `const inputDisabled = saving || status.churn_labels_enabled;`
    exactly as `HubSpotWritebackCard.tsx:62`. Rationale is the same: don't re-point a live
    harvester's renewal set out from under an in-flight run. The operator toggles off, edits, toggles on.
11. **`REASON_COPY` / `STATUS_COPY` maps** translating machine reasons to human copy, with the
    `friendlyReason` / `friendlyStatus` fallback-to-raw helpers. Minimum keys — reasons:
    `unknown_pipeline`, `unknown_opportunity_type`, `no_active_integration`, `options_fetch_failed`,
    `missing_read_scope`, `validation_error`; statuses: `ok`, `retrying`,
    `error: missing_read_scope`, `deferred: daily_limit` (SF).
12. **Bottom stats grid** — `grid grid-cols-2 gap-4 text-sm pt-2 border-t border-border`:
    Last Harvest (`toLocaleString()`), Last Status (`friendlyStatus`), Suggestions Created
    (`toLocaleString()`), plus a `last_harvest_error` destructive `<Alert>` below.
13. **DEFAULT-DENY empty state (critical).** When `churn_labels_enabled === true` and the config's
    renewal list is empty/absent, the card renders a **visible warning** (not a muted hint):
    HubSpot — *"No renewal pipelines selected — no suggestions will be created."*; Salesforce —
    *"No renewal opportunity types selected — no suggestions will be created."* Both with a next
    action ("Pick the pipeline your renewals close in."). The card must never present an enabled
    toggle over an empty config as a working state.
14. **Frontend API client** — `lib/api/hubspot.ts` `hubspotAPI.updateChurnLabels(
    {enabled, config})` / `hubspotAPI.getChurnLabelOptions()`; the same pair on
    `lib/api/salesforce.ts` `salesforceAPI`. Types `ChurnLabelsConfig`, `ChurnLabelOption`,
    `ChurnLabelsResponse`; extend `HubSpotConnectionStatus` / `SalesforceConnectionStatus` with the
    six churn-label fields.
15. **Mount** both cards on the integrations settings page beside the existing writeback cards,
    passing the same `status` / `onStatusChange` pair.

## Out of scope

- **The `churn_labels_enabled` / `churn_label_config` columns + migration** — owned by the
  `data-model` aspect. This aspect **consumes** them and must not migrate. (Alembic's pre-existing
  2-head fork, PRD R6, is that aspect's problem, not ours.)
- The harvester, the suggestions table, the review queue, backfill, readiness (M1/M2/M4–M7).
- Any change to `_pick_renewal_deal` / `get_open_opportunities` / the CRM clients (PRD R4).
- Fetching the churn signal itself — `/options` reads **metadata** (pipelines, picklists), not deals.

## Acceptance criteria (testable)

Backend (`pytest`, real SQLite `db` fixture + a hand-written fake client injected through the
seam — no httpx, no patching; `understanding.md` "Test style"):

1. `PATCH .../churn-labels {enabled: true, config: {renewal_pipeline_ids: ["default"]}}` on an
   active HubSpot integration → 200; row shows `churn_labels_enabled is True` and the config persisted.
2. Same PATCH with `renewal_pipeline_ids: ["nope"]` (absent from the fake's pipeline list) → **422**,
   detail names the offending id; the row is **unchanged** (no partial write).
3. Config with an unknown key, a bare-string value, or a list of non-strings → **422** each.
4. `{enabled: false}` with no config → 200, disables, **leaves the existing config intact** (Jira
   precedent: `if payload.status_mapping is not None`).
5. `{enabled: true}` with an empty/absent renewal list → **200** (allowed; the card warns). The
   API does not invent a default — silently defaulting to "all pipelines" would be exactly the
   false-label injection this PRD exists to prevent.
6. No integration row → 404. Row present but `is_active=False` → 400.
7. Fake client raising on the metadata call → **502** on both PATCH and `/options` (assert *not* 500).
8. `GET .../options` on an active integration → 200, `[{id, label}]` from the fake; no active
   integration → 404.
9. **Token leak test:** the serialized body of PATCH, `/options`, and `/status` contains neither
   `access_token` nor `refresh_token` nor the raw secret value — asserted against the response JSON.
10. A `member`-role JWT → **403** on all four endpoints.
11. An org cannot read/write another org's integration row (org-scoping).
12. Both provider suites are symmetric — same 12 cases, Salesforce shape.

Frontend (`vitest` + `@testing-library/react`, mocking `@/lib/api/{hubspot,salesforce}`, mirroring
`components/settings/__tests__/HubSpotWritebackCard.test.tsx`):

13. Renders `null` when `!status.connected` (`expect(container.firstChild).toBeNull()`).
14. Toggling on calls `updateChurnLabels({enabled: true, config: {...selected}})`, then
    `getStatus()`, then `onStatusChange(refreshed)` — in that order.
15. The switch does **not** latch optimistically: while the PATCH promise is pending the switch is
    still `data-state="unchecked"`.
16. A rejected PATCH (`{response: {data: {detail: {reason: 'unknown_pipeline'}}}}`) surfaces
    `REASON_COPY` text and leaves the switch `unchecked`.
17. **Default-deny empty state:** `churn_labels_enabled: true` + empty renewal list renders
    /no renewal pipelines selected/i and /no suggestions will be created/i.
18. Picker is `disabled` when `churn_labels_enabled` is true, and enabled when false.
19. Stats grid renders last harvest, `friendlyStatus(last_harvest_status)`, the
    `suggestions_created` count, and the `last_harvest_error` alert.
20. Both card suites are symmetric.

## Dependencies & sequencing

- **Hard-blocked on `data-model`** for `churn_labels_enabled` / `churn_label_config` on both
  integration models + the migration. Wave 2 starts when that lands.
- **Soft-depends on the harvester aspect** for `last_harvest_*` / `suggestions_created` (PRD
  Should-have). Ship the card reading them as nullable/zero; the harvester fills them. Nothing here
  blocks on it.
- **Blocks the harvester's fan-out filter** (`churn_labels_enabled.is_(True)`) and the review queue
  — nothing can be harvested until an org can configure it.
- Reuses, does not touch: `salesforce_writeback_validation.py`'s token-mint + describe path,
  `require_admin_or_owner`, `get_current_org`.

## Risks

- **R-A — `/options` is a live CRM call on a settings page render.** A slow/down CRM makes the card
  feel broken. *Mitigation:* fetch options lazily (on picker open, not card mount), 502 → the
  `options_fetch_failed` copy with a retry, and **never block the toggle's rendering** on it.
- **R-B — Locking the picker while enabled (item 10) makes editing a two-step dance.** Deliberate:
  it matches the shipped writeback card, and the alternative re-points a live harvester mid-run.
  If operators complain, revisit as a separate change — do not diverge from the house pattern here.
- **R-C — Validating against live metadata couples config-save to CRM uptime.** A pipeline deleted
  in HubSpot later makes a *previously valid* saved config stale, and the next PATCH 422s on an id
  the org didn't touch. *Mitigation:* validate only the ids **present in the incoming payload**;
  surface staleness in the picker (unknown saved id → shown, flagged), never auto-prune.
- **R-D — `Opportunity.Type` and deal `pipeline` are customizable and may be null** (PRD R5). This
  aspect only lists what the CRM returns; null-handling is the harvester's default-deny. If an org's
  picklist is empty, `/options` returns `[]` and the card must say so rather than render a dead picker.
- **R-E — Copy drift.** Three near-identical cards (writeback ×2, churn-labels ×2) invite divergence.
  Accepted per house precedent (extract-on-second-use was already declined for the writeback pair);
  keep them symmetric and let the symmetric test suites catch drift.
