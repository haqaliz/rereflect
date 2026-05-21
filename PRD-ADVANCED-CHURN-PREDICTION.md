# PRD: Advanced Churn Prediction (M4.1)

**Product**: Rereflect
**Author**: Rereflect Team
**Date**: 2026-05-20
**Timeline**: 6–7 weeks
**Status**: Draft — pending review
**Tracking**: AI-TRACKING.md → Q4 2026 → M4.1

---

## 1. Overview

Turn Rereflect's existing 9-factor heuristic churn score into a **calibrated 30-day churn probability** with a confidence interval, time-to-churn timeline, cohort analytics, and reusable prevention playbooks. This is the "killer feature" called out in AI-TRACKING.md — *"churn prediction that actually works (predict 30-60 days before churn with actionable reasons)"* — and the only roadmap item with no parity from Productboard, Canny, UserVoice, or Thematic.

### Strategic context
- Stage gate: **calibrated heuristic now, real ML later.** We don't yet have churn labels for end-customers (no CRM integration, no subscription mapping). Promising a "probability" without labels would be selling a confidence number with no ground truth. M4.1 ships a calibrated probability (isotonic regression on the existing 9-factor heuristic, fit against collected labels), starts collecting real labels via a new "Mark as churned" UI + CSV import, and re-fits weekly. Once label volume justifies it (≥500 labels per org or ≥5,000 globally), v2 swaps in a trained ML model with no API contract change.
- Honest framing in the UI: every probability shows a confidence interval; the accuracy card surfaces the basis (label count, precision/recall) so users see the math.

### Current state
- 9-factor algorithmic churn risk score (0–100) per feedback item — `services/worker-service/src/tasks/analysis.py:526-793`
- 4-component weighted customer health score (churn 35 / sentiment 25 / resolution 25 / frequency 15)
- Confidence score (volume + recency + diversity)
- One-shot backtest script + admin endpoint — `scripts/backtest_churn.py`, `routes/admin_backtest.py`
- 3-tier weekly LLM analysis (churn_risk / retention / growth_opportunity), Mondays 7AM UTC
- Customer 360 list + profile, factor breakdown, action checklist, history timeline
- AI corrections capturing thumbs up/down + category/sentiment overrides
- `health_score_threshold` automation trigger (closest existing thing to a playbook)

### What's missing
- No calibrated probability — only a 0–100 severity score
- No labeled churn outcomes (no `customer_churn_events` table, no manual labeling UI, no CRM signal)
- No time-to-churn estimate
- No cohort/segment view of churn
- No reusable playbook concept (only one-off automation rules)
- No continuous accuracy tracking — backtest is one-shot, results are not persisted

### Success criteria
- Every customer with `customer_email` has a 30-day churn probability + 90% confidence interval
- A `time_to_churn_bucket` (immediate / 2w / 2-4w / 1-3m / low) is derived from probability × sentiment trend
- Probability replaces `risk_level` as the primary visual signal across feedback list, Customer 360, dashboard widgets
- Users can mark a customer as churned with a structured reason and optional winback tracking
- CSV import seeds historical labels
- Calibration model refits weekly (Mondays 07:45 UTC) and stores precision/recall/F1/AUC per run
- New surfaces ship: `/analytics/churn-cohorts`, `/settings/playbooks`, `/system/churn-accuracy`, `ModelAccuracyCard` on dashboard
- 5–7 pre-built playbooks seeded; each binds to a probability range and a sequence of automation actions
- Plan gating: probability + timeline + cohort + playbooks + accuracy on **Business+**; existing risk_level + factor breakdown stays on **Pro+**
- ~60 backend + ~40 frontend tests added; zero regressions on existing test suite

---

## 2. Decisions Locked

