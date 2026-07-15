# Aspect spec — readiness-honesty

**Parent PRD:** `../prd.md` (M6) · **Slug:** `readiness-honesty` · **Sequencing:** wave 2

## Problem slice & outcome

**The readiness report can tell an operator they are ready to train on labels the fit refuses to
use.** `_churn_label_counts` (`routes/ai_readiness.py:74-79`) counts `CustomerChurnEvent` with
**no source filter**, and `churn_labels_ready = churn["total"] >= CHURN_LABEL_TARGET` (`:149`,
`config/readiness_thresholds.py:8` = 500). The calibrator meanwhile excludes
`source='auto_suggested'` in **four** places — `tasks/churn_calibration.py:50,125`,
`services/calibration_refit.py:64,191`. The report and the fit disagree about what a label is.

Worse than an inert counter: this is the one number an operator consults to decide whether M5.3 is
reachable, and it can say *ready* on rows the fit drops (or, at `:125`/`:191`, trains as
**negatives**).

**Outcome:** `churn_labels_ready` counts only **trainable** labels, aligned with the four
calibration filters; pending CRM suggestions surface as a **separate** number that never counts
toward readiness. Defensive — this feature writes no `auto_suggested` rows (PRD Out of Scope) —
but the report should agree with the fit regardless of who writes.

## In scope

1. **`trainable` count** — `_churn_label_counts` gains a count of the org's `CustomerChurnEvent`
   with `source != 'auto_suggested'`, mirroring the four calibration filters. Exposed as a new
   `churn_labels_trainable` field on `AIReadinessResponse`.
2. **`churn_labels_ready = trainable >= CHURN_LABEL_TARGET`** (`:149`) — the **only** semantic
   change to the boolean. `CHURN_LABEL_TARGET` stays 500; this aspect does not re-derive it (R8).
3. **`churn_labels_total` keeps its current meaning** — every event regardless of source. It is
   "what exists"; `churn_labels_trainable` is "what trains". Both reported; the gap is the honesty.
4. **`churn_labels_by_source` keeps showing `auto_suggested`** — the breakdown exists so a human
   can see composition. Only the boolean and the new trainable total change.
5. **`pending_suggestions`** — count of `churn_label_suggestions` WHERE
   `organization_id = org_id AND status = 'pending'` (M4 table), as a **separate** response field.
   **Never** added to `churn_labels_total`, `trainable`, or the boolean. Zero when unconfigured.
6. **Frontend Readiness card copy** — trainable-vs-target and pending rendered as distinct facts,
   e.g. *"312 trainable labels / 500 · 47 CRM suggestions awaiting review"*, with the review queue
   linked. A suggestion must never read as progress toward the gate.
7. **A comment at the trainable filter naming the four calibration sites it mirrors**, so the next
   editor of either side sees the coupling.

## Out of scope

- **Changing `CHURN_LABEL_TARGET` or re-deriving the 500 gate.** PRD R8 flags 500 as a pre-pivot
  artifact (the "≥5,000 globally" half is meaningless post-OSS-pivot) and recommends a separate
  M5.3-scoped investigation. M8 records it as under review; this aspect does not do it.
- **The other three no-source-filter consumers** — cohort analytics
  (`churn_analytics.py:356-363`), winback (`winback_detector.py:103-116`), timeline
  (`customer_timeline_service.py:417`). Harmless under this design (no auto rows written); logged
  in `understanding.md` Finding 3, not fixed here.
- **Any calibration-side change.** The four filters are correct; the report moves to them.
- `correction_volume_ready` / `CORRECTION_VOLUME_TARGET` and the corrections half of the report.
- Writing, confirming, or harvesting suggestions — M4/M5.

## Acceptance criteria (testable)

