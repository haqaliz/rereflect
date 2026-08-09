# Phase 2 — Understanding: `feat/discord-channel-preferences`

**Dug:** 2026-08-09, against the worktree at `feat/discord-channel-preferences`
(base `4fe117d3`). Three parallel dig agents (worker / backend / frontend) mapped
the notification system; both disputed claims re-verified directly with `file:line`
reads after synthesis. Live-verified: single alembic head `8114adde5d96`.

---

## What the feature is really asking

Discord alerting currently **rides the Slack per-type toggle**: a user cannot
receive Discord alerts without Slack being on for the same alert type, and cannot
route types independently to each channel. The fix is a `channel_discord` per-type
preference on `UserAlertPreference` (per-user, per-alert-type row — the model
already follows the column-per-channel pattern), surfaced in the Settings →
Notifications page, and honoured by the worker's dispatch.

**The honest one-line framing:** *configure Discord, switch the Slack toggle off,
and you receive nothing* — DEV-TRACKING P5.

---

## F1 — The coupling, exactly (premise verified)

Two sites in the worker gate Discord on the Slack flag:

- **Main pipe** — `services/worker-service/src/notification_dispatch.py:626-631`:
  `if counts["slack"] > 0: _dispatch_slack_alert(...)` then
  `_dispatch_discord_alert(...)` unconditionally inside the same block. Comment
  at 628-629: *"There is no separate channel_discord preference yet — Discord
  webhook integrations piggyback on the same 'chat' toggle as Slack."*
- **Health-drop pipe** — `notification_dispatch.py:443-468`:
  `if any_slack:` sends `_dispatch_slack_health_alert` **and**
  `_dispatch_discord_health_alert` from the same flag. No `channel_discord` read
  anywhere in the function (only `channel_slack` at :417).

`channel_discord` does not exist anywhere in the worktree (backend model, worker
model, migrations, frontend types, tests) — grepped, zero hits.

---

## F2 — The worker health-drop path is production-dormant (scope wrinkle)

- The worker's `dispatch_health_drop_alert` (with its Slack + Discord health
  builders/dispatchers) has **no production caller** in worker-service — grep
  shows only its definition and tests.
- The live path is backend-only: `health_score_service.py:877,900`
  (`_do_dispatch_health_drop_alert`) → `notification_dispatch_helpers.py:133`
  `dispatch_health_drop_alert_impl`, which creates **in-app `Notification` rows
  only** (is_enabled + channel_inapp; never Slack/Discord), despite a docstring
  (lines 148-150) claiming it "delegates dedup and Slack to the worker".
- Consequence: in production today, `customer_health_drop` alerts never reach
  Slack or Discord at all. The health-drop Discord coupling is exercised by tests
  (`test_discord_health_dispatch.py`, `test_health_dispatch.py`) but not by any
  live dispatch.
- **Decision for the PRD:** fix the health-drop worker path for consistency
  (same pattern, tests already pin it, and it is the documented home of
  Slack/Discord health alerts) — or scope to the main pipe and record the
  health-drop coupling as dead-code debt. Recommendation: fix both; leaving one
  coupled recreates the trap for whoever wires the worker path.

---

## F3 — Model mirror drift (trap to avoid)

- Backend model: `services/backend-api/src/models/user_alert_preference.py:5-25`
  — columns: `is_enabled`, `channel_email` (default False), `channel_slack`
  (default True), `channel_inapp` (default True), `channel_intercom` (default
  False), `threshold_value`, `retention_days`, `drop_threshold` handled as a
  secondary row (`_DROP_THRESHOLD_KEY`). UNIQUE(user_id, alert_type).
- Worker mirror: `services/worker-service/src/models/__init__.py:379-395` — same
  shape **minus `channel_intercom`** (the `d3e4f5g6h7i8` migration never landed
  in the mirror). Pre-existing drift; `channel_discord` must be added to **both**
  copies or the worker silently ignores it (the automations-engine trap class,
  per CLAUDE.md).