| Topic | Decision |
|---|---|
| Labels strategy | Calibrated heuristic + label collection. Ship now; retrain as real ML in v2 when labels justify it. |
| Labeling UI | Rich — boolean + `churned_at` + structured reason code + free-text + `recovered_at` |
| Model approach | **Isotonic regression** mapping heuristic score → probability. Bootstrap for 90% CI. Re-fit weekly. |
| v1 scope | Full M4.1: probability, labeling UI, timeline buckets, accuracy dashboard, cohort analytics, playbooks |
| Probability display | **Replace** `risk_level` badge with probability % everywhere. risk_level derived from probability bands as secondary color hint. |
| Cohort dimensions | Source channel, acquisition month (first_feedback_at), volume segment (light/regular/power). No custom-builder in v1. |
| Playbooks | Pre-built templates (5–7) + clone/edit. Each binds to a probability range and an action sequence. Builds on existing Automations engine. |
| Plan gating | Probability / timeline / cohorts / playbooks / accuracy = **Business+**. Existing risk_level + factor breakdown stays **Pro+**. Enterprise = unlimited playbooks + custom probability bands. |
| Accuracy dashboard | Both — system admin sees full metrics + per-org observability; orgs see their own accuracy card (Business+). |
| Winback behavior | Auto-flag as potential winback when churned customer sends new feedback; require manual confirmation to clear status. |
| CSV import | Yes — v1 includes CSV import for historical labels (email, churned_at, reason). |
| Backtest cadence | Weekly — Mondays 07:45 UTC, after the 07:00/07:15/07:30 LLM analysis tasks. |

---

## 3. Data Model

### 3.1 New tables

> **PK convention note**: PRD originally specified UUID PKs, but the Rereflect codebase uses `BigInteger`/`Integer` auto-increment PKs uniformly. New tables follow the existing convention. Updated by Phase 1 agents and locked.

#### `customer_churn_events`
Manual + imported + auto-suggested churn labels. Drives the calibration training set.

```sql
id                   BIGINT PRIMARY KEY  -- per existing codebase convention
organization_id      UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE
customer_email       VARCHAR(255) NOT NULL  -- normalized lowercase
churned_at           TIMESTAMP NOT NULL
reason_code          VARCHAR(40) NOT NULL  -- enum: price | competitor | product_quality | no_longer_needed | silent_churn | other
reason_text          TEXT NULL
recovered_at         TIMESTAMP NULL
marked_by_user_id    UUID NULL REFERENCES users(id) ON DELETE SET NULL  -- NULL for csv_import + auto_suggested
source               VARCHAR(20) NOT NULL  -- enum: manual | csv_import | auto_suggested
created_at           TIMESTAMP NOT NULL DEFAULT NOW()
updated_at           TIMESTAMP NOT NULL DEFAULT NOW()

UNIQUE (organization_id, customer_email, churned_at)
INDEX (organization_id, churned_at DESC)
INDEX (organization_id, customer_email)
```

Notes:
- `recovered_at` set when CS user confirms a potential winback.
- A customer can have multiple churn events over time (churn → win back → churn again is legal).
- Active churn = latest event has `recovered_at IS NULL`.

#### `churn_calibration_models`
Versioned isotonic models. One global model + one per org with sufficient labels.

```sql
id                   BIGINT PRIMARY KEY  -- per existing codebase convention
organization_id      UUID NULL REFERENCES organizations(id) ON DELETE CASCADE  -- NULL = global fallback
model_json           JSONB NOT NULL  -- isotonic regression parameters
label_count          INTEGER NOT NULL
positive_count       INTEGER NOT NULL  -- # of churn=true labels
precision            NUMERIC(5,4) NULL
recall               NUMERIC(5,4) NULL
f1                   NUMERIC(5,4) NULL
auc                  NUMERIC(5,4) NULL
threshold_bands      JSONB NOT NULL  -- {"low":0.30,"medium":0.50,"high":0.70,"critical":0.85}
fit_at               TIMESTAMP NOT NULL DEFAULT NOW()
is_active            BOOLEAN NOT NULL DEFAULT FALSE  -- only one active per (org_id|NULL)

INDEX (organization_id, fit_at DESC)
INDEX (is_active) WHERE is_active = TRUE
```

#### `churn_backtest_runs`
Weekly observability — keeps history of every refit and what came out.

```sql
id                       UUID PRIMARY KEY
organization_id          UUID NULL REFERENCES organizations(id) ON DELETE CASCADE  -- NULL = global
calibration_model_id     UUID REFERENCES churn_calibration_models(id) ON DELETE CASCADE
run_at                   TIMESTAMP NOT NULL DEFAULT NOW()
label_count              INTEGER NOT NULL
precision                NUMERIC(5,4) NULL
recall                   NUMERIC(5,4) NULL
f1                       NUMERIC(5,4) NULL
auc                      NUMERIC(5,4) NULL
optimal_threshold        NUMERIC(5,4) NULL
duration_ms              INTEGER NULL
notes                    TEXT NULL  -- e.g., "insufficient labels, fell back to global"

INDEX (organization_id, run_at DESC)
```

