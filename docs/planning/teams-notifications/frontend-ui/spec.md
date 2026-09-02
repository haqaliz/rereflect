# Spec: frontend-ui

## Problem slice

The Settings → Integrations surface offers Teams as a first-class provider: live tile,
webhook connect page, detail page, API client — Discord parity.

## In-scope

- `components/icons/TeamsIcon.tsx` (brand `#6264A7`, mirrors `DiscordIcon.tsx`).
- Integrations list `app/(dashboard)/settings/integrations/page.tsx`:
  - Replace the "Microsoft Teams — Coming Soon" placeholder tile (:1447-1465) with a
    live tile linking to `/settings/integrations/new?type=teams`.
  - Icon/color ternary (:301-317) gains a Teams branch (`bg-[#6264A7]/10`, TeamsIcon).
  - Test-dispatch ternary (:178-180) gains `type === 'teams' ? testTeams : …`.
- Connect page `new/page.tsx`: type union gains `'teams'` (:38); URL validator for the
  two accepted hosts (mirror `DISCORD_WEBHOOK_URL_PREFIXES` :44-51); type-selector tile
  (:262-322) with `setConnectionMethod('webhook')`; header copy (:205-230); submit
  branch (:160-164) → `createTeamsWebhook`; placeholder/help text (:489-519, :580-583).
- Detail page `[id]/page.tsx`: test dispatch (:167-169), header icon/color (:281-295),
  subtitle (:311-315), status copy (:369-374), webhook-format hint (:518) — Teams
  MessageCard copy. **`channel_name`/`team_name` rendering:** Teams `config` has neither
  — the detail page must hide/omit those fields for Teams instead of rendering blanks.
- API client `lib/api/integrations.ts`: `createTeamsWebhook` + `testTeams` (:120-151
  shape); template-variables call gains a non-Slack path if Teams ever needs it (only
  if the endpoint supports it — verify; otherwise leave).
- Tests mirroring `__tests__/settings/NewIntegrationPage.discord.test.tsx` /
  `IntegrationsListPage.discord.test.tsx` / `IntegrationDetailPage.discord.test.tsx`.

## Out-of-scope

Notifications toggle (see `channel-preference`); PlaybookEditor select (see
`playbook-notify`); inbound source UI.

## Acceptance criteria

- "Coming Soon" tile gone; live tile navigates to the connect page with `type=teams`.
- Valid classic/Workflows URL submits and persists; invalid URL shows the validator
  error without submitting.
- Test button on the detail page calls `POST /api/v1/integrations/teams/test` and
  renders success/error.
- Frontend lint + test suite green (incl. the three mirrored test files).

## Dependencies / sequencing

Depends on `backend-connector` (endpoints). UI can proceed in parallel with the worker
aspects.