- Migration precedent to copy: `d3e4f5g6h7i8_add_channel_intercom_to_alert_prefs.py`
  (`add_column(... server_default='false')`). New migration chains onto
  `8114adde5d96`; CI asserts one head.

---

## F4 — Backend API + frontend plumbing

- Routes: `GET/PUT /api/v1/notifications/preferences`
  (`routes/notifications.py:325-442`). `AlertPreferenceUpdate` (L98-133) requires
  all channel bools on PUT (wholesale copy, L396-410) — adding
  `channel_discord: bool = False` as an optional field keeps the API
  backward-compatible; `AlertPreferenceItem` (L82-91) already shows the
  `channel_intercom=False` default pattern.
- Frontend: `lib/api/notifications.ts:21-31` `AlertPreference` interface (needs
  `channel_discord`); `app/(dashboard)/settings/notifications/page.tsx` —
  `CHANNEL_CONFIG` (L119-124: In-App, Slack, Intercom, Email — the list a Discord
  entry joins), `DEFAULT_PREFERENCES` (L82-91, all 8 types need the new key or
  first-load renders `undefined`), `getActiveChannels` (L264-271) and
  `renderChannelIcon` (L273-282) need Discord branches, Customize dialog
  iterates `CHANNEL_CONFIG` (L442-459).
- The page renders channel toggles **unconditionally** (no integration-connected
  state is fetched; there is no integrations hook/context). Keep Discord
  consistent: render the toggle unconditionally — the org-level Discord
  connection is a separate surface (Settings → Integrations).
- Frontend test coupling: `__tests__/settings/NotificationsSettingsPage.test.tsx:255-277`
  assumes Email is the **last** switch in the dialog — Discord must be inserted
  before Email (e.g. In-App, Slack, Discord, Intercom, Email) or the test
  updated; fixtures L69-91 also need the new key.
- Worker test coupling: `test_discord_dispatch.py:213-251` and
  `test_discord_health_dispatch.py:230-271` assert Discord fires from
  `channel_slack=True` — both must be reworked to assert the new pref.

---

## Open questions for the PRD

1. **Default for `channel_discord`.** Follow the `channel_intercom` precedent
   (`False` — Discord becomes per-user per-type opt-in; existing Discord-sending
   orgs stop getting Discord after upgrade until a user toggles it) **or**
   default `True` matching `channel_slack` (existing behavior preserved where
   Slack is on; the feature becomes opt-*out* per type; orgs that had Slack off
   start receiving Discord — a visible behavior change the UI makes legible).
   Needs a decision; card's original caveat.
2. **Health-drop scope** (F2): fix both worker paths or only the main pipe.
3. **Counts dict shape.** `counts` is `{"inapp", "slack", "email"}` in
   `dispatch_alert` (L571) and `{"inapp", "slack", "email"}`-family in the
   health-drop path — add a `"discord"` key (return contract is a status dict;
   check exact-shape assertions in `test_health_dispatch.py` before committing).
4. **Channel order in the dialog** (frontend test index math) — insert Discord
   after Slack, before Email.

---

## Contradictions / flags surfaced (do not paper over)

- The `notification_dispatch_helpers.py:148-150` docstring claim ("delegates
  dedup and Slack to the worker-service notification_dispatch when called from
  the Celery context") is false in code — no delegation exists. Separate defect,
  noted; **not** in scope for this feature (flag in PRD as related finding).
- The worker mirror missing `channel_intercom` (F3) is a live divergence; adding
  `channel_discord` to both copies is in scope, back-filling `channel_intercom`
  into the mirror is a judgement call (recommend: add both columns to the mirror
  in the same migration to stop the drift — or explicitly leave `channel_intercom`
  as separate debt).
- `_send_anomaly_discord` / `_send_anomaly_slack` (`tasks/anomaly.py:220,285`)
  are dead code with tests (DEV-TRACKING P6) — not touched here.