#### `churn_playbooks`
Reusable prevention plans.

```sql
id                       UUID PRIMARY KEY
organization_id          UUID NULL REFERENCES organizations(id) ON DELETE CASCADE  -- NULL = system template
name                     VARCHAR(120) NOT NULL
description              TEXT NULL
probability_min          NUMERIC(3,2) NOT NULL  -- 0.0–1.0
probability_max          NUMERIC(3,2) NOT NULL
action_sequence          JSONB NOT NULL  -- list of action objects (reuses Automations action schema)
is_template              BOOLEAN NOT NULL DEFAULT FALSE
is_active                BOOLEAN NOT NULL DEFAULT TRUE
source_template_id       UUID NULL REFERENCES churn_playbooks(id) ON DELETE SET NULL
created_at               TIMESTAMP NOT NULL DEFAULT NOW()
updated_at               TIMESTAMP NOT NULL DEFAULT NOW()

INDEX (organization_id, is_active)
CHECK (probability_min < probability_max)
```

#### `churn_playbook_executions`
Audit log + status for running playbooks.

```sql
id                       UUID PRIMARY KEY
playbook_id              UUID NOT NULL REFERENCES churn_playbooks(id) ON DELETE CASCADE
organization_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE
customer_email           VARCHAR(255) NOT NULL
triggered_by             VARCHAR(40) NOT NULL  -- manual | auto_probability | scheduled
triggered_by_user_id     UUID NULL REFERENCES users(id) ON DELETE SET NULL
status                   VARCHAR(20) NOT NULL  -- queued | running | done | failed | cancelled
action_log               JSONB NOT NULL DEFAULT '[]'::jsonb  -- per-action result
error_message            TEXT NULL
started_at               TIMESTAMP NULL
completed_at             TIMESTAMP NULL
created_at               TIMESTAMP NOT NULL DEFAULT NOW()

INDEX (organization_id, created_at DESC)
INDEX (playbook_id, created_at DESC)
INDEX (customer_email, created_at DESC)
```

90-day retention via Celery Beat purge task (same pattern as automation execution log).

### 3.2 Columns added to `customer_health_scores`

```sql
churn_probability            NUMERIC(5,4) NULL  -- 0.0000–1.0000
churn_probability_low        NUMERIC(5,4) NULL  -- 90% CI lower bound
churn_probability_high       NUMERIC(5,4) NULL  -- 90% CI upper bound
time_to_churn_bucket         VARCHAR(20) NULL   -- immediate | 2w | 2-4w | 1-3m | low
calibration_model_id         UUID NULL REFERENCES churn_calibration_models(id) ON DELETE SET NULL
probability_computed_at      TIMESTAMP NULL
has_potential_winback        BOOLEAN NOT NULL DEFAULT FALSE  -- set when churned customer sends new feedback
```

Existing `risk_level` is kept and **derived from probability bands** going forward: `low<0.30 ≤ medium <0.50 ≤ high <0.70 ≤ critical`. Bands come from the active calibration model (overridable on Enterprise plan).

### 3.3 Alembic migration
Single migration `add_advanced_churn_prediction.py` that:
- Creates the 5 new tables
- Adds the 7 columns to `customer_health_scores`
- Backfills `customer_health_scores.churn_probability` for existing rows using the global isotonic model (seeded with sensible defaults: identity mapping if no labels yet)

---

## 4. Backend Architecture

### 4.1 `ChurnCalibrator` service
New module `services/backend-api/src/services/churn_calibrator.py` (mirrored by a thin client in `services/worker-service/src/services/`).

Public API:
```python
class ChurnCalibrator:
    def fit(self, scores: list[int], labels: list[bool]) -> CalibrationModel: ...
    def predict(self, score: int, model: CalibrationModel) -> float: ...
    def predict_with_interval(
        self, score: int, model: CalibrationModel, n_bootstrap: int = 200
    ) -> tuple[float, float, float]: ...  # (p, low, high) — 90% CI
    def derive_risk_level(self, p: float, bands: dict) -> str: ...
    def derive_timeline_bucket(self, p: float, sentiment_trend: float) -> str: ...
    def backtest(self, scores: list[int], labels: list[bool], model: CalibrationModel) -> Metrics: ...
```

