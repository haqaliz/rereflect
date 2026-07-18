# PRD — Churn-Triggered Playbook Auto-Execution

**Slug:** `churn-triggered-playbooks`
**Branch:** `feat/churn-triggered-playbooks`
**Type:** feat (freeform; no GitHub issue — selected via `rereflect-next`)
**Status:** Draft — pending review gate
**Author:** Rereflect (via `rereflect-begin-fast`)
**Source:** `docs/planning/_card/card.md` + `understanding.md` (3-service dig)

---

## Problem Statement

Rereflect closes most of the churn loop: it computes a calibrated **churn probability**
and a **customer health score** (M4.1), and it ships **churn playbooks** — reusable
action sequences (assign a CS owner, change workflow status, notify the team, draft a
response) that a human runs manually against one customer (`RunPlaybookDropdown`) or a
cohort (`run-batch`). The **last step is still manual**: someone has to notice a
customer got risky and click "run playbook."

That gap is exactly what `PRD-ADVANCED-CHURN-PREDICTION.md:465` deferred:

> "Real-time playbook execution on probability threshold cross. v1 supports manual
> trigger + run-batch only. Auto-execution on threshold cross is M4.1.5."

The schema already anticipated this feature — `ChurnPlaybookExecution.triggered_by`
pre-declares an unused `"auto_probability"` value (`churn_playbook.py:44`), but nothing
writes it today.

**Who has this problem:** self-hosting operators (OSS, single-tenant) running the churn
suite who want at-risk customers actioned the moment the model flags them, without a
human babysitting a dashboard.

**Evidence it's real:** the deferred M4.1.5 line above; the pre-declared enum slot; and
the fact that the automation engine (`AutomationEngine`, M4.4) already fires on
`health_score_threshold` and `churn_risk_level_change` transitions but has **no way to
run a playbook** in response.

**Cost of status quo:** at-risk customers wait on human vigilance; the churn →
health → playbook → automation loop — a core Rereflect moat — is broken at the last
hop.

---

## Goals & Success Metrics

- **G1 — Auto-run on threshold breach.** A configured **active** rule automatically runs
  its designated playbook when a customer's `churn_probability` **or** `health_score`/
  `risk_level` crosses the rule's threshold.
  - *Metric (tested):* given a rule and a customer whose recomputed signal breaches the
    threshold, exactly one `ChurnPlaybookExecution(triggered_by=<auto>, status="queued")`
    is created and `tasks.churn_playbooks.run_playbook` is enqueued — for both the
    backend health seam and the worker churn-probability seam.
- **G2 — Fire once per cooldown, never a storm.** A customer sitting above threshold
  does not re-trigger every recompute; re-firing is gated by the rule's `cooldown_hours`
  (existing engine mechanism) plus the playbook engine's 60-min per-(playbook,customer)
  rate-limit as a backstop.
  - *Metric (tested):* two evaluations within the cooldown window produce exactly one
    execution.
  - **First-observation semantics (intended, not a bug):** the trigger is level-based, so
    the *first* qualifying evaluation after a rule becomes `active` fires — including for a
    customer who was already above threshold. This is per-customer and gated by cooldown;
    it is **not** a bulk backfill sweep (no scan of the existing book), but activating a
    rule *will* action already-at-risk customers on their next recompute. See Risk #7.
- **G3 — Shadow mode builds trust before real actions fire.** A rule in **shadow** state
  records what it *would* have run and executes **nothing**.
  - *Metric (tested):* a shadow rule that breaches threshold creates **zero**
    `ChurnPlaybookExecution` rows and one shadow audit record.
- **G4 — Visible on the customer timeline.** An auto-run surfaces as a
  `playbook_auto_run` timeline event on the customer's profile.
  - *Metric (tested):* after an auto-run, `build_timeline` returns a `playbook_auto_run`
    event for that customer.
- **G5 — No regressions.** Existing automation actions (`auto_assign`, `change_status`,
  `send_notification`, `draft_response`) and manual playbook runs are byte-behaviour
  unchanged; existing `is_active` rules keep working.
  - *Metric (tested):* characterization tests on the engine + manual `/run` and
    `/run-batch` stay green.

**Explicitly not a metric:** churn-model accuracy. This feature acts on the existing
calibrated signal as-is; it does not change how probability/health are computed.

---

## User Personas & Scenarios

- **Operator / CS lead (admin/owner).** Configures a rule in Settings → Automations:
  "When churn probability ≥ 0.70, run the *At-Risk Outreach* playbook (assign to CS
  owner + notify admins)." Starts it in **shadow** for a week, reviews the "would-run"
  log, then flips it to **active**.
- **CS teammate (member).** Sees auto-run entries on a customer's timeline and the
  resulting assigned feedback / in-app notification, and follows up.

---

## Requirements

### Must-have