- **AC-1 (the bug).** 500 `manual` + 1 `auto_suggested` → `churn_labels_trainable == 500`,
  `churn_labels_ready is True`. 499 `manual` + 5 `auto_suggested` → `churn_labels_total == 504`,
  `churn_labels_trainable == 499`, **`churn_labels_ready is False`**. The second case fails on
  today's code — it is the regression test for the bug.
- **AC-2 (breakdown preserved — existing tests stay green unmodified).**
  `tests/test_ai_readiness.py:172,190` assert `churn_labels_total == 4` and
  `churn_labels_by_source == {"manual": 2, "csv_import": 1, "auto_suggested": 1}`. Both still
  pass; the auto row keeps appearing in `by_source` and in `total`.
- **AC-3 (trainable sources).** `manual` and `csv_import` both count as trainable; only
  `auto_suggested` is excluded — asserted per source value, matching the calibration filters.
- **AC-4 (recovered unchanged).** A recovered event still counts toward `total`, its
  `by_reason`/`by_source` bucket, **and** `trainable` if its source is trainable — the `:68-72`
  docstring stays true; recovery is not a source filter.
- **AC-5 (pending is separate).** 47 `pending` + 3 `confirmed` + 2 `rejected` →
  `pending_suggestions == 47`; `churn_labels_total` and `churn_labels_trainable` are **unchanged**
  by any suggestion row. With 499 trainable + 47 pending, `churn_labels_ready is False` —
  suggestions never close the gap.
- **AC-6 (confirmed counts via its event, not itself).** Confirming a suggestion writes
  `CustomerChurnEvent(source='manual')` (M5) → trainable +1, `pending_suggestions` −1. No double
  count.
- **AC-7 (org scoping).** Suggestions and events from another org contribute 0 to every field —
  extends the existing cross-org isolation test.
- **AC-8 (no gate change).** The endpoint stays read-only with no role gate (any org member can
  view, per the `:119-131` docstring and the RBAC "view analytics — all roles" row). No
  `require_admin_or_owner` added here.
- **AC-9 (frontend).** The card renders trainable/target and pending as two distinct numbers;
  pending is never summed into the progress indicator. Zero pending → the line is absent, not
  "0 suggestions" noise.

**Test style.** Strict TDD, tests first. Extend `services/backend-api/tests/test_ai_readiness.py`
with its existing `_make_churn_event` / `_make_org` helpers + the real SQLite `db` fixture; add a
`_make_suggestion` helper in the same shape. No patching.

## Dependencies & sequencing

**Wave 2 — blocked on `data-model` (M4's `churn_label_suggestions` table + migration)** for §5's
`pending_suggestions` only. §1–§4 (the trainable fix) depend on nothing and could ship first; kept
in one aspect so the card tells one honest story, but if the migration slips, the trainable fix is
the half that can land alone. Independent of `harvester-core`, `review-queue`, and
`historical-backfill` — touches only `routes/ai_readiness.py`, its schema, its test, and the
frontend Readiness card. Feeds `docs-and-tracking` (M8, wave 4). Adds **no** migration of its own
and must not resolve the PRD R6 2-head fork.

## Risks

- **Existing tests encode the current breakdown.** `:172,190` are the guardrail, not an obstacle:
  if a change makes them fail, the change is too broad. AC-2 pins this.
- **Coupling by convention, not by code.** The trainable filter duplicates a rule living in four
  worker-side files, and the worker cannot import backend code — a fifth copy can drift. Mitigated
  by §7's comment; a shared constant is not worth a cross-service mirror for one string.
- **The number will go down.** An operator at "500/500 ready" may see "499/500". That is the point
  — M8 must say so plainly rather than shipping a silent correction to a trust surface.
- **PRD R8 — the target may be wrong anyway.** Being honest about *which* labels count does not
  make 500 the right number. Not this aspect's problem; M8 records it as under review so we stop
  quoting 500 as settled.
- **`pending_suggestions` could be misread as progress.** A copy risk. AC-9 pins the two numbers
  apart; the review-queue link makes pending actionable, not aspirational.