Implementation notes:
- Uses `sklearn.isotonic.IsotonicRegression` (already a transitive dep via scikit-learn used in `analysis-engine`).
- Bootstrap: resample with replacement n_bootstrap times, fit each, return 5th/95th percentile probabilities.
- Timeline buckets:
  - `immediate`: p ≥ 0.85 OR (p ≥ 0.70 AND sentiment_trend ≤ -0.4)
  - `2w`: 0.70 ≤ p < 0.85
  - `2-4w`: 0.50 ≤ p < 0.70
  - `1-3m`: 0.30 ≤ p < 0.50
  - `low`: p < 0.30
- All math is plain numpy — no Celery dependency, no I/O. Pure function.
- Calibration model JSON is small (~50 KB max) — stored inline, no S3.

### 4.2 Recomputation triggers
- **On feedback ingest** (existing path in `analysis.py:388`): after `update_customer_health(...)`, look up active calibration model for org (fall back to global), call `predict_with_interval(churn_risk_component, model)`, persist `churn_probability/low/high`, `time_to_churn_bucket`, `calibration_model_id`, `probability_computed_at`.
- **On churn event written**: recompute the customer's probability immediately (their label just changed the training set, but their own row isn't refit until weekly — this just refreshes the displayed `risk_level` if bands changed).
- **On calibration refit (weekly)**: refresh probability on every CustomerHealth row in the org (parallelized Celery task, idempotent).

### 4.3 Celery Beat additions

Append to `services/worker-service/src/celery_app.py`:
```python
"refit-churn-calibration": {
    "task": "tasks.churn_calibration.refit_all_orgs",
    "schedule": crontab(hour=7, minute=45, day_of_week=1),  # Mondays 07:45 UTC
},
"purge-playbook-executions": {
    "task": "tasks.churn_playbooks.purge_old_executions",
    "schedule": crontab(hour=3, minute=0, day_of_week=0),   # Sundays 03:00 UTC
},
```

Tasks:
- `refit_all_orgs`: loop orgs, dispatch `refit_org_calibration(org_id)` per org with ≥ 20 labels. Orgs below threshold use global model. Store new model + backtest_run row. Alert system admin via existing `system_admin_alert` channel if F1 drops > 10 pts vs previous active model.
- `refit_global_calibration`: pool all orgs' labels into one global model. Stored as `organization_id=NULL`. Default for low-label orgs.
- `purge_old_executions`: delete `churn_playbook_executions` rows older than 90 days.

### 4.4 API endpoints

New module `services/backend-api/src/api/routes/churn_events.py`:
- `POST /api/v1/customers/{email}/churn-event` — body: `{churned_at?, reason_code, reason_text?}`. Returns the created event. Triggers immediate probability recompute.
- `POST /api/v1/customers/{email}/recover` — body: `{recovered_at?, note?}`. Sets `recovered_at` on active event. Re-enables probability tracking for the customer.
- `DELETE /api/v1/customers/{email}/churn-event/{id}` — undo (system admin or original author within 24h).
- `POST /api/v1/customers/churn-events/bulk` — body: `{emails: [...], churned_at, reason_code}`. Bulk mark from customers list.
- `POST /api/v1/customers/churn-events/import` — multipart CSV upload. Columns: `email, churned_at, reason_code, reason_text` (last two optional). Validates emails, dedupes against existing events. Returns import summary.
- `GET /api/v1/customers/churn-events` — list with pagination + filter by `recovered_at IS NULL / reason_code / date range`.

New module `services/backend-api/src/api/routes/churn_analytics.py`:
- `GET /api/v1/analytics/churn-cohorts?dimension=source|month|volume&range=30d|90d|all`
  - Response includes per-cohort: churn_count, total_count, churn_rate, avg_probability, top_reason_codes.
  - Heatmap-friendly: returns 2D grid for `dimension × time_bucket`.
- `GET /api/v1/analytics/churn-accuracy` — org-level: latest precision/recall/F1/AUC + 4-week trend + label_count.
- `GET /api/v1/system/churn-accuracy` — system admin only. Cross-org table with per-org metrics, label volume, last refit timestamp, model version history.

