# Understanding — churn-triggered-playbooks (Phase 2 dig synthesis)

Synthesis of three read-only digs (worker, backend, frontend). All paths under the
worktree. This note is input to the requirements interview.

## What the feature really is

When a customer's churn signal crosses a per-org threshold, automatically run a
designated churn playbook — **once per crossing** (idempotent, cooldown) — reusing
the existing SMTP-free playbook execution engine, and surface the run on the
customer timeline.

**The schema already anticipated this.** `ChurnPlaybookExecution.triggered_by`
pre-declares an unused `"auto_probability"` value (`churn_playbook.py:44`,
`PLAYBOOK_TRIGGER_SOURCES = ["manual", "auto_probability", "scheduled"]`). Today
both run paths hard-code `"manual"` (`playbooks.py:525`, `:645`). This feature is the
intended producer of `auto_probability`.

## Confirmed reusable machinery (little is net-new)

- **Playbook execution is fully reusable and SMTP-free.** All four action handlers —
  `assign`, `change_status`, `send_notification` (in-app `Notification` rows only),
  `draft_response` — send no email (`playbook_engine.py:169-376`). Auto-running from a
  headless context needs **no SMTP/Resend**. The engine also has a status-guard
  (`:51`) and a 60-min per-`(playbook,customer)` rate-limit (`:101-118`).
- **Execution seam:** insert `ChurnPlaybookExecution(status="queued", triggered_by=…)`
  then `send_task("tasks.churn_playbooks.run_playbook", [execution_id])`
  (`playbooks.py:221-226` → `churn_playbooks.py:24` → `playbook_engine.execute`).
  Models are already mirrored into the worker (`playbook_engine.py:18-22`), so no
  cross-service import issue.
- **Thresholdable per-customer values** on `CustomerHealth`
  (`customer_health.py`): `churn_probability` (Numeric 5,4), `health_score` (0-100),
  `risk_level` (`healthy|moderate|at_risk|critical`), `time_to_churn_bucket`.
- **Config house-pattern:** single-row-per-org `OrgAIConfig` (`org_ai_config.py`,
  `organization_id` unique) + `PATCH`/`GET` with `require_admin_or_owner` and the
  `if "field" in data.model_fields_set:` partial-update idiom (`ai_settings.py`).
  `threshold_value`+`is_enabled` idiom from `UserAlertPreference`.
- **Timeline is derived-on-read, not written** (`customer_timeline_service.build_timeline`).
  No event table/writer. Add a `_fetch_playbook_runs` fetcher reading
  `churn_playbook_executions` (mirror `_fetch_churn_events`) → emit a
  `playbook_auto_run` `TimelineEvent`. No new table needed.
- **Alembic:** single head `t3u4v5w6x7y8`; migration template
  `u0v1w2x3y4z5_add_advanced_churn_prediction.py`.

## ⚠️ The central architecture fork (decide in the interview)

There are **two seams where a crossing can be detected**, covering different signals:

**Option A — extend the existing AutomationEngine with a `run_playbook` action.**
`health_score_service.update_customer_health()` (backend) already computes the exact
`old→new` transition and **already calls**
`AutomationEngine.evaluate(org, "health_score_threshold" | "churn_risk_level_change", …)`
(`health_score_service.py:529-541`). The engine already has `is_active`,
`cooldown_hours`, a rules list + templates UI (`settings/automations/`), and action
types `auto_assign | change_status | send_notification | draft_response`. The **only**
missing piece is a `run_playbook` action type. Pros: minimal new code; reuses
crossing-edge detection + cooldown + config UI; genuinely event-driven (fires on the
transition, better than "next poll tick"); one coherent automation surface. Cons: the
AutomationEngine health path covers **health_score / risk_level**, but the brief
emphasizes **churn_probability** — `churn_probability` is recomputed in the *worker*
(`probability_updater.update`), which does **not** currently invoke the AutomationEngine.
Covering churn-probability crossings via Option A means adding a new trigger type
(`churn_probability_threshold`) invoked from the worker seam.

**Option B — dedicated worker trigger + per-org rule model.** Detect the crossing in
`worker-service/tasks/analysis.py:463-481` (right after `update_customer_health` +
`update_churn_probability`), capture the pre-update value, check a new
`org_auto_playbook_rule` (threshold + playbook_id + cooldown), insert the execution +
dispatch. Pros: directly targets `churn_probability`; self-contained. Cons: builds a
parallel config surface + trigger machinery that substantially duplicates the
AutomationEngine (which the frontend already exposes for health triggers); more
net-new code and a second "automation" concept for operators to learn.

**Leaning:** Option A (extend AutomationEngine with `run_playbook`) is the DRY,
house-pattern, moat-aligned choice — it fuses churn→health→playbook→automation into
the *existing* automation loop rather than forking it. The open question is purely
**which signal(s) to trigger on** and, if churn_probability is required, whether to add
a `churn_probability_threshold` trigger wired from the worker's `probability_updater`.

## Risks / constraints surfaced by the dig

1. **Idempotency must be enforced at insert time** (before enqueue), via the rule's
   cooldown + a check of the last `auto_*` execution for `(playbook, email)`. The
   engine's 60-min rate-limit is a downstream safety net, not the primary guard
   (wrong layer).
2. **Crossing (edge) vs level:** fire only on an *upward crossing* (was below, now
   above), not every tick while above. Needs the pre-update value (capture at the
   seam, or read `CustomerHealthHistory` / rely on AutomationEngine's transition
   inputs which already carry `old`/`new`).
3. **No SMTP needed** — confirmed; scope holds to SMTP-free actions natively.
4. **Plan gating is STALE (OSS pivot).** Agents flagged `churn_playbooks` as Business+
   and that the worker path bypasses the HTTP `require_feature` gate — but per the
   OSS/self-hosted pivot all features are **unlocked**; do **not** add tier gating.
   (Confirm we simply don't re-gate in the worker.)
5. **Trigger-source label:** `auto_probability` is pre-declared. If we also trigger on
   health_score, decide whether to reuse `auto_probability` generically or add a second
   label (e.g. `auto_health`) to `PLAYBOOK_TRIGGER_SOURCES`.

## Affected areas by service

- **backend-api:** AutomationEngine action executor (+`run_playbook`) OR new worker
  seam; automation/rule model + migration; `customer_timeline_service` (+fetcher +
  `playbook_auto_run` type); config route if Option B.
- **worker-service:** `probability_updater` / `analysis.py` seam if churn_probability
  triggering; execution enqueue reuse (unchanged engine).
- **frontend-web:** a `run_playbook` action option in `settings/automations/` (Option A)
  or a new auto-run config card in `settings/playbooks/` (Option B); timeline renderer
  gains `playbook_auto_run`.

## Open questions for the interview

1. **Signal(s):** trigger on `churn_probability`, `health_score`/`risk_level`, or both?
2. **Architecture:** Option A (extend AutomationEngine — add `run_playbook` action,
   and a `churn_probability_threshold` trigger if churn-prob is in scope) vs Option B
   (dedicated worker trigger + per-org rule)?
3. **Cooldown default + configurability** (hours? per-rule?).
4. **Which playbook runs** — a single designated per-org playbook, or the existing
   probability-band matching (`RunPlaybookDropdown` logic) picks the playbook?
5. **Timeline:** surface auto-runs only, or all playbook runs (manual + auto)?
