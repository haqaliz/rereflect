# Aspect Spec — m5.0-readiness-report

**Parent PRD:** `../prd.md` · **Sequencing:** INDEPENDENT — no dependency on `sentiment-provider-core`,
`per-org-resolution`, `model-packaging`, or `eval-harness-and-card`. Can be built fully in parallel;
owns PRD must-have #8 and `AI-TRACKING.md:313` (M5.0 — Data & Model Readiness Assessment, no ML).

## Problem slice & outcome

M5.2 (per-org self-improving classifiers) and M5.3 (per-org churn ML) are documented but **nobody
knows whether real orgs have enough data to train them.** `AI-TRACKING.md:313-317` calls this out
explicitly as the cheap, first, non-negotiable step: "we know per real org whether A and C are
buildable now or need bootstrapping." The raw data already exists — `FeedbackItem` rows,
`AICorrection` rows (M3.3 flywheel), `CustomerChurnEvent` rows (M4.1 labels) — but there is no
aggregation surfacing it.

This aspect ships a **pure read/aggregation** endpoint (no ML, no new tables, no migration) that
counts, per org: feedback volume, `AICorrection` counts by type, and churn-label counts +
distribution — plus the target thresholds M5.2/M5.3 will gate on and an honest ready/not-ready
flag. A small frontend card surfaces it under **Settings → AI**.

**Outcome:** `GET /api/v1/analytics/ai-readiness` returns a per-org readiness snapshot; a new
**Readiness** tab on `settings/ai/page.tsx` renders it via `AIReadinessCard`.

## Data model grounding (read before coding — exact field names)

- **`AICorrection`** (`services/backend-api/src/models/ai_correction.py:6`) — `organization_id`,
  `correction_type` (String(50), free string, **not a DB enum**). The model's own doc-comment
  declares five aspirational values: `copilot_response | sentiment | category | churn_risk |
  response_suggestion`. **What is actually written today** (grepped every `correction_type=`
  call site):
  - `services/frontend-web/app/(dashboard)/feedbacks/[id]/page.tsx:271-274` —
    `correctionTypeMap = { sentiment: 'sentiment', pain_point: 'category', feature_request:
    'category' }` → writes `'sentiment'` or `'category'`.
  - `services/frontend-web/app/(dashboard)/customers/[email]/page.tsx:426` — writes
    `'churn_risk'`.
  - `services/frontend-web/components/copilot/MessageActions.tsx:55,76` — writes
    `'copilot_response'`.
  - `'response_suggestion'` is declared in the model comment but **never written anywhere** —
    dead/aspirational value.
  - **`AI-TRACKING.md:313` / PRD must-have #8 say "sentiment/category/urgency."** There is **no
    `'urgency'` correction_type in the schema or the code.** The closest real analog is
    `'churn_risk'` (the customer-profile churn-risk-score correction, which is the urgency-adjacent
    signal in this codebase — `feedback.is_urgent`/`urgent_category` have no correction UI wired
    to `AICorrection` at all). **Resolution for this aspect:** do **not** hardcode a fixed
    `{sentiment, category, urgency}` triple in the response schema — it would silently misreport
    (zero `urgency` forever, since it never exists) and break the moment a new `correction_type`
    is added. Instead mirror the existing `GET /api/v1/ai-corrections/stats` endpoint's own
    `by_type: Dict[str, int]` shape (`services/backend-api/src/api/routes/ai_corrections.py:69-72,
    165-172`) — a dynamic group-by, forward-compatible, and already the precedent the frontend
    (`settings/ai/page.tsx:44-49` `CORRECTION_TYPE_LABELS`) already handles generically. The PRD
    wording is treated as informal shorthand for "by type," not a literal fixed enum.
  - Index: `ix_ai_corrections_org_type` on `(organization_id, correction_type)` — exactly matches
    our query shape (count total + group by type, both filtered by org).

- **Churn labels — `CustomerChurnEvent`** (`services/backend-api/src/models/churn_event.py:46`),
  **not** `ChurnCalibrationModel`/`ChurnBacktestRun` (those are *derived model artifacts*, not the
  labels themselves). Fields: `organization_id`, `customer_email`, `churned_at`, `reason_code`
  (one of module-level `CHURN_REASON_CODES = ["price","competitor","product_quality",
  "no_longer_needed","silent_churn","other"]`), `recovered_at` (nullable — set when a customer
  "un-churns"; the row is **not** deleted), `source` (one of `CHURN_EVENT_SOURCES =
  ["manual","csv_import","auto_suggested"]`). Index: `ix_churn_event_org_date` on
  `(organization_id, churned_at)` — leftmost `organization_id` covers our org-scoped count/group-by
  filters; `reason_code`/`source` aren't indexed but this is a low-QPS admin report, not a hot path.