New module `services/backend-api/src/api/routes/playbooks.py`:
- `GET /api/v1/playbooks` — list active org playbooks + system templates.
- `POST /api/v1/playbooks` — create from scratch or clone template. Body: `{name, description, probability_min, probability_max, action_sequence, source_template_id?}`.
- `GET /api/v1/playbooks/{id}` — detail + recent executions.
- `PUT /api/v1/playbooks/{id}` — update (org playbooks only; templates immutable).
- `DELETE /api/v1/playbooks/{id}` — delete (org playbooks only).
- `POST /api/v1/playbooks/{id}/run` — run on one customer. Body: `{customer_email}`. Returns execution_id.
- `POST /api/v1/playbooks/{id}/run-batch` — run on customers matching probability range. Returns list of execution_ids.
- `GET /api/v1/playbooks/executions?playbook_id?&customer_email?&status?` — execution history.

All churn-related endpoints gated via existing `require_feature("advanced_churn_prediction")` (Business+). Cohorts gated via `require_feature("churn_cohorts")`. Playbooks gated via `require_feature("churn_playbooks")` + plan limit check (Business=20 / Enterprise=unlimited).

### 4.5 Pre-seeded playbook templates

Seeder in `services/backend-api/src/services/playbook_seeder.py`, idempotent, runs at startup (same pattern as `response_template_seeder.py`).

| Name | Probability range | Action sequence |
|---|---|---|
| **Critical Save** | 0.85–1.00 | (1) Assign to CS lead role, (2) Send Slack alert to #cs-leads, (3) Create urgent notification, (4) Draft AI response with `critical_save` tone |
| **Churn Prevention** | 0.70–0.85 | (1) Assign to assigned CS owner or round-robin, (2) Draft AI response with empathetic tone, (3) Schedule check-in task |
| **At-Risk Outreach** | 0.50–0.70 | (1) Send email digest entry, (2) Tag customer `at-risk`, (3) Send notification to assignee |
| **Light-Touch Nudge** | 0.30–0.50 | (1) Tag customer `monitor`, (2) Add to weekly review queue |
| **Power-User Recovery** | 0.50–1.00 (with `volume_segment=power`) | (1) Escalate to founder/exec channel, (2) Draft personalized AI response, (3) Create high-priority task |
| **New-Customer Save** | 0.40+ (with `acquisition_month <= 1 month ago`) | (1) Trigger onboarding playbook, (2) Assign to CS, (3) Draft welcome+save response |
| **Silent-Churn Watch** | n/a (manual trigger only) | (1) Send re-engagement email via response template, (2) Flag for follow-up in 14 days |

Templates are read-only (`is_template=true`, `organization_id=NULL`). Users clone to edit.

### 4.6 Winback flow
- When new feedback arrives for a customer with an active churn event (`recovered_at IS NULL`):
  - Set `customer_health_scores.has_potential_winback = TRUE` (new boolean column)
  - Insert in-app notification of type `winback_suggested`
  - Do NOT auto-clear churn event
- Customer profile shows `PotentialWinbackBanner` with "Confirm recovery" CTA → calls `/recover`
- If user dismisses banner without confirming, banner re-shows on next feedback (no permanent dismiss).

---

## 5. Frontend Architecture

### 5.1 New / changed pages

| Path | Status | Purpose |
|---|---|---|
| `/customers` | Modified | `risk_level` badge replaced with `ChurnProbabilityBadge` (% + CI tooltip). New filter: probability range slider. New column: `time_to_churn_bucket`. New bulk action: "Mark as churned". |
| `/customers/[email]` | Modified | Header: probability % + CI + timeline bucket as primary stat. `PotentialWinbackBanner` (when applicable). New "Mark as churned" button → opens `MarkAsChurnedDialog`. New "Run Playbook" dropdown. `ModelAccuracyCard` (Business+). |
| `/churn-risks` | Modified | Sort/filter by probability instead of `churn_risk_score`. Cohort filter (source/month/volume). |
| `/feedbacks` | Modified | `churn_risk_score` column shows the per-feedback score + a customer-level probability chip (small, near `customer_email`). |
| `/feedbacks/[id]` | Modified | Churn card shows feedback-level intensity (existing) + customer-level probability + CI + timeline + "View customer" link. |
| `/analytics/churn-cohorts` | **New** | 3 cohort dimensions (source / acquisition month / volume segment). Heatmap (cohort × time) + bar chart (churn rate by cohort) + reason-code donut. Date range selector. Business+ gate. |
| `/settings/playbooks` | **New** | Template card grid → clone modal → playbook list. Detail page: probability range slider, action sequence builder (reuses Automations action UI), recent executions table. Business+ gate. |
| `/system/churn-accuracy` | **New** | System admin only. Cross-org table (org / latest F1 / label count / last refit). Per-org drill-in: model history line chart (F1/precision/recall/AUC over time), threshold tuner, label distribution chart. |
| `/system/churn-events` | **New** | System admin: all churn events across orgs. Search/filter/export. |

