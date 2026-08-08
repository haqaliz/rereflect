# PRD — Discord channel preferences

**Slug:** `discord-channel-preferences` · **Branch:** `feat/discord-channel-preferences`
**Type:** feat (freeform — no GitHub issue) · **Date:** 2026-08-09
**Card:** `../_card/card.md` · **Understanding:** `../_card/understanding.md`
**Traces to:** DEV-TRACKING P5 (`DEV-TRACKING.md:194-202`) — Post-1.0.0 User Feedback Backlog
**Status:** DRAFT (awaiting review gate)

---

## Problem Statement

Discord alerting **rides the Slack per-type toggle**. In the worker's
`notification_dispatch.py`, the Discord webhook fires only when at least one user
in the org has `channel_slack` enabled for that alert type — the coupling is
explicit at `notification_dispatch.py:626-631` (main pipe) and `:443-468`
(health-drop pipe), with an in-code comment admitting it: *"There is no separate
channel_discord preference yet — Discord webhook integrations piggyback on the
same 'chat' toggle as Slack."*

Consequences:

- **Configure Discord, switch the Slack toggle off → you receive nothing.**
- With **both** integrations active, both get every alert — there is **no
  per-type routing** (e.g. email-only for one alert type, Discord for another).
- The user asked for this channel in the first place (batch-2 feedback: "plug in
  a Slack or Discord webhook to get pinged" — shipped as
  `feat/discord-notifications`); this coupling is the leftover defect on that ask
  path.

It is a documented limitation today (SELF_HOSTING.md + changelog), so it is not a
surprise to existing users — but it will read as a bug to the first person who
hits it, which is the same silent-failure class the post-1.0.0 backlog has been
stamping out.

## Goals & Success Metrics

- **G1.** A user can receive Discord alerts for an alert type with Slack **off**
  for that type (and vice-versa) — per-type channel routing is independent.
- **G2.** Existing installs that already receive Discord alerts keep receiving
  them after upgrade with zero configuration (default preserves current
  behavior).
- **G3.** The worker honours the new preference on both dispatch pipes; Slack
  behavior is byte-identical for orgs that never touch the new toggle.
- **G4.** No delivery regression for orgs currently receiving Discord. The one
  intended change (a type with Slack off, Discord on) is per-type, visible in the
  UI, and under the user's control — never hidden in the migration.

**Measured by:** worker tests asserting per-type independent Slack/Discord
dispatch (both pipes); backend preference round-trip tests; frontend
preferences-page tests. No product metrics — this is a correctness/credibility
fix on a shipped user ask.

## User Personas & Scenarios

- **Self-hoster, Discord-only notifications** (the motivating case): configured a
  Discord webhook under Settings → Integrations, wants all alerts there, does not
  use Slack. Today: silently receives nothing unless a user's Slack toggle is on.
  After: enables Discord per type (or relies on the default) and receives alerts;
  Slack stays off.
- **Mixed-channel power user**: wants critical/urgent types on Discord + in-app,
  routine types email-only, Slack off. Today impossible. After: per-type toggles.
- **Slack-only org**: never connects Discord. After: nothing changes (no Discord
  integration rows → no Discord sends, whatever the toggles say).

## Requirements

### Must-have

- **R1 — Data model:** `channel_discord` Boolean column on `UserAlertPreference`
  (per-user, per-alert-type), **default `True`** (`server_default='true'`),
  nullable=False, on the backend model **and** the worker-service mirror model.
  Same change back-fills the missing `channel_intercom` column into the worker
  mirror so the two models converge (pre-existing drift, see
  `understanding.md` F3). One Alembic migration chaining onto `8114adde5d96`.
- **R2 — Preferences API:** `GET/PUT /api/v1/notifications/preferences` accept
  and return `channel_discord` (response item default `False` for absent fields
  at the API layer; the DB default is `True`). **PUT absent-field semantics:**
  `channel_discord` must be `Optional[bool] = None` on the request schema, where
  `None` means **leave the column unchanged** — a stale client that PUTs without
  the field must not silently flip Discord off (the PUT handler wholesale-copies
  every channel bool, `routes/notifications.py:396-410`, so a `bool = False`
  default would be written over the DB default). Frontend ships atomically with
  backend in this monorepo; the None-sentinel protects stale browser tabs.
- **R3 — Worker main pipe:** `dispatch_alert` adds a `"discord"` key to the
  counts dict; Discord dispatch keys off **its own** per-type flag
  (`channel_discord`), independent of `counts["slack"]`; per-user default when no
  pref row exists is `True` (matching the column default). Slack dispatch
  unchanged. **Counts-dict consumers to check for exact-shape assertions before
  committing:** `insights.py:82`, `anomaly.py:185`, `alerts.py:315`,
  `alerts.py:749`, plus the worker test suites (`test_health_dispatch.py`,
  `test_discord_dispatch.py`).
- **R4 — Worker health-drop pipe:** `dispatch_health_drop_alert` gains the same
  independent `channel_discord` gate, decoupled from the `any_slack` flag
  (both worker paths per confirmed scope — the worker health-drop path is
  production-dormant today, see `understanding.md` F2; it is fixed for
  consistency so the coupling cannot resurface when wired).