- **Feedback volume — `FeedbackItem`** (`services/backend-api/src/models/feedback.py:7`) —
  `organization_id`. Index: `ix_feedback_org_date` on `(organization_id, created_at)` — leftmost
  `organization_id` covers a `COUNT(*) WHERE organization_id = ?`.

- **`~500 churn labels` target** comes from `AI-TRACKING.md:317` verbatim ("gate ... M5.3 (~500
  churn labels)"). This is a **different, larger** number than the existing
  `churn_calibrator.MIN_LABELS = 20` (`services/backend-api/src/services/churn_calibrator.py:20`)
  — that constant gates the **already-shipped** per-org isotonic-regression *calibration* (M4.1),
  a much cheaper fit than the ML classifier M5.3 will train. Do not conflate the two; this aspect's
  threshold is a **new, separate constant** for the not-yet-built M5.3.
  - **No PRD/tracking number exists for the M5.2 "correction volume" target.** This aspect must
    propose one. Recommendation: a plain module constant, `CORRECTION_VOLUME_TARGET = 200` (total
    corrections across all types, per org) — a defensible v1 floor for a few-shot per-org
    classifier (SetFit-style training typically wants dozens-to-low-hundreds of labeled examples
    per class; 200 total across `sentiment`/`category`/`churn_risk` is a conservative, round,
    honestly-labeled starting gate). **This number is explicitly a placeholder, not a validated
    ML result** — call it out as tunable once M5.2 actually runs a training pass and reports what
    volume it needed. State this caveat in the API docstring and the frontend copy, per the PRD's
    "framed honestly" instruction.

## Endpoint design

`GET /api/v1/analytics/ai-readiness` — new router `src/api/routes/ai_readiness.py`,
`analytics_router = APIRouter(prefix="/api/v1/analytics", tags=["ai-readiness"])`, mirroring
`churn_accuracy.py`'s `analytics_router` (same prefix, sibling route). Registered in `main.py`
next to the existing `churn_accuracy_router` includes.

**Auth/scoping:** `current_org: Organization = Depends(get_current_org)` (which itself depends on
`get_current_user`) — **no role gate, no plan/feature gate.** Rationale: (a) it's a read-only,
purely informational report, matching RBAC matrix "View dashboard & analytics — ✅ all roles"; (b)
it mirrors `GET /api/v1/ai-corrections/stats`, which is explicitly "any authenticated user (no plan
gating)"; (c) the repo is OSS/self-hosted-first (`SELF_HOSTED=true` default makes `require_feature`
a no-op anyway — memory: `rereflect-oss-pivot`) so gating behind a feature flag would be theater.
All queries filter by `organization_id == current_org.id` — never cross-org.

**Response schema** (`src/schemas/ai_readiness.py`, flat like `AccuracyCardResponse` — no deep
nesting):

```python
class AIReadinessResponse(BaseModel):
    organization_id: int
    generated_at: datetime

    # Feedback volume
    feedback_volume: int

    # AICorrection counts (M3.3 flywheel)
    corrections_total: int
    corrections_by_type: Dict[str, int]        # dynamic keys, e.g. {"sentiment": 12, "category": 4, "churn_risk": 1}

    # Churn labels (M4.1 CustomerChurnEvent)
    churn_labels_total: int
    churn_labels_recovered: int                # subset of total where recovered_at is not null
    churn_labels_by_reason: Dict[str, int]      # keyed by reason_code
    churn_labels_by_source: Dict[str, int]      # keyed by source

    # Activation thresholds this report exists to inform (M5.0 exit criterion)
    correction_volume_target: int               # CORRECTION_VOLUME_TARGET constant (v1 proposal, see above)
    churn_label_target: int                     # CHURN_LABEL_TARGET constant (500, from AI-TRACKING.md:317)
    correction_volume_ready: bool                # corrections_total >= correction_volume_target
    churn_labels_ready: bool                     # churn_labels_total >= churn_label_target

    class Config:
        from_attributes = True
```

`correction_volume_ready`/`churn_labels_ready` are **v1 proxies** using the *total* count, not a
per-type gate — `corrections_by_type` is exposed precisely so a human (or later M5.2 itself) can
see whether the total is concentrated in one type or spread thin. Document this caveat in the
route docstring.