### 5.2 New components

| Component | Location | Notes |
|---|---|---|
| `ChurnProbabilityBadge` | `components/customers/` | % + risk_level color hint + tooltip with CI + label count. Replaces RiskBadge in most places. |
| `MarkAsChurnedDialog` | `components/customers/` | shadcn Dialog. Fields: churned_at (date picker, default today), reason_code (Select), reason_text (Textarea), optional. |
| `RecoverCustomerDialog` | `components/customers/` | Confirm recovery. Fields: recovered_at, note. |
| `BulkMarkChurnedDialog` | `components/customers/` | Triggered from customers list bulk action. Single reason_code applied to selection. |
| `PotentialWinbackBanner` | `components/customers/` | Yellow banner on customer profile. "Confirm recovery" / "Dismiss for now" buttons. |
| `ChurnTimelineBadge` | `components/customers/` | "Likely in 2-4 weeks" pill with icon. |
| `CohortHeatmap` | `components/analytics/` | Recharts-based grid. Tooltip on hover shows cohort details + drill-in. |
| `ReasonCodeBreakdown` | `components/customers/` | Donut chart of reason_code distribution. Reused on cohort page + customer profile. |
| `ModelAccuracyCard` | `components/dashboard/` | Compact card: "73% precision · 81% recall · 142 labeled". Linked to org-level accuracy view. Business+ only. |
| `PlaybookTemplateCard` | `components/playbooks/` | Template grid card with description, probability range, action count, "Use template" button. |
| `PlaybookEditor` | `components/playbooks/` | Range slider for probability + action sequence builder (reuse Automations action components). |
| `RunPlaybookDropdown` | `components/customers/` | Lists playbooks matching customer's probability. Single click → POST `/playbooks/{id}/run`. |
| `ChurnCsvImportDialog` | `components/customers/` | Upload CSV, preview rows, validate, confirm import. Shows success/failure counts. |

### 5.3 API client modules
- `lib/api/churn-events.ts` — CRUD + bulk + import
- `lib/api/churn-analytics.ts` — cohorts + accuracy
- `lib/api/playbooks.ts` — CRUD + run + executions

### 5.4 Sidebar additions
- Under **Analytics**: "Churn Cohorts" (new) — Business+ gated.
- Under **Settings**: "Playbooks" (new) — Business+ gated.
- Under **System** (system admin only): "Churn Accuracy", "Churn Events".

---

## 6. Plan Gating

| Feature ID | Free | Pro | Business | Enterprise |
|---|:---:|:---:|:---:|:---:|
| `customer_health_scores` (existing) | – | ✓ | ✓ | ✓ |
| `enhanced_churn_prediction` (existing — 9-factor score, factor breakdown) | – | ✓ | ✓ | ✓ |
| `churn_llm_insights` (existing — weekly LLM analysis) | – | ✓ | ✓ | ✓ |
| **`advanced_churn_prediction`** (probability % + CI + timeline) | – | – | ✓ | ✓ |
| **`churn_cohorts`** (cohort analytics page) | – | – | ✓ | ✓ |
| **`churn_playbooks`** (templates + execution) | – | – | ✓ (limit 20) | ✓ (unlimited) |
| **`churn_accuracy_card`** (org-level model accuracy) | – | – | ✓ | ✓ |
| **`custom_probability_bands`** (override default thresholds) | – | – | – | ✓ |
| **`churn_event_csv_import`** (historical labels) | – | – | ✓ | ✓ |

