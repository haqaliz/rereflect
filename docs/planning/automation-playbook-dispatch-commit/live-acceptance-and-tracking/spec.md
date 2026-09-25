# Spec — live-acceptance-and-tracking

**Outcome:** real proof that a rule-fired playbook completes, and honest tracking (PRD M4–M5).

## In scope
- Scratch Postgres DB (`createdb`, full `alembic upgrade head` with `DATABASE_URL` + `LLM_ENCRYPTION_KEY`),
  real Celery worker from the worktree on an isolated Redis DB index; drive
  `evaluate_churn_probability_triggers` against an active `churn_probability_threshold` rule with a
  `run_playbook` action; observe the execution row. Run on master code (expect `queued` + `not found`)
  and on the branch (expect terminal status). `dropdb` after; stop the worker.
- `DEV-TRACKING.md` entry; `AI-TRACKING.md` M4.1.5 + M3.2c annotations; `CHANGELOG.md` Fixed entry.

## Acceptance criteria
1. Recorded evidence (commands + observed statuses) in `live-acceptance-and-tracking/evidence.md`.
2. If Postgres/Redis are unavailable, the evidence file says so and the PR says M4 is unproven.
3. Docs land in the same branch.
