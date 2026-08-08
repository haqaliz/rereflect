# Card — `feat/discord-channel-preferences`

**Type:** feat (freeform — no GitHub issue)
**Branch:** `feat/discord-channel-preferences`
**Worktree:** `.claude/worktrees/feat-discord-channel-preferences`
**Opened:** 2026-08-09
**Traces to:** DEV-TRACKING P5 (`DEV-TRACKING.md:194-202`) — Post-1.0.0 User Feedback Backlog
**Picked by:** `rereflect-next` (previous session) — the one remaining user-visible
defect on the batch-2 ask path (Discord webhook + batch sentiment trigger both shipped;
this is the leftover).

## The problem

Discord alerting **rides the Slack notification toggle**. In
`services/worker-service/src/notification_dispatch.py`, `dispatch_alert` fires the
Discord webhook only when `counts["slack"] > 0` (~line 626), and the code comment says
it directly: *"There is no separate channel_discord preference yet."*

Consequences (from DEV-TRACKING P5):

- **Configure Discord, switch the Slack toggle off → you receive nothing.**
- With **both** integrations active, both get every alert, with **no per-type routing**
  — you cannot have email-only for one alert type and Discord for another.

This is a documented limitation (SELF_HOSTING.md + changelog), so it is not a surprise
to existing users — but it will read as a bug to the first person who hits it, on the
exact path a user asked for ("plug in a Slack or Discord webhook to get pinged").

## The fix (minimal slice)

- `channel_discord` column on `UserAlertPreference` + Alembic migration
  (backend model; worker reads it via its own model mirror).
- A Settings → Notifications toggle (per-user alert preferences), mirroring the Slack
  per-type toggles.
- Decouple the two dispatch calls in the worker: Slack dispatch keys off
  `counts["slack"]`, Discord dispatch keys off `channel_discord` (per-type aware).
- Default for existing rows: **TBD** (inherit Slack-toggle behavior vs default-on) —
  open question, decide up front so the migration doesn't silently change who gets
  alerted. See PRD.

## Scope guards (from DEV-TRACKING, do not expand)

- The **automations engine's notify path has no channels editor** (`DEV-TRACKING.md:189-191`
  — Discord was deliberately excluded there because `channels: ["discord"]` would be
  unreachable except via a seeded template or direct API call). **This branch stays at
  alert dispatch; the automations channels editor is out of scope.**
- No new notification *types* — this is per-channel routing of existing types.
- Slack behavior must stay byte-identical for orgs that never touch the new toggle.

## Related shipped work

- `feat/discord-notifications` (2026-07-29, SHIPPED): Discord integration CRUD + test
  route, sender per process (backend returns status dict, worker raises), dispatch on
  the main alert pipe and the health-drop path, `DiscordIcon`, provider tile, ternary
  fixes. Slack-mrkdwn template path and 429 retry deliberately excluded there.
- `notification_dispatch.py` — the shared alert pipe: per-type preferences, counts,
  Slack/email/in-app channels, digests.