Pro users see existing risk_level + factor breakdown + LLM analysis (unchanged). When they view a customer with an active probability, they see a Business+ upgrade CTA instead of the probability badge.

Free users see customers list blurred (existing behavior unchanged).

---

## 7. Phased Delivery (6–7 weeks)

### Phase 1 (Week 1): Foundation — labels + calibrator
- Alembic migration: new tables + new columns on `customer_health_scores`
- Models + Pydantic schemas
- `ChurnCalibrator` service (fit / predict / bootstrap CI / backtest)
- Seeded global calibration model (identity mapping until first refit)
- Unit tests: calibrator math, isotonic monotonicity, bootstrap CI sanity

### Phase 2 (Week 2): Labeling UI + CSV import
- API: `POST /churn-event`, `POST /recover`, `DELETE /churn-event/{id}`, `POST /bulk`, `POST /import`, `GET /churn-events`
- Frontend: `MarkAsChurnedDialog`, `RecoverCustomerDialog`, `BulkMarkChurnedDialog`, `ChurnCsvImportDialog`
- Customer profile + customers list integrations (button + bulk action)
- `/system/churn-events` admin page
- CSV import validation + de-dup logic
- Tests: backend churn event CRUD, CSV import edge cases, frontend dialog flows

### Phase 3 (Week 3): Probability integration + winback
- Recompute probability on feedback ingest (worker-service)
- Add `has_potential_winback` column + auto-flag on churned-customer feedback
- `PotentialWinbackBanner` + recovery confirmation flow
- `ChurnProbabilityBadge` + `ChurnTimelineBadge` components
- Replace `RiskBadge` in customer list, profile, feedback list/detail, dashboard widgets
- Notification type `winback_suggested`
- Tests: probability persistence, winback state machine, badge rendering

### Phase 4 (Week 4): Cohort analytics
- API: `GET /analytics/churn-cohorts` for 3 dimensions
- Frontend: `/analytics/churn-cohorts` page with cohort selector, heatmap, bar chart, reason-code donut
- `CohortHeatmap` + `ReasonCodeBreakdown` components
- Sidebar entry (Business+ gated)
- Tests: cohort SQL correctness, page rendering, plan gating

### Phase 5 (Week 5): Playbooks
- API: full playbook CRUD + run + run-batch + executions
- `playbook_seeder.py` with 7 templates (idempotent startup)
- Playbook execution engine (Celery task `run_playbook(playbook_id, customer_email)` that fan-outs to existing automation action handlers)
- Frontend: `/settings/playbooks` list + detail + editor
- `RunPlaybookDropdown` on customer profile
- Sidebar entry
- Tests: playbook CRUD, execution engine, action sequencing

### Phase 6 (Week 6): Accuracy dashboard + weekly calibration
- Celery Beat: `refit_all_orgs` Mondays 07:45 UTC, `refit_global_calibration` daily 03:00 UTC, `purge_old_executions` Sundays 03:00 UTC
- API: `GET /analytics/churn-accuracy` (org), `GET /system/churn-accuracy` (admin)
- Frontend: `/system/churn-accuracy` admin page (cross-org + drill-in)
- `ModelAccuracyCard` dashboard widget (Business+)
- Tests: refit task idempotency, accuracy API correctness, dashboard rendering

### Phase 7 (Week 7): Polish + cross-page consistency + landing page
- Audit every UI surface for risk_level → probability conversion
- Landing page: bento card for advanced churn prediction + FAQ entry
- Blog post draft: "How Rereflect predicts churn 30 days out" (for Aug roundup)
- E2E test: label → refit → predict → display
- Performance check: probability recompute under load
- Documentation updates: CLAUDE.md (Plan Gating section), AI-TRACKING.md (mark M4.1 complete), DEV-TRACKING.md

---

