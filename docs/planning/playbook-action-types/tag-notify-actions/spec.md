# Aspect — `tag-notify-actions`

**Slice:** M1 + M2 — the `tag` and `notify` playbook actions in the worker engine.
Pure worker-side, no schema change beyond a model-mirror column.

**PRD requirements:** M1, M2.

---

## Problem slice & outcome

A seeded playbook step `{"type": "tag", "config": {"tag": "at-risk"}}` writes the tag to the
customer's `customer_health_scores.tags`; a step `{"type": "notify", "config": {"channel":
"slack", "target": "#cs-leads", "message": "..."}}` delivers the message to the org's
connected Slack/Discord integration (and/or in-app notifications), instead of both failing
with `unsupported action type`.

## In scope

1. **Worker `CustomerHealth` mirror gains `tags`** (`services/worker-service/src/models/__init__.py`)
   — JSON column, `nullable=True`, matching the backend column
   (`backend-api/src/models/customer_health.py:68-72`). Model-only; the column already
   exists in the DB (backend shipped it via segment-actions), so **no Alembic migration**.
2. **`_handle_tag(config, customer_email, health, db)`** in
   `services/worker-service/src/services/playbook_engine.py`:
   - config `{tag: str}`; normalize (trim), require non-empty, ≤50 chars, ≤20 tags/customer
     (mirrors `customers.py:664-681,713-724` bulk-tag constraints)
   - add-if-absent into `health.tags` (JSON array), sorted; over-cap → `ok: False` with a
     specific reason, customer row unchanged
   - side effect is visible after the run (committed by `_finalize_execution`)
3. **`_handle_notify(config, customer_email, health, db)`**:
   - config `{channel: "slack"|"discord"|"dashboard", target?: string, message: string}`
   - `slack` → send the message to the org's connected Slack integration(s) (webhook or
     OAuth channel, via `src/tasks/alerts.py` senders, wrapped so the sender's raise
     contract becomes `ok: False`); `target` advisory — the integration's configured
     channel is used, and `target` is recorded in the result
   - `discord` → same via `send_discord_message_webhook`
   - `dashboard` → `Notification` rows for admins, honoring `UserAlertPreference`
     (reuse the `notification_dispatch` `dispatch_alert` seam; report
     `{notifications_created: N}`)
   - no integration connected for the requested channel → `ok: False`, specific reason
   - unknown channel → `ok: False`, loud
4. `_dispatch_action` branches for `tag` and `notify`.

**Models to read first (all worker-side):** `notification_dispatch.py:578-672`
(`dispatch_alert`), `notification_dispatch.py:675-829` (slack/discord send paths),
`automation_feedback_trigger.py:676-827` (channel-aware `send_notification` precedent),
`tasks/alerts.py` (senders that raise).

## Out of scope

- Per-channel OAuth channel-id resolution from `target` names (advisory in v1).
- Email channel for `notify` (dashboard/slack/discord only).
- Any change to the 5 existing handlers.
- Frontend editor/config forms for these types (aspect `seeder-and-ui`).

## Acceptance criteria

- **AC1** — `tag` adds a missing tag to `customer_health_scores.tags`, dedupes, sorts,
  and the change is persisted after the run.
- **AC2** — `tag` over the 20-tag cap returns `ok: False` with reason and leaves the row
  unchanged; >50-char or empty tags are refused the same way.
- **AC3** — `tag` on a customer whose tags are `NULL` initializes the array.
- **AC4** — `notify` with `channel: slack` calls the Slack sender for the org's connected
  integration and reports the channel used; a raising sender maps to `ok: False` (never
  crashes the run).
- **AC5** — `notify` with `channel: discord` calls the Discord sender.
- **AC6** — `notify` with `channel: dashboard` creates `Notification` rows for admins
  (preferences honored) and reports the count.
- **AC7** — `notify` with no connected integration for the channel → `ok: False`, specific
  reason; unknown channel → `ok: False`, loud.
- **AC8** — a failing `tag`/`notify` never prevents sibling actions from running
  (continue-past-failures preserved).
- **AC9** — the full existing playbook-engine suite stays green (no handler behavior
  change).

## Dependencies & sequencing

First slice (no schema migration, no backend change). Independent of
`playbook-tasks` / `trigger-automation`; `seeder-and-ui` depends on nothing from here.

Test precedent: `tests/test_playbook_engine.py` — in-memory SQLite + `StaticPool`, builder
helpers `_make_org/_make_playbook/_make_execution/_make_health/_make_user`, external
senders mocked via `monkeypatch`.

## Risks / open questions

- The worker `CustomerHealth` mirror may not have `tags` yet — adding the column to the
  mirror is required; verify byte-compatibility with the backend column definition
  (JSON nullable) before writing the handler.
- Slack OAuth sends need a `channel_id`; the integration row's `alert_channel_id`/
  `config.channel_id` is the source — confirm which field the automation feedback-trigger
  sender uses and mirror it exactly.