# Spec — worker-dispatch

**Aspect of:** `discord-channel-preferences` · **PRD refs:** R3, R4, R6 (worker half)
**Date:** 2026-08-09

## Problem slice and user outcome

The worker must dispatch Discord alerts off **their own** per-type
`channel_discord` preference, independently of the Slack toggle, on **both**
dispatch pipes — the main alert pipe (`dispatch_alert`) and the health-drop pipe
(`dispatch_health_drop_alert`) — and the worker model mirror must carry the new
column (plus the pre-existing missing `channel_intercom`) or the worker silently
ignores both.

## In-scope requirements

- **Worker model mirror**
  (`services/worker-service/src/models/__init__.py:379-395`): add
  `channel_discord` (`Boolean, default=True, nullable=False`) **and** back-fill
  `channel_intercom` (`Boolean, default=False, nullable=False`) — both mirror the
  backend model so the two copies converge.
- **Main pipe (`dispatch_alert`, `notification_dispatch.py:542-632`):**
  - counts dict gains `"discord": 0` (`:571`); docstring return note updated.
  - per-user loop: `channel_discord = pref.channel_discord if pref else True`
    (`:599` area); `if channel_discord: counts["discord"] += 1`.
  - dispatch block (`:625-630`): Slack fires on `counts["slack"] > 0`; Discord
    fires on `counts["discord"] > 0` — **two independent ifs**, comment removed.
- **Health-drop pipe (`dispatch_health_drop_alert`, `:306-474`):**
  - counts dict gains `"discord": 0` (`:333`); docstring updated.
  - per-user loop (`:408-439`): add `channel_discord` read + `any_discord` flag
    (mirroring `any_slack`).
  - dispatch block (`:443-468`): Slack path unchanged under `any_slack`; Discord
    embeds + `_dispatch_discord_health_alert` move to their own `if any_discord:`.
- **Tests:** rework the two coupling tests to assert independent dispatch:
  - `test_discord_dispatch.py::TestDispatchAlertTriggersDiscord` — split into
    Slack-on/Discord-off and Slack-off/Discord-on cases + both-on.
  - `test_discord_health_dispatch.py::TestDispatchHealthDropAlertTriggersDiscord`
    — same split.
  - Check `test_health_dispatch.py` for exact counts-dict shape assertions and
    extend if the new key breaks equality.

## Out-of-scope boundaries

- No backend API/model changes here (aspect `backend-prefs-api`).
- No frontend changes (aspect `frontend-page`).
- The backend health-drop impl (`notification_dispatch_helpers.py`) and its false
  docstring — separate tracked defect, not touched.
- Automations-engine notify channels — out of scope (PRD).

## Acceptance criteria (testable)

1. A user with `channel_slack=True, channel_discord=False` gets Slack dispatch
   but **no** Discord dispatch (main pipe).
2. A user with `channel_slack=False, channel_discord=True` gets Discord dispatch
   but **no** Slack dispatch (main pipe).
3. Same two cases on the health-drop pipe (`_dispatch_discord_health_alert` /
   `_dispatch_slack_health_alert`).
4. No-pref-row user defaults to `channel_discord=True` (Discord fires like today).
5. Counts dicts include `"discord"`; all existing callers
   (`insights.py:82`, `anomaly.py:185`, `alerts.py:315`, `alerts.py:749`) still
   receive a valid dict (only additive key).
6. Worker suite green: `cd services/worker-service && pytest tests/ -v`.

## Dependencies and sequencing notes

- Depends on `backend-prefs-api` (schema exists in the same migration).
- Runs before `frontend-page` (no frontend dependency, but sequencing keeps the
  branch coherent).

## Open questions or risks

- `test_health_dispatch.py` assertions on counts shape: verify before assuming —
  extend fixture expectations if exact-dict assertions exist.
- The worker mirror gains `channel_intercom` that nothing reads at dispatch —
  behavior-neutral, confirmed by worker suite.
