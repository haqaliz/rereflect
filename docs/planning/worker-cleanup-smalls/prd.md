# PRD — Worker cleanup: dead anomaly-alert functions (P6)

**Slug:** `worker-cleanup-smalls` · **Branch:** `chore/worker-cleanup-smalls`
**Type:** chore · **Created:** 2026-08-18
**Card:** `docs/planning/_card/card.md`

---

## Problem (DEV-TRACKING P6, :211-219)

`_send_anomaly_slack` (anomaly.py:238-310) and `_send_anomaly_discord`
(anomaly.py:313-363) are fully implemented and **never called** — anomaly alerts
route via `_dispatch_anomaly_alerts` (anomaly.py:198-220) → `dispatch_alert`, which
delivers **both** Slack (`_dispatch_slack_alert`, notification_dispatch.py:675-763)
and Discord (`_dispatch_discord_alert`, :766-829) with per-user preferences + health
bookkeeping. The orphans are the "green tests over dead code" family.

**The dig found a third orphan:** `_send_anomaly_email` (anomaly.py:223-235) — its
callee `src.email.send_anomaly_alert_email` (email.py:160) is imported only by this
dead wrapper; the entire anomaly-email production path is unreachable. Deleting
Slack+Discord while keeping email would be internally inconsistent — **all three go**.

**Wire-up verdict (locked): delete.** Wiring the orphans would double-send (the main
pipe already covers both channels) and bypass user preferences; replacing
`dispatch_alert` with them would lose prefs + bookkeeping. Delete is the only sound
option.

## Fix (locked)

1. **Delete** from `anomaly.py`: `_send_anomaly_slack` (:238-310),
   `_send_anomaly_discord` (:313-363), `_send_anomaly_email` (:223-235), the
   now-unused `send_discord_message_webhook` import (:16), and the `_decrypt` helper
   (:27-33 — used only by the orphans; `notification_dispatch.py` has its own).
2. **Delete** `src.email.send_anomaly_alert_email` (email.py:160 — dead callee).
3. **Delete** `test_discord_anomaly.py` (7 tests pinning the orphans) +
   `test_anomaly_email.py` (tests the deleted sender directly); trim the docstring
   coverage list at `test_discord_alerts.py:7`.
4. **Keep untouched:** `_dispatch_anomaly_alerts`, `dispatch_alert`, the main pipe,
   and `test_anomaly_integration.py::TestDispatchAnomalyAlerts` (:345-409 pins the
   live delegation — stays green).
5. **Sweep proof:** grep `_send_anomaly_slack|_send_anomaly_discord|_send_anomaly_email|send_anomaly_alert_email`
   → zero hits in `services/` (planning docs + the P6 FIXED note are the only
   remaining mentions).
6. **Docs:** DEV-TRACKING P6 (:211-219) → **FIXED** with the shipped summary +
   merge-facts placeholder; the `docs/planning/discord-notifications/` docs
   referencing the orphans get pointer/note edits (no history rewriting); the
   oauth-tokens-encryption docs' decrypt-site references die with the orphan (note,
   not rewrite).
7. **CHANGELOG:** a cleanup entry (dead anomaly senders deleted; anomaly delivery is
   unchanged via the main pipe).

## Out of scope (guardrails)

- No changes to the working anomaly delivery pipe (dispatch_alert + both channel
  senders).
- P7 (provider duplication) stays deferred.
- No plan gates; no migration.

## Honest limits

- Anomaly email delivery is **gone entirely** — it was unreachable before this
  change; the main pipe never delivered anomaly email (only Slack/Discord). State
  this in the CHANGELOG rather than implying a regression.
