# Live acceptance evidence — 2026-09-25

Real Postgres + real Celery worker. Not a unit test.

## Setup

- Scratch DB `rr_dispatch_scratch`, created with `createdb`, migrated to head (`ad76527a185e`)
  with `DATABASE_URL` + a throwaway `LLM_ENCRYPTION_KEY`. Dropped afterwards.
- Seed: 1 org, 1 active playbook (`tag: live-proof`), 1 active `churn_probability_threshold`
  rule (threshold 0.5, `run_playbook` → that playbook), 40 `customer_health_scores` rows.
- Worker: `celery -A src.celery_app worker --pool=threads --concurrency=4`, broker/backend on
  **Redis DB 9** (`CELERY_BROKER_DB=9 CELERY_BACKEND_DB=9`) so the shared dev broker (DB 0) was
  never touched.
  - `--pool=threads` because the default prefork pool crashes on macOS spawn
    (`ValueError: not enough values to unpack` in `fast_trace_task`) before running any task.
    Threads still use one DB connection each, so cross-connection visibility is real.
- Driver (`scratchpad/drive.py`): imports `src.celery_app` (so `shared_task` binds to the worker
  app, as it does inside a real worker), disables cooldowns by stubbing `_get_redis → None` (so
  shared Redis DB 1 is never written), then calls `evaluate_churn_probability_triggers(1, email,
  0.9, db)` for 40 customers, each in a fresh session (as `probability_updater` does), waits 10 s,
  and reads the tables.
- "master" = `git archive origin/master services/worker-service` into the scratchpad, run with
  the same venv. "branch" = this worktree.
- `LIVE_COMMIT_DELAY_MS=50` wraps `Session.commit` with a 50 ms sleep: it stands in for work that
  happens between publish and commit on master (later actions in the rule, the Redis cooldown
  round-trip, and in the backend engine HTTP notifications or an LLM draft).

## Results

| Code | Pre-commit delay | `churn_playbook_executions` | Worker `execution N not found` | Customers tagged | Audit rows |
|---|---|---|---|---|---|
| master | 0 ms | 40 `done` | 0 | 40 | 40 `success` |
| master | **50 ms** | **40 `queued`** | **40** | **0** | 40 `success` |
| branch | 50 ms | 40 `done` | 0 | 40 | 40 `success` |
| branch | 0 ms | 40 `done` | 0 | 40 | 40 `success` |

## Reading

- **The race is real, and whether you lose it depends on timing.** With nothing between publish
  and commit, on this machine the commit (microseconds) beats the worker's pickup, so the minimal
  master run succeeds. As soon as anything runs between publish and commit, master loses every
  run, and it does so **silently**: the audit log still says `success` for all 40.
- On the branch the row is committed before its id is published, so the result no longer depends
  on timing. 40 of 40 runs complete, with or without the delay.
- The 2026-08-21 session note said "proven live" without the delay. That did not reproduce
  here at 0 ms. Recorded honestly: the unforced window is narrow on a quiet single machine, and
  wider under load, over a network broker, or with later actions in the rule.
- Only the worker churn path was run live. The backend engine and usage-trend sites have the
  same shape and are covered by ordering tests (RED on master, GREEN on the branch).
