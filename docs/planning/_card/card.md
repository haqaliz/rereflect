# Card — chore/worker-cleanup-smalls (freeform, no GitHub issue)

Source: DEV-TRACKING P6 — Dead anomaly-alert functions (cleanup, NOT STARTED)
(:211-219). Branch `chore/worker-cleanup-smalls`, worktree
`.claude/worktrees/worker-cleanup-smalls`.

## Item — P6: dead anomaly-alert functions (wire or delete)

`services/worker-service/src/tasks/anomaly.py`:
- `_send_anomaly_slack` is fully implemented and **never called** — anomaly alerts
  route via `_dispatch_anomaly_alerts` → `dispatch_alert` (anomaly.py:169 → :185).
- Its new Discord twin `_send_anomaly_discord` mirrors it — two tested, orphaned
  functions.
- Discord anomaly alerts **do** work through the main pipe — this is dead code, not
  a delivery gap.
- Decide: wire them up, or delete both. Deleting only the Discord one would leave
  the next person wiring up the Slack one with no Discord equivalent — delete BOTH
  or wire BOTH.

## Caveats (carried into the PRD)

- The dig must confirm the dispatch path (the main pipe) truly covers Slack +
  Discord anomaly delivery, and that the orphaned functions are only referenced by
  their own tests (the "green tests over dead code" family — the sweep guard
  approach applies).
- Deleting both is the likely answer (the pipe works; wiring the orphans would
  create a second delivery path and double-send).

## Deliverables (proposed, refine in PRD)

1. Delete both orphaned senders (or wire them — dig decides) + their tests;
   sweep proof (grep).
2. DEV-TRACKING P6 → FIXED (or the wire-up summary).

## Out of scope (guardrails)

- No changes to the working anomaly delivery pipe.
- P7 (provider duplication) stays deferred.
