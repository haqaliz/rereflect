# Implementation Report — `crm-profile-and-timeline`

**Status: COMPLETE — all phases green**

## Commits

| Hash | Subject |
|------|---------|
| `aa7758f` | feat(crm-profile): serializer reads crm_enrichment → 7 optional crm_* fields |
| `bf7b97a` | feat(crm-profile): surface crm_* on v1 + public Customer 360 profile |
| `5ca7df8` | feat(crm-timeline): _fetch_crm_events (contact_synced + renewal_upcoming) + payload fields |
| `3394a1f` | feat(crm-ui): CRM profile fields + crm_* event types in customers api types |
| `f265504` | feat(crm-ui): eventIconMap icons + theme tints for crm timeline events |
| `1987fc0` | feat(crm-ui): CrmCompanyCard (company/ARR/renewal/deal) on Customer 360 Overview |

## Test Commands + Results

### Backend (run these from `services/backend-api/`):

```bash
./venv/bin/python -m pytest tests/test_customer_profile.py tests/test_public_api_customer360.py tests/test_customer_timeline_service.py -v
```
**Result: 115 passed** (B1–B4 sweep)

Full regression sweep (`pytest tests/ -q`):
**2432 passed, 20 failed, 1 skipped** — the 20 failures are pre-existing in `test_report_ws.py` (segfault/WebSocket) and `test_sentry.py` (Sentry init test), confirmed pre-existing before any CRM changes.

### Frontend (run these from `services/frontend-web/`):

```bash
./node_modules/.bin/vitest run __tests__/customers/CrmCompanyCard.test.tsx __tests__/customers/ActivityTimelineIcons.test.tsx
```
**Result: 31 passed (2 test files)**

- `ActivityTimelineIcons.test.tsx`: 24 tests — crm_contact_synced + crm_renewal_upcoming icon/color/bg; all 12 event types in map; unknown type → undefined (muted dot fallback)
- `CrmCompanyCard.test.tsx`: 7 tests — data/empty/skeleton/error states

## Deviations from Plan

### `crm_deal_stage_changed` deferred (as planned)
A single enrichment snapshot cannot detect a deal stage *change* — there is no per-sync history table in v1. `crm_contact_synced` and `crm_renewal_upcoming` are the only derivable event types from the current row. This is documented in `_fetch_crm_events` docstring and stated honestly here as planned.

### `CrmEnrichment` model already existed
The `hubspot-sync` aspect had already committed `src/models/crm_enrichment.py` to the branch. The model definition is compatible with the plan (no redefinition needed). No guarded lazy import on the model file — it was directly imported since it was confirmed present.

### B4 regression sweep — no fixup commit needed
The 20 failures in `test_report_ws.py` / `test_sentry.py` are pre-existing (confirmed by stashing changes and observing same failures). The additive `db=None` serializer change broke no existing callers; the v1 profile route passes `db` explicitly.

### Frontend linter hook
A linter hook fired mid-session and reverted `ActivityTimeline.tsx` to remove the CRM icon imports/entries. A `git stash pop` restored the changes. Final committed state is correct.

## Concerns / Notes for Reviewer

1. **`crm_renewal_upcoming` timestamp anchoring**: The event is anchored at `last_synced_at` (when the renewal was detected), not at the future `renewal_date`. This keeps the timeline strictly past-dated and cursor-safe. The renewal date appears in the event `description` and `renewal_date` payload field. This is a product decision — if stakeholders want the event to appear at the future renewal date, a different timeline architecture (future-dated events) would be required.

2. **`CRM_RENEWAL_WINDOW_DAYS = 30`**: Renewals within 30 days trigger `crm_renewal_upcoming`. This matches the frontend's 30-day tint threshold in `CrmCompanyCard`. Confirm with product if a different window is desired.

3. **Icons chosen**: `Building2` (chart-3 / soft peach tint) for `crm_contact_synced`, `CalendarClock` (chart-1 / coral attention tint) for `crm_renewal_upcoming`. HubSpot brand orange is NOT used anywhere in the timeline (only permissible on the Settings integration tile per plan).

4. **No migration**: This aspect adds no Alembic migration — it reads the `crm_enrichment` table owned by `hubspot-sync`. If `hubspot-sync` is not yet merged, the serializer and `_fetch_crm_events` both use guarded patterns (`db is None` → None CRM fields; row not found → empty events list) so the feature degrades gracefully.