Threshold constants live in `src/config/readiness_thresholds.py` (new, tiny module — plain
constants, not env-configurable, mirroring `churn_calibrator.MIN_LABELS`'s style rather than the
`plans.py` env-driven style, since these are planning heuristics, not billing/feature toggles):

```python
CHURN_LABEL_TARGET = 500          # AI-TRACKING.md:317 — M5.3 exit criterion, verbatim
CORRECTION_VOLUME_TARGET = 200    # proposed v1 floor for M5.2; unvalidated, tune after first real training run
```

## In scope

- `services/backend-api/src/config/readiness_thresholds.py` — the two constants above.
- `services/backend-api/src/schemas/ai_readiness.py` — `AIReadinessResponse`.
- `services/backend-api/src/api/routes/ai_readiness.py` — the route, org-scoped, three small
  aggregation helper functions (`_feedback_volume`, `_correction_counts`, `_churn_label_counts`),
  each a single filtered `func.count`/`group_by` query (mirror `churn_accuracy.py`'s
  `_get_active_model`/`_collect_history` helper style).
- `services/backend-api/src/api/main.py` — one import + `app.include_router(ai_readiness_router.router)`
  next to the existing `churn_accuracy_router` includes.
- `services/backend-api/tests/test_ai_readiness.py` — full TDD coverage (see plan).
- `services/frontend-web/lib/api/ai-readiness.ts` — `aiReadinessAPI.get(): Promise<AIReadiness>`
  (mirrors `lib/api/ai-corrections.ts` shape/style, camel-free — snake_case field names passed
  through as-is, matching every other API client in this repo).
- `services/frontend-web/components/settings/AIReadinessCard.tsx` — the card: feedback volume,
  corrections total + by-type breakdown, churn-label total + by-reason/by-source breakdown, two
  progress indicators (corrections vs `correction_volume_target`, churn labels vs
  `churn_label_target`) with a ready/not-ready badge each, and copy stating the thresholds are
  "planning targets, not guarantees" (honest framing, per PRD).