1. **New trigger type `churn_probability_threshold`** on the AutomationEngine.
   - `trigger_config = {"threshold": <float 0..1>, "direction": "above"}`.
   - Fires when `context["churn_probability"] >= threshold` (level-based, matching the
     existing `health_score_threshold` pattern — the cooldown, not edge-detection,
     prevents re-fire).
   - **Dispatched from the worker** at the churn-probability recompute seam
     (`worker-service/src/services/probability_updater.py:update()` after the commit at
     `:87`): `engine.evaluate(org_id, "churn_probability_threshold",
     {"churn_probability": p, "customer_email": email})`, wrapped in try/except so a
     failure never breaks probability updates (mirrors the existing analysis.py call
     site).
2. **New action type `run_playbook`** on the AutomationEngine.
   - `action_config = {"playbook_id": <int>}`.
   - Resolves the playbook (must be org-owned — or a system template — and `is_active`);
     an invalid/inactive/foreign playbook yields an action error, not a crash.
   - **Active** rule: insert `ChurnPlaybookExecution(playbook_id, organization_id,
     customer_email, triggered_by=<auto label>, triggered_by_user_id=None,
     status="queued")` and enqueue `tasks.churn_playbooks.run_playbook` — reusing the
     existing engine **unchanged**. The enqueue must work from **both** service contexts
     (backend via `celery_client.send_task`, worker via its Celery app).
   - **Shadow** rule: record intent (audit log) and do **not** insert/enqueue.
3. **Rule state: `off | shadow | active`** (replaces the binary `is_active` semantics for
   evaluation).
   - New `AutomationRule.mode` column; migration backfills `active` where `is_active` is
     true, else `off`, so existing shipped rules are unchanged.
   - **`mode` is the single source of truth for evaluation.** `is_active` is retained only
     as a compatibility alias, kept derived as `is_active == (mode != 'off')` (write-through
     both directions in the API/model so old callers that send only `is_active` map to
     `mode`, and vice-versa). The engine never reads `is_active` after this change — no
     state where the two can disagree.
   - Engine `evaluate()` selects rules where `mode IN ('shadow','active')` and, per rule,
     executes actions only when `mode == 'active'`; in `shadow` it logs a shadow audit
     record and skips execution.
   - `mode` applies engine-wide (all action types get shadow) for consistency with the
     AI classifier `off/shadow/auto` precedent.
4. **Timeline surfacing.** Add a `_fetch_playbook_runs` source to
   `customer_timeline_service.build_timeline` reading `ChurnPlaybookExecution` (auto-
   triggered), emitting `playbook_auto_run` `TimelineEvent`s; extend the timeline
   response schema + frontend renderer with the new type.
5. **Frontend config in Settings → Automations.**
   - `run_playbook` selectable as an action, with a picker populated from the org's
     active, non-template playbooks.
   - `churn_probability_threshold` selectable as a trigger, with a numeric threshold
     input (0–1, validated).
   - Rule state control exposing `off / shadow / active` (mirrors classifier mode cards).
6. **No SMTP dependency.** All auto-runnable playbook actions are SMTP-free by
   construction; the feature adds none.

### Should-have

- Health-signal parity: the existing `health_score_threshold` and
  `churn_risk_level_change` triggers gain `run_playbook` for free (they already dispatch
  from `health_score_service`); ship + test at least one health-triggered auto-run.
- Shadow "would-run" entries visible to the operator (in the automation execution log,
  and/or a distinct shadow marker on the timeline).

### Nice-to-have (candidate v2, not this slice)

- Recovery/downward triggers (auto-run a "win-back completed" playbook when a customer
  crosses back below threshold).
- Per-action allow-listing (restrict which action types may auto-run).
- A dedicated "auto-run history" analytics view.

---

## Technical Considerations

**Services touched:** `backend-api` (engine, model, migration, timeline, automations
routes/schemas), `worker-service` (churn-probability dispatch seam; engine reachability —
see risk), `frontend-web` (automations config + timeline renderer).

**Reuse (confirmed by dig):**
- Execution engine is fully reusable and SMTP-free (`playbook_engine.py`); the auto path
  only creates the `ChurnPlaybookExecution` row + enqueues the existing task.
- `AutomationEngine.evaluate()` already provides the trigger/cooldown/log/stats loop and
  a Redis per-(rule,customer) cooldown (`automation_engine.py:89-190, 316-338`).
- Timeline is derived-on-read (no event table); add a fetcher, no new event store.

**Data model / migration (single alembic head `t3u4v5w6x7y8`):**
- `AutomationRule.mode` — `String`, values `off|shadow|active`, `NOT NULL`, backfilled
  from `is_active`. `is_active` retained for back-compat (kept in sync or derived).
- `ChurnPlaybookExecution.triggered_by` — reuse the pre-declared `"auto_probability"`
  for the rule-driven runs (naming decision below); no new column. Add a neutral value
  to `PLAYBOOK_TRIGGER_SOURCES` only if we prefer `"automation"` over overloading
  `auto_probability`.
- No new table required (rules live in `automation_rules`; executions in
  `churn_playbook_executions`).

**API contracts (extend `automations.py`):**
- Accept `trigger_type="churn_probability_threshold"` and `actions[].type="run_playbook"`
  in create/update; validate `threshold ∈ [0,1]` and `playbook_id` ownership.
