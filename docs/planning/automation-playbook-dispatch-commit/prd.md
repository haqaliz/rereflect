# PRD — Automation playbook dispatch: commit before publish

**Status:** Approved 2026-09-25 (user: "continue until everything is done") · **Branch:** `feat/automation-playbook-dispatch-commit`
**Inputs:** `docs/planning/_card/card.md`, `understanding.md` (this directory). Freeform card — no GitHub issue.

## Problem Statement

Automation rules that carry a `run_playbook` action create a `ChurnPlaybookExecution` row,
`flush()` it for an id, and publish that id to Celery **before committing**. The worker reads on
another connection, sees nothing, returns `{"skipped": True, "reason": "execution not found"}`
(`worker-service/src/services/playbook_engine.py:46-49`), and never retries. The row stays
`queued` forever; the playbook never runs; nothing is surfaced.

Three production sites (details and call paths in `understanding.md`):

1. `backend-api/src/services/automation_engine.py:826-833` — reached via
   `health_score_service` for `health_score_threshold` / `churn_risk_level_change` rules (the API
   allows `run_playbook` on any trigger).
2. `worker-service/src/services/automation_churn_trigger.py:289-293` — every analysis via
   `probability_updater`, and nested via the playbook `trigger_automation` action.
3. `worker-service/src/services/automation_usage_trend_trigger.py:332-336` — nightly usage recompute.

Shipped-but-inert as a result: M4.1.5 (`AI-TRACKING.md:400`), the M3.2c `usage_trend → run_playbook`
path, and the `trigger_automation` playbook action. Manual runs work because
`routes/playbooks.py:529-535` commits first — which is why nobody noticed.

A fourth, lower-severity site of the same class:

4. `worker-service/src/tasks/source_events.py:453-470` — webhook-ingested `FeedbackItem`
   (`auto_import` sources) published to `analyze_single_feedback` before the commit at `:127`.
   Recovered within ~30 s by the `process_unanalyzed_feedback` beat task, so the cost is latency
   plus a wasted task, not loss.

**Evidence:** code shape verified at `6ecae609` by three independent dig agents and direct reads.
A live repro on 2026-08-21 exists only in session notes; this PRD requires a fresh one.

## Goals & Success Metrics

- **G1.** An automation-fired playbook run reaches `completed` (or its engine's normal terminal
  status) against a real Postgres + real Celery worker. Measured by the live acceptance run:
  before the fix → `queued` + worker log `execution not found`; after → terminal status, no
  `not found` log.
- **G2.** Every fixed site is pinned by an ordering test (`commit` precedes the publish call) that
  fails on today's code (RED) and passes after (GREEN).
- **G3.** No regression: the backend, worker scoped suites and the worker full suite stay green.
- **G4.** Tracking is honest: the defect is recorded in `DEV-TRACKING.md`, and the M4.1.5 / M3.2c
  markers point to this fix, in the same branch.

## User Personas & Scenarios

- **Self-hosting CS lead** configures "Critical Save" to auto-run when churn probability crosses
  70 %. Today: the Automations page shows the rule firing (audit row `success`), the customer
  timeline shows nothing, the playbook never ran. After: the playbook runs.
- **Operator chaining playbooks** via `trigger_automation`. Today: the inner run is lost. After: runs.

## Requirements

### Must-have
- **M1.** At sites 1–3, `commit()` the session after adding the `ChurnPlaybookExecution` and
  **before** `send_task` / `.delay`. Mirror the `send_customer_email` precedent
  (`automation_engine.py:959-971`, `automation_email_delivery.py:209-235`), including a
  `COMMIT BEFORE PUBLISH` comment naming why a flush is insufficient.
- **M2.** Ordering tests per site, in the precedent's shape (spy on `db.commit`, record publish
  via `side_effect`, assert `calls.index("commit") < calls.index(publish)`), written RED first.
- **M3.** Existing `run_playbook` behaviour otherwise unchanged: result dict shape, error branches
  (no playbook / wrong org / inactive / no email) still create no row and publish nothing, shadow
  mode still dispatches nothing, cooldown + audit + counters unchanged.
- **M4.** Live acceptance run (scratch Postgres DB, real Celery worker on an isolated Redis DB
  index) demonstrating G1 for the worker churn trigger path at minimum; `dropdb` afterwards.
- **M5.** `DEV-TRACKING.md` entry + `AI-TRACKING.md` M4.1.5 / M3.2c notes + `CHANGELOG.md` entry.