- **R5 — Frontend:** Settings → Notifications page — `CHANNEL_CONFIG` gains a
  Discord entry (icon `DiscordIcon`, label "Discord"), `DEFAULT_PREFERENCES` and
  the `AlertPreference` API type gain `channel_discord` for all 8 alert types,
  and `getActiveChannels`/`renderChannelIcon` render the Discord channel. The
  Discord toggle renders **unconditionally**, exactly like the Slack and Intercom
  toggles today (no integration-connected state fetch — the org-level connection
  is the Settings → Integrations surface).
- **R6 — Tests:** rework the two worker coupling tests
  (`test_discord_dispatch.py::TestDispatchAlertTriggersDiscord`,
  `test_discord_health_dispatch.py::TestDispatchHealthDropAlertTriggersDiscord`)
  to assert independent dispatch; add coverage for the new per-type flag on both
  pipes; backend preference round-trip tests **including a PUT that omits
  `channel_discord` and asserts the stored value is unchanged** (R2 sentinel);
  frontend page tests.

### Should-have

- **S1 — Docs:** update `docs/SELF_HOSTING.md` (the notifications section that
  documents the current limitation) and the changelog entry for the Discord
  feature; the P5 limitation note is replaced with the new behavior.
- **S2 — Discovery copy:** the "readiness" style surfaces that mention the Slack
  toggle coupling (if any remain) are updated.

### Nice-to-have

- **N1 — Counts/digest parity:** the daily digest (`send_daily_alert_digests`)
  and volume-spike path keep reading only `channel_email` — unchanged, out of
  scope. If the counts dict shape is asserted exactly anywhere, that assertion is
  updated as part of R3.

## Technical Considerations

**Services changed:** `services/backend-api` (model + migration + preferences
routes + tests), `services/worker-service` (model mirror + `notification_dispatch.py`
both pipes + tests), `services/frontend-web` (page + API client + tests).

**Key mechanics:**

- Preferences are **per-user, per-alert-type** rows (`UNIQUE(user_id, alert_type)`),
  column-per-channel. Discord sends remain **per-org once** (query
  `Integration(type == "discord", is_active)`), fired when **any** user in the
  org opted in for that type — exactly the Slack fan-out model.
- Default `True` is load-bearing for G2: a fresh row behaves like today (Slack
  on → Slack + Discord both fire); the change is strictly additive per type. The
  only behavior change is the intended one: a type with Slack off but Discord on
  now fires Discord.
- Migration follows the `d3e4f5g6h7i8_add_channel_intercom_to_alert_prefs.py`
  precedent (`add_column(..., server_default='true')`); CI asserts a single
  alembic head.
- No new notification types, no new webhook events, no new delivery transports.

**Multi-tenancy:** unchanged — prefs are user-scoped (org via user), Discord
send is org-scoped via the integration row filter. No cross-org data.

## Risks & Open Questions

- **Risk: migration silently changes who gets Discord.** Default `True` means a
  user who explicitly disabled Slack for a type starts receiving Discord for it
  (if the org has a Discord webhook). Mitigation: this is the feature's intent,
  the UI shows the per-type toggle, and Discord delivery requires a deliberately
  created integration. Accepted.
- **Risk: stale-client PUT flips Discord off.** A pre-upgrade browser tab editing
  any preference would send no `channel_discord`; the request schema must treat
  `None` as "leave unchanged" (R2), or the edit silently disables Discord for
  that type. Mitigated by the R2 sentinel + a round-trip test that PUTs without
  the field and asserts the stored value is untouched.
- **Risk: worker mirror drift recurs.** Both models are edited in this change;
  a future column added to only one model reintroduces the silent-ignore trap.
  Mitigated by the back-fill (R1) — no new divergence is created.
- **Open:** should the UI hint when a Discord toggle is on but the org has no
  Discord integration connected? Slack/Intercom toggles render unconditionally
  today (consistency says: no hint, keep parity); recorded, not decided here.
- **Open:** the backend health-drop impl (`notification_dispatch_helpers.py:133`)
  is in-app only and its docstring falsely claims worker delegation
  (`:148-150`) — a separate defect, recorded, **not** fixed here.
- **Open:** the `channel_intercom` worker mirror back-fill means the worker now
  reads a column it previously ignored — behavior-neutral today (nothing reads
  `channel_intercom` at dispatch), verified by the worker suite.

## Out of Scope

- **Automations-engine notify channels** (DEV-TRACKING `P2` scope note): there
  is no channels editor in the automations UI; `channels: ["discord"]` stays
  unreachable there. A channels editor is a separate feature.
- No new alert types, no per-org defaults, no channel-aware audit/provenance on
  `Notification` rows (only `metadata` exists).
- Not fixing: the health-drop docstring lie (`notification_dispatch_helpers.py:148-150`),
  the dead `_send_anomaly_discord`/`_send_anomaly_slack` functions (DEV-TRACKING
  P6), the legacy `users.alert_channels`/`organizations.default_alert_channels`
  JSON channel system, or the Slack/Intercom OAuth plaintext-token issue — all
  tracked separately.
- No plan gating — all unlocked (OSS self-hosted).

## Non-Functional Requirements

- Backend and worker suites stay green (`pytest tests/ -v` in each service);
  frontend `npm run test` + `npm run lint` green; single alembic head.
- Strict TDD: RED → GREEN → REFACTOR per task; commit per task on
  `feat/discord-channel-preferences`.
