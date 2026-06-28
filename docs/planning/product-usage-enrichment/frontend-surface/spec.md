# Aspect Spec — frontend-surface

Parent PRD: `../prd.md`

## Problem slice & outcome

The operator sees product usage on the Customer 360 profile (a "Usage Activity" card + usage-over-time chart), the 5th component in the health breakdown, and a settings/docs section explaining how to send usage events.

## In scope

- `lib/api/customers.ts`: add `getUsage(email, days=30)` (pattern `:163-231`, axios bearer interceptor `lib/api-client.ts:14-29`); types `CustomerUsageResponse`, `UsageHistoryEntry`; add `usage_component: number` to `CustomerProfileData`.
- `components/customers/ComponentProgressBars.tsx:16-21`: add 5th `{key:'usage', label:'Usage Activity'}` + tooltip + description band; accept `usage_component` prop.
- `components/customers/UsageTimeline.tsx`: new, copy `HealthTimeline.tsx` (Recharts `LineChart`, 30/60/90 toggle, CSS-var colors — never hardcode).
- Profile page `app/(dashboard)/customers/[email]/page.tsx`: render a "Usage Activity" Card (last active, logins/active-days, distinct features) + `<UsageTimeline>`, slotted after Health Timeline (~`:688`); pass `usage_component` to `ComponentProgressBars`.
- (should-have) Customers list `app/(dashboard)/customers/page.tsx`: add a "Last active (product)" column distinct from `last_feedback_at`.
- Settings/docs: a section (settings page + `SELF_HOSTING` doc) describing `POST /api/v1/webhooks/usage`, the normalized schema, ingest-key creation, a curl example, and a "verify it's working" note. Inbound — **not** the existing outbound `settings/webhooks` CRUD.

## Out of scope

- Backend endpoints/score (other aspects). This aspect consumes `GET /customers/{email}/usage` and the `usage_component` field.

## Acceptance criteria (testable)

1. Profile shows "Usage Activity" with last-active, frequency, and feature breadth when usage exists; shows an empty/neutral state when none.
2. `ComponentProgressBars` renders 5 bars including Usage; existing 4-bar snapshots updated.
3. `UsageTimeline` renders the daily series from `getUsage`; period toggle refetches.
4. No hardcoded colors (CSS vars only); `npm run lint` + `npm run test` pass.
5. Settings/docs section renders the endpoint + schema + curl, gated to admin/owner per existing settings pattern (display-only; no plan gating).

## Dependencies & sequencing

- Build last. Depends on `usage-rollup-and-score` (read API) and `health-component` (`usage_component` field). Can be developed against mocked API responses in tests before the backend merges.

## Open questions / risks

- Whether to also surface a usage badge on the customers list rows (kept as should-have).
- Exact copy for the "verify it's working" operator note.
