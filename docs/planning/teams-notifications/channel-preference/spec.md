# Spec: channel-preference

## Problem slice

Users can opt out of Teams alerts per notification type, exactly like `channel_discord`
(P5, `discord-channel-preferences`).

## In-scope

- Backend model `UserAlertPreference` gains `channel_teams` (default `true`) +
  one Alembic migration, chained off the current single head.
- API round-trip with the `None = unchanged` sentinel so a stale client PUT cannot
  silently flip Teams off (P5 precedent for `channel_discord`).
- Worker mirror `UserAlertPreference` (worker `models/__init__.py:390-408`) gains the
  column — the worker mirror drift is a named failure class; pin with a test.
- Frontend Settings → Notifications:
  - `lib/api/notifications.ts` `AlertPreference` gains `channel_teams` (:21-32).
  - `CHANNEL_CONFIG` (:120-126) + `renderChannelIcon` (:276-287) + `DEFAULT_PREFERENCES`
    (:83-92) gain the Teams entry (TeamsIcon, default true).
  - Customize-dialog channel list (:452-471) gains the toggle row.
- Dispatch gating: `notification_dispatch.py` health (:445-448) and generic (:633-636)
  per-user gating reads `channel_teams` like `channel_discord` (this spec owns the gating
  read; `worker-dispatch` owns the send branches — coordinate).

## Out-of-scope

Changing the Slack toggle semantics; per-rule notification prefs; P7 refactor.

## Acceptance criteria

- Migration applies cleanly; `channel_teams` defaults true for existing rows.
- PUT with `channel_teams: null` leaves the stored value unchanged.
- Toggle off → no Teams sends for that user even with an active integration; toggle on
  (default) → sends per `worker-dispatch` gating.
- Worker mirror column present; drift-pin test green.
- Backend + worker + frontend notification suites green.

## Dependencies / sequencing

Migration must precede `worker-dispatch`'s gating read. Can otherwise land in parallel.