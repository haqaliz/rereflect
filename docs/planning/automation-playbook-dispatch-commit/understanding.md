# Understanding — automation-playbook-dispatch-commit

Dig date: 2026-09-25, against `origin/master` @ `6ecae609`. Three read-only agents (backend
engine, worker mirrors, repo-wide sweep) plus direct verification of every cited line.

## What the card is really asking

Automation-fired playbook runs publish a `ChurnPlaybookExecution` id to Celery before the row
is committed. The consumer runs on another connection, cannot see the row, and returns
`{"skipped": True, "reason": "execution not found"}` (`worker-service/src/services/playbook_engine.py:46-49`).
`run_playbook` (`worker-service/src/tasks/churn_playbooks.py:24`) has no `autoretry_for`, no
`self.retry`, and nothing sweeps `queued` executions — so the loss is **permanent**: row stuck
at `queued`, playbook never runs, no error surfaced.

## Affected sites (all live in production)

| # | Site | Reached from |
|---|---|---|
| 1 | `backend-api/src/services/automation_engine.py:826-833` (`_execute_run_playbook`: `flush()` → `send_task`) — commit only at `_evaluate_rule:203` | `health_score_service.update_customer_health:550-565` for `health_score_threshold` / `churn_risk_level_change` rules. The API (`routes/automations.py:62-69, 320-340`) does **not** restrict actions by trigger, so a rule on either trigger may carry `run_playbook`. |
| 2 | `worker-service/src/services/automation_churn_trigger.py:289-293` (`flush()` → `run_playbook.delay`) — commit at `:214` | `probability_updater.py:122-134` (after every analysis), **and** `playbook_engine._handle_trigger_automation` (nested: playbook → rule → playbook) |
| 3 | `worker-service/src/services/automation_usage_trend_trigger.py:332-336` — commit at `:264` | `usage_metrics.recompute_usage_scores:658-671` |

So M4.1.5 (`AI-TRACKING.md:400`), M3.2c `usage_trend → run_playbook`, and the
`trigger_automation` playbook action (`playbook-action-types`) are all marked shipped but
deliver nothing when a real worker wins the race.

## Same-class site found by the sweep (not in the card)

| 4 | `worker-service/src/tasks/source_events.py:453-470` — webhook-ingested `FeedbackItem` (`auto_import` sources): `flush()` → `analyze_single_feedback.delay(feedback.id)`; commit at `:127` after the loop. Consumer returns `not_found` without raising (`analysis.py:161-163`), so its `autoretry_for` never fires. |

**Severity is much lower than 1–3:** the beat task `process_unanalyzed_feedback` runs every
30 s (`celery_app.py:113-117`) and picks up any `sentiment_label IS NULL` item. Impact is
up to ~30 s extra latency + a wasted task, not loss.

## Reference pattern already in the codebase

`send_customer_email` was fixed for exactly this on `feat/automation-send-customer-email`:

- backend `automation_engine.py:959-971` — `db.add(delivery); db.commit(); send_task(...)`,
  with a `COMMIT BEFORE PUBLISH` comment.
- worker `automation_email_delivery.py:209-235` — same.
- Ordering tests: `backend-api/tests/test_automation_engine_send_customer_email.py:445-484` and
  `worker-service/tests/test_automation_email_delivery.py:388-416` — spy on `db.commit`
  and the publish call, append to a `calls` list, assert `calls.index("commit") < calls.index(<publish>)`.
- Manual routes already commit first: `playbooks.py:529-535` (single), `:650-658` (batch).

## Transaction consequences of an in-action commit

- **Caller work:** no new exposure. Backend `_evaluate_rule:203` already commits the caller's
  session on every fire; the `CustomerHealthHistory` row is added after the engine returns
  (`health_score_service.py:614-628`). Worker callers commit their own work before invoking
  the trigger (`probability_updater.py:123`, `usage_metrics.py:646-647`).
- **Same-rule work:** earlier actions' session changes (e.g. `change_status`, `notify` rows)
  are committed a few lines sooner than before. They would have been committed at `:203`
  anyway — the engine never rolls back (`evaluate:128-136` only logs).
- **Partial failure:** if something raises *after* the new commit (audit log, counters), the
  execution row is committed and runs while the `AutomationExecution` audit row is missing.
  Today the same failure leaves an uncommitted — and, in the engine, later still-committed —
  state; the new behaviour is no worse, and a running playbook with a missing audit row beats
  a silently dead one.
- **Shadow mode:** skips all actions (`automation_engine.py:171-173`), so no dispatch, no change.

## Tests today

Unit suites use one in-memory SQLite session (`backend-api/tests/conftest.py`) and mock Celery,
so they **cannot** observe cross-connection visibility — only call order. No existing
`run_playbook` test asserts commit-before-publish:
`backend-api/tests/test_automation_engine_run_playbook.py`,
`worker-service/tests/test_automation_churn_trigger.py`,
`worker-service/tests/test_automation_usage_trend_trigger.py`,
`worker-service/tests/test_usage_trend_trigger_seam.py`.

## Contradictions / honesty notes

- The card says the defect is "proven live 2026-08-21". That proof lives in session memory,
  not in the repo. The code shape is verified today; a fresh live repro is part of acceptance.
- `usage_trend` docstring (`automation_usage_trend_trigger.py:157-161`) "never inside the scan
  loop" is about the *caller's* placement, not a ban on evaluator commits — the evaluator
  already commits per fired rule. Not a contradiction with the fix.

## Out of scope (recorded, not fixed)

- Publish failure after commit (broker down) leaves the row `queued` — true today for the
  manual route too (`playbooks.py:533-536` logs and moves on). Separate concern: a
  stale-`queued` reaper or mark-failed-on-publish-error.
- The backend dispatch has no local try/except (`automation_engine.py:831`); the per-action
  handler catches it. Unchanged.