- Accept/return `mode` on rule create/update/read (default `active` on create for
  back-compat; UI can create in `shadow`).

**Multi-tenancy:** every path is `organization_id`-scoped (rule, playbook, execution,
timeline). The `run_playbook` action must verify the target playbook belongs to the
rule's org (or is a system template) before enqueue.

**OSS / plan gating:** all features are unlocked (MIT self-hosted, BYOK). Do **not** add
tier gating; ignore the stale `require_feature("churn_playbooks")` Business+ framing in
CLAUDE.md. (The manual `/run` route keeps its existing guard; the auto path adds none.)

---

## Risks & Open Questions

1. **Worker engine reachability (must resolve first in tech-plan).** `analysis.py:175`
   imports `from src.services.automation_engine import AutomationEngine`, but
   `worker-service/src/services/` has **no** `automation_engine.py` (only
   `playbook_engine.py`, `probability_updater.py`). Either the import already resolves
   via a shared path/deploy copy, or the existing worker automation call is latent. The
   plan must confirm the mechanism and decide whether the engine (with the new trigger +
   action) must be **mirrored into the worker** the way `playbook_engine.py` is.
2. **Redis-off is a correctness hole, not a footnote (must-decide).** The engine treats
   Redis-unavailable as "no cooldown → always allow" (`automation_engine.py:319-320`).
   With a level-based trigger, that means a persistently-at-risk customer re-fires on
   *every* recompute; the playbook engine's 60-min DB rate-limit caps it at ~24 runs/day —
   still a storm. **Decision required in tech-plan:** (a) declare Redis a hard requirement
   of the self-host baseline (it is already the Celery broker, so this is defensible and
   documentation-only), or (b) add a DB-backed last-fired guard for `run_playbook`
   (e.g. check the newest `auto`-triggered `ChurnPlaybookExecution` for `(playbook,email)`
   against `cooldown_hours` before insert). **Recommend (a)** + an explicit note in
   `SELF_HOSTING.md`; (b) only if a Redis-optional deployment is a real target.
3. **Cross-service enqueue for `run_playbook`.** The action runs inside whichever service
   called `evaluate()` (backend for health, worker for churn-prob). The enqueue helper
   must dispatch `tasks.churn_playbooks.run_playbook` correctly from both.
4. **Back-compat of `mode`.** Adding `mode` changes the engine's rule selection; migration
   must backfill so no existing rule changes behaviour, and the automations API/UI must
   keep working for callers that only send `is_active`.
5. **Trigger-source naming.** Reuse `auto_probability` for all rule-driven runs (simplest;
   already declared) vs add `"automation"` to `PLAYBOOK_TRIGGER_SOURCES` (clearer for
   health-triggered runs). Recommend reuse; low-stakes, decide in plan.
6. **Level vs edge semantics.** Firing is level+cooldown (house pattern), so a persistently
   at-risk customer is re-engaged once per `cooldown_hours` — intended, but must be
   documented so operators don't expect strict one-shot.
7. **Activation stampede (the greenlight question).** Because the trigger is level-based,
   flipping a rule `shadow → active` will fire it for **every** customer currently above
   threshold on their next recompute — potentially dozens of auto-runs at once. This is
   arguably the feature working as intended, but it can read as an incident. **Decision:**
   accept it and set expectations in the UI ("activating will action N customers now"),
   and/or optionally seed each customer's cooldown on activation so only *new* breaches
   fire. Resolve in tech-plan; the shadow "would-run" count gives the operator the N
   preview before they flip it.

---

## Out of Scope

- **Email/outreach-to-customer actions** (needs operator SMTP; the deferred
  segment-actions "trigger outreach campaign", `AI-TRACKING.md:228`). All actions here
  are SMTP-free.
- **Auto-pick playbook by probability band** — a rule names one designated playbook.
- **Recovery/downward triggers**, per-action allow-listing, auto-run analytics view
  (v2 candidates above).
- **Backfill / retroactive runs** on customers already above threshold — the feature only
  acts on evaluations going forward.
- **Changes to churn/health computation, calibration, or a real ML churn model** (M5.3,
  separately data-gated).
- **Plan-tier gating** (OSS: all unlocked).

---

## Proposed Aspect Decomposition (for tech-plan)

1. **engine-trigger-and-action** — `churn_probability_threshold` trigger + `run_playbook`
   action + `mode` handling in `AutomationEngine`; the shared enqueue helper. (backend,
   + worker mirror per risk #1)
2. **model-and-migration** — `AutomationRule.mode` column + backfill migration; trigger-
   source constant.
3. **worker-dispatch-seam** — wire `evaluate("churn_probability_threshold", …)` into
   `probability_updater.update()` (try/except, org-scoped).
4. **automations-api** — validate/accept the new trigger, action, and `mode` in
   `automations.py` routes + schemas.
5. **timeline** — `_fetch_playbook_runs` + `playbook_auto_run` event type (backend
   service + response schema).
6. **frontend-automations-ui** — action/trigger options + threshold input + off/shadow/
   active control in `settings/automations`; timeline renderer for `playbook_auto_run`.