- `services/frontend-web/app/(dashboard)/settings/ai/page.tsx` — **minimal, isolated diff**: add
  `'readiness'` to `VALID_TABS`, one `<TabsTrigger value="readiness">`, one
  `<TabsContent value="readiness">` rendering `<AIReadinessCard />`. **Deliberately a new tab, not
  an addition to the existing `'accuracy'` tab** — the sibling `eval-harness-and-card` aspect (PRD
  must-have #7, not yet spec'd as of this writing) is also expected to touch the `'accuracy'` tab
  on this same file; keeping this aspect's readiness UI on its own tab avoids a merge collision on
  that tab's JSX body. The `VALID_TABS` array/`TabsList` edit is a small, easy-to-rebase diff either
  way.
- `services/frontend-web/__tests__/settings/AIReadinessCard.test.tsx` — component tests (mocked
  API client, mirroring `AISettingsUsage.test.tsx`/`ModelAccuracyCard.test.tsx` patterns).

## Out of scope

- Any ML/training work (M5.2, M5.3 themselves) — this aspect only reports counts and a threshold
  comparison; it must never construct or fit a model.
- The `SentimentProvider`/`resolve_sentiment_provider` provider layer — entirely unrelated; this
  aspect has zero interaction with `analysis-engine`, `OrgAIConfig.sentiment_provider`, or the two
  sentiment call sites.
- Model packaging, Dockerfile/`HF_HOME` wiring, pre-bake — N/A, no models here.
- The eval harness / accuracy card (transformer vs VADER metrics) — a different endpoint
  (`GET /sentiment/accuracy` per PRD contract), a different aspect, and a different tab.
- Any Alembic migration — this is a pure read over existing tables; no new columns/tables.
- System-admin cross-org overview (like `churn_accuracy.py`'s `system_router`) — the PRD scopes
  must-have #8 to "per org" only; a cross-org admin rollup is a plausible follow-up but not asked
  for here. Flagged as an open question below, not built.
- Making `CORRECTION_VOLUME_TARGET`/`CHURN_LABEL_TARGET` configurable per-org or via env var — v1
  ships plain module constants; revisit only if an operator explicitly asks to tune them.

## Testable acceptance criteria

- **AC1 (empty org → zeros):** A freshly created org with no `FeedbackItem`/`AICorrection`/
  `CustomerChurnEvent` rows returns `feedback_volume=0`, `corrections_total=0`,
  `corrections_by_type={}`, `churn_labels_total=0`, `churn_labels_recovered=0`,
  `churn_labels_by_reason={}`, `churn_labels_by_source={}`, `correction_volume_ready=False`,
  `churn_labels_ready=False`, and the two target constants echoed back unchanged. HTTP 200 (not
  404 — an org with zero data is a valid, expected state, not an error).
- **AC2 (org with mixed data → correct counts):** Seed N feedback items, M corrections split across
  ≥2 `correction_type` values (including one org's worth of `sentiment` + `category` +
  `churn_risk`), K churn events split across ≥2 `reason_code`/`source` values with at least one
  `recovered_at` set. Assert every count and every breakdown dict matches the seeded data exactly
  (exact key→count pairs, not just totals).
- **AC3 (cross-org isolation):** Two orgs, each with their own feedback/corrections/churn-label
  rows. Org A's token must only see Org A's counts — assert Org B's rows are never included (classic
  off-by-one risk: a bug that omits the `organization_id` filter on any one of the three queries).
- **AC4 (ready-flag thresholds — corrections):** `corrections_total` exactly at
  `CORRECTION_VOLUME_TARGET - 1` → `correction_volume_ready is False`; exactly at
  `CORRECTION_VOLUME_TARGET` → `True` (boundary-inclusive `>=`).
- **AC5 (ready-flag thresholds — churn labels):** Same boundary test for `churn_labels_total` vs
  `CHURN_LABEL_TARGET`.
- **AC6 (recovered churn events still count as labels):** A `CustomerChurnEvent` with
  `recovered_at` set still contributes to `churn_labels_total` and its `reason_code`/`source`
  bucket (recovery doesn't erase that the customer did churn at some point) but is also reflected
  in `churn_labels_recovered`.
- **AC7 (auth required, any role):** No token → 401. A `member`-role token (not just admin/owner)
  → 200 with correct data (confirms no unintended role gate, matching the "all roles can view
  analytics" RBAC row).
- **AC8 (frontend — loading/empty/populated states):** `AIReadinessCard` shows a loading skeleton
  while the fetch is pending, an honest empty/zero-state when all counts are 0 (not a blank card),
  and correct numbers + ready/not-ready badges once loaded. A failed fetch shows an error state
  (mirrors `ModelAccuracyCard`'s "failed to load" pattern) rather than crashing.

## Dependencies & sequencing

- **Upstream:** none — reads only existing, already-migrated tables (`feedback_items`,
  `ai_corrections`, `customer_churn_events`). No dependency on `sentiment-provider-core`,
  `per-org-resolution`, or `model-packaging`.
- **Downstream:** informs (but does not block) the future M5.2/M5.3 milestones, which will read
  this report manually/operationally, not call this endpoint programmatically — no code coupling.
- Can be implemented and merged independently of every other `local-analyzer-sentiment-model`
  aspect; the only shared-file touch point is `settings/ai/page.tsx` (see the tab-isolation note
  above) and `main.py` (additive router include — low collision risk, every other aspect appends
  its own router the same way).

## Open questions / risks

- **OQ1 — is a system-admin cross-org rollup wanted?** `churn_accuracy.py` has a `system_router`
  precedent for "show me this metric across every org." Not requested by the PRD for M5.0, but a
  natural follow-up once there are multiple real self-hosted orgs to compare. Recommend: skip for
  v1, revisit if/when multi-org self-host operators actually ask.
- **OQ2 — should `CORRECTION_VOLUME_TARGET` be per-type instead of a single total?** Flagged above;
  v1 uses one aggregate number for simplicity and because there is no empirical M5.2 training data
  yet to justify per-type numbers. `corrections_by_type` is still exposed so this can be revisited
  without a schema change (additive: add per-type ready flags later).
  A `reason_code`/`source` composite index on `customer_churn_events` — not needed at v1's admin-report
  query volume (this endpoint is not a hot path; existing org-scoped composite indexes already
  bound the row-scan to one org's rows). Flag as a "consider if slow at scale" note, not a blocker.
- **Risk — `correction_type`/`reason_code`/`source` are free strings, not DB enums.** A typo'd or
  new value (e.g. a future `AICorrection.correction_type='urgency'` if that ever gets wired up)
  will simply show up as a new key in `corrections_by_type` — this is the intended forward-compatible
  behavior, not a bug, but worth stating so nobody "fixes" the dynamic-dict design into a fixed
  enum later without re-reading this doc.
