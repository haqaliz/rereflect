# PRD — Playbook execution reaper

**Status:** Approved 2026-09-25 (user: "go for the follow ups") · **Branch:** `feat/playbook-execution-reaper`
**Source:** follow-ups recorded in `DEV-TRACKING.md` under `automation-playbook-dispatch-commit` (PR #30).

## Problem
A `ChurnPlaybookExecution` can be stuck at `queued` forever:
1. **Publish fails after commit** (broker down / network blip) — every dispatch site (manual route,
   batch route, backend engine, worker mirrors) logs and moves on; nothing re-publishes.
2. **Pre-fix orphans** — rows orphaned by the flush-then-publish bug before PR #30.
And one sibling: a row stuck at `running` when the worker process dies mid-run
(`task_reject_on_worker_lost` redelivers, but `execute` then sees `running` and skips forever).

Separately, `playbook_engine.execute`'s idempotency guard is read-then-write (`status != "queued"`
check, then `status = "running"` + commit), so two deliveries of one id can both run. Harmless today
(one publish per row) but a re-publisher makes duplicates possible.

## Requirements (must)
- **R1 Atomic claim.** `execute` claims with a conditional `UPDATE … SET status='running',
  started_at=now WHERE id=:id AND status='queued'`; rowcount 0 → `{"skipped": True, ...}`. The
  rate-limit cancel is likewise conditional on `status='queued'`.
- **R2 Reaper task** `src.tasks.churn_playbooks.reap_stale_executions`, beat every 10 min:
  - `queued`, `created_at` older than **15 min** and newer than **24 h** → re-publish
    `run_playbook(id)` (row untouched; R1 makes duplicates safe). Per-id publish errors logged.
  - `queued` older than **24 h** → `failed`, `completed_at=now`, `error_message` = "never picked up
    by a worker (dispatch lost); not re-run automatically because it is over 24h old — run the
    playbook again if it still applies". Re-running a days-old save play would act on stale state.
  - `running`, `started_at` older than **1 h** → `failed`, message "worker stopped mid-run; actions
    may be partially applied — check the action log before re-running". Never re-run (actions are
    not idempotent).
  - Bounded: at most 500 rows per class per run, oldest first. Returns counts.
- **R3** Tests first (RED): atomic claim (second claim skips), each reaper class, boundaries,
  bounded batch, publish failure does not abort the run, beat entry registered.
- **R4** Docs: CHANGELOG (replace the "not re-run automatically" note), DEV-TRACKING follow-ups ticked,
  SELF_HOSTING mention if it documents beat tasks.

## Out of scope
Backend-side changes (the reaper lives in the worker, where `run_playbook` lives); UI for failed
reasons (existing execution list already shows status + error_message); restricting actions per trigger.

## Risks
- A `queued` row legitimately waiting >15 min in a backed-up queue gets a duplicate message → R1 skips it.
- The 1 h `running` cutoff could fail a legitimately slow run — playbook actions are DB writes, Slack/
  email sends and one optional LLM call; none approach 1 h.
- No migration (status is free-text `String(20)`, no check constraint; `failed` already used).

## Build notes + live evidence (2026-09-25)

- Implemented TDD: 15 new tests (3 engine claim, 12 reaper), RED first. Two of the engine tests failed
  on the old read-then-write claim (actions ran over another worker's `running`; rate-limit cancel
  overwrote it). Worker suite 2018 passed.
- Integrator refinement: reaper failed-marking uses conditional `UPDATE … WHERE id IN (…) AND
  status=<selected>`, so a row finished/claimed between select and update is never overwritten.
- **Live** (scratch Postgres, real worker, `--pool=threads`, Redis DB 9), seeded rows:

| Row | Seeded | After reaper + worker |
|---|---|---|
| 101 | queued, 20 min old | re-published → `done` |
| 102 | queued, 30 h old | `failed` "never picked up by a worker…" |
| 103 | running, started 2 h ago | `failed` "worker stopped mid-run…" |
| 104 | queued, 5 min old | untouched (`queued`) |
| 105 | queued, published **twice** | one delivery `done`, the other `{"skipped": true, "reason": "status is already 'running'"}` |

Reaper returned `{'redispatched': 1, 'expired_queued': 1, 'failed_running': 1}`. Scratch DB dropped.