### Should-have
- **S1.** Fix site 4 (`source_events.py`) the same way — commit before `analyze_single_feedback.delay`
  — with its own ordering test. Chosen shape: collect the created feedback ids and publish after
  the existing commit at `:127` (the function already has one commit point after the loop; an
  in-loop commit per source would split the event-log + source-stats writes).

### Nice-to-have
- None.

## Technical Considerations

- **Services:** `backend-api` (one file), `worker-service` (three files). No frontend, no
  analysis-engine, **no migration**, no API change.
- **Why commit-in-action, not deferred dispatch:** deferred dispatch (queue ids, publish after
  `_evaluate_rule`'s commit) keeps execution + audit rows in one transaction but restructures three
  engine copies and the nested `trigger_automation` call path. Commit-in-action matches existing
  code and the only new edge case — an execution that runs while its `AutomationExecution` audit
  row fails to write — is strictly better than today's silent loss.
- **Commit scope is not widened:** callers commit their own work before invoking triggers
  (`probability_updater.py:123`, `usage_metrics.py:646-647`); backend `_evaluate_rule:203` already
  commits the caller's session on every fire. Earlier same-rule action writes get committed a few
  lines sooner; the engine never rolls back, so they were going to commit anyway.
- **Two-copy rule** (`CLAUDE.md`, *Automations engine*): both worker mirrors change together;
  backend changes in the same branch.
- **Tests cannot see visibility:** conftests use one in-memory SQLite session. Ordering tests are
  the unit-level guard; M4 is the only real proof.
- **Multi-tenancy:** unchanged — rows keep `organization_id`; no query changes.

## Risks & Open Questions

- **R1.** Committing inside `_execute_run_playbook` expires ORM instances in the session
  (`expire_on_commit`). Later code in `_evaluate_rule` touches `rule` / `feedback`; they reload
  lazily — fine on Postgres, fine on SQLite `StaticPool`. The precedent handler already commits
  mid-rule without issue. Verify in tests.
- **R2.** Live run needs Redis + Postgres locally and the `LLM_ENCRYPTION_KEY` for a fresh
  migration chain (repo gotcha). If either is unavailable, report M4 as not done — do not claim it.
- **R3.** `source_events` reorder: if `.delay` raises after commit, the item is still recovered by
  the 30 s sweeper — acceptable.

## Out of Scope

- Publish failure after commit (broker down) leaving an execution `queued` — same gap exists in
  the manual route (`playbooks.py:533-536`). Recorded in `DEV-TRACKING.md` as a follow-up
  (stale-`queued` reaper or mark-failed-on-publish-error).
- Adding retry to `run_playbook` for `not found` — masks ordering bugs rather than fixing them.
- Restricting which actions a trigger may carry.
- The six copilot defects and P7 provider duplication.

## Self-critique (prd-generator, 2026-09-25)

| # | Sev | Gap | Resolution |
|---|---|---|---|
| 1 | 🟡 | Nested path: `trigger_automation` runs `_evaluate_rule` *inside* a running playbook execution, so the new in-action commit also commits the outer execution's in-progress state. | Already tolerated — `_evaluate_rule` commits mid-run today and the engine's finalization is pinned by `test_execute_finalizes_done_when_handler_commits_mid_run` (`playbook_engine.py:922-923`, observed). The new commit is one more of the same kind. Plan must run that test. |
| 2 | 🟡 | Live proof (M4) covers the worker churn path only; backend site 1 and usage-trend site 3 get ordering tests but no live run. | Accepted: all three are the identical three-line shape, and the worker churn path is the highest-traffic one. If time allows, also exercise site 1 live via `update_customer_health`. |
| 3 | 🟡 | `expire_on_commit` after the new commit (R1): the result dict reads `exec_row.id` post-commit. | Post-commit attribute access triggers a refresh by PK — safe; ordering tests assert the returned `execution_id` equals the row's id. |
| 4 | 🟢 | Success metrics are binary, not rate-based. | Appropriate for a correctness fix. |

**Hard question:** M4.1.5 and M3.2c were marked COMPLETE for ~2 months while inert. Do we
annotate the markers ("delivery fixed 2026-09-25 by …") rather than silently leaving COMPLETE?
**Decision:** annotate, per `DEV-TRACKING.md` roadmap-hygiene rule ("correct the marker in the same commit").

## Aspects

1. `dispatch-ordering` — sites 1–3 + ordering tests (M1–M3).
2. `source-events-dispatch` — site 4 + ordering test (S1).
3. `live-acceptance-and-tracking` — M4 live run + M5 docs.