## 8. Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| <20 labels per org → no per-org calibration | Most orgs use global model with poor org-specific fit. | Global model fallback. UI shows "Using global model — mark customers as churned to improve accuracy." CSV import lowers the activation bar. |
| Silence-proxy label noise contaminates training | Happy customers labeled as churned (silent_churn). | Structured `reason_code` lets us train without silent_churn (filter at fit time). Display "manual labels only" filter on accuracy card. |
| Probability ↔ heuristic_score collinearity | Calibration is just a monotonic remap; not "real" ML. | Honest framing in UI. v2 milestone (M4.1.5) explicitly notes ML upgrade once labels ≥ 500. |
| Probability bands shifting on refit cause noisy `risk_level` changes | Customer churn moves between bands week-to-week. | Hysteresis: a customer doesn't downgrade severity unless probability dropped ≥ 0.05 below band threshold for 2 consecutive refits. |
| Playbook actions trigger downstream side effects (notifications, Slack, AI generation) | Cost overrun + spam to CS team. | Per-org daily playbook execution limit (Business=50/day, Enterprise=unlimited). Idempotency keys on action handlers. |
| Recompute every feedback × every probability change → expensive | DB/CPU load. | Probability only recomputes if `churn_risk_component` changed by ≥ 2 points. Calibration prediction is O(log n) — fast. |
| CSV import accepting malformed dates / invalid emails | Bad labels poison the model. | Strict validation: ISO date, RFC 5322 email, reason_code enum check. Preview before commit. Reject row + report to user. |
| Customers gaming the system by mass-marking everyone churned | Skews global calibration. | Per-org rate limit on churn events (max 500/day). Global model excludes orgs flagged for anomalous label velocity (>10× p99). |
| Mixed `auto_suggested` + `manual` labels in training | Auto labels reinforce silence-proxy bias. | `auto_suggested` excluded from fit by default. Toggle on system admin page for advanced users. |

---

## 9. Out of Scope (Explicit)

- **Real ML model** (logistic regression / XGBoost / Cox PH). Deferred to M4.1.5 once labels ≥ 500/org or ≥ 5,000 globally.
- **CLV / revenue impact scoring.** Requires Stripe-to-customer mapping; deferred until HubSpot M3.1 lands.
- **Real-time playbook execution on probability threshold cross.** v1 supports manual trigger + run-batch only. Auto-execution on threshold cross is M4.1.5.
- **Custom cohort builder** (filter by tag, category, custom field). v1 = 3 fixed dimensions.
- **A/B testing of playbooks** (which playbook saves more customers). Future work.
- **Multi-window prediction** (60-day, 90-day probability). v1 = 30-day only.
- **External label sources** (Stripe webhook, HubSpot CRM, Segment). Future integration milestones (M3.1, M3.2).
- **Feature impact prediction** ("ship this and churn drops 5%"). Deferred — needs longitudinal product change tracking.

---

## 10. Success Metrics (Post-Launch)

- ≥ 50% of Business+ orgs mark at least one customer as churned within 30 days of launch (label-collection adoption)
- ≥ 30% of Business+ orgs run at least one playbook within 30 days
- Calibration F1 (global model) ≥ 0.55 by week 8 post-launch
- Org-level F1 ≥ 0.65 for orgs with ≥ 100 labels by week 12
- At least 3 blog posts / case studies reference the probability + timeline feature
- Conversion from Pro → Business attributable to M4.1: ≥ 5 orgs in first 90 days

---

## 11. Open Questions (For Implementation Plan)

- Exact action schema reuse: how much of the Automations action JSON to share vs fork for playbooks?
- Should `recovered_at` reset `churn_risk_component` to neutral, or just unflag the customer? (Decision likely: just unflag.)
- Bootstrap n=200 for CI — acceptable latency? Will benchmark in Phase 1.
- Should system templates be editable by system admins (vs immutable)? Leaning immutable + clone-to-customize.
- Cohort SQL: cache layer? Recharts perf on >50 cohort cells?

---

## 12. References

- AI-TRACKING.md → M4.1 (lines 217–224)
- DEV-TRACKING.md → Phase 3 → Predictive Analytics
- PRD-PREDICTIVE-ANALYTICS.md (foundation: 9-factor heuristic + health score + 3-tier LLM analysis)
- PRD-CHURN-PREDICTION-ACCURACY.md (foundation: factor breakdown + confidence score + one-shot backtest)
- PRD-CUSTOMER-360.md (customer list + profile + LLM analysis section + activity timeline)
- CLAUDE.md → Plan Gating & Feature IDs
- Existing code: `services/worker-service/src/tasks/analysis.py:526-793`, `services/backend-api/src/services/health_score_service.py`, `services/backend-api/scripts/backtest_churn.py`
