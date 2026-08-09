# Spec — frontend-page

**Aspect of:** `discord-channel-preferences` · **PRD refs:** R5, R6 (frontend half)
**Date:** 2026-08-09

## Problem slice and user outcome

The Settings → Notifications page exposes a per-type **Discord** channel toggle so
a user can route each alert type to Discord independently of Slack, and the row
indicators show Discord as an active channel.

## In-scope requirements

- **API type**
  (`services/frontend-web/lib/api/notifications.ts:21-31`): `AlertPreference`
  gains `channel_discord: boolean`.
- **Page** (`app/(dashboard)/settings/notifications/page.tsx`):
  - `CHANNEL_CONFIG` (`:119-124`): insert
    `{ key: 'channel_discord' as const, label: 'Discord', icon: null, customIcon: 'discord' }`
    **after Slack, before Intercom** (Email must stay last — frontend test index
    math).
  - `DEFAULT_PREFERENCES` (`:82-91`): add `channel_discord: true` to all 8 rows
    (matches DB default semantics).
  - `getActiveChannels` (`:264-271`): push `'Discord'` when `pref.channel_discord`.
  - `renderChannelIcon` (`:273-282`): `case 'channel_discord': return <DiscordIcon className={size} />;`
    (import `DiscordIcon` — exists at `components/icons/DiscordIcon.tsx`).
  - The Customize dialog iterates `CHANNEL_CONFIG` (`:442-459`) — no further
    change needed for the toggle itself.
- **Tests** (`__tests__/settings/NotificationsSettingsPage.test.tsx`):
  - Fixtures (`:69-91`) gain `channel_discord`.
  - Assert the dialog renders a Discord switch; keep the "Email is last switch"
    assertion valid (Discord inserted before Email).
  - Assert a Discord-only round-trip: toggle Discord on / Slack off for a type →
    save payload contains `channel_discord: true`.

## Out-of-scope boundaries

- No backend/API contract changes here (aspect `backend-prefs-api`).
- No landing-page / README copy (aspect `docs`).
- No integration-connected-state fetch: the Discord toggle renders unconditionally,
  exactly like the Slack and Intercom toggles today (PRD open question, decided:
  parity, no hint).
- Global `alert_channels` on `/settings/preferences` — untouched (different
  legacy surface, out of scope per PRD).

## Acceptance criteria (testable)

1. Page renders a per-type Discord switch in the Customize dialog; Email remains
   the last switch.
2. Saving a type with Discord on and Slack off persists and reloads
   `channel_discord: true`.
3. Row indicator shows "Discord" among active channels when on.
4. `npm run test` and `npm run lint` green in `services/frontend-web`.

## Dependencies and sequencing notes

- Depends on `backend-prefs-api` (API field) and `worker-dispatch` (behavior).
- Tests run via vitest in `services/frontend-web`.

## Open questions or risks

- The DiscordIcon's `customIcon` rendering path must be verified in the dialog
  (`CHANNEL_CONFIG` icon switch) — if the dialog only renders `icon` components,
  the `customIcon` mechanism already handles Slack/Intercom, so Discord follows
  the same path.
