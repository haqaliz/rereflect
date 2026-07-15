# Aspect spec — review-queue

**Parent PRD:** `../prd.md` (M5) · **Slug:** `review-queue` · **Sequencing:** wave 3 (after data-model)

## Problem slice & outcome

A CRM suggestion is a guess. Nothing trains a model until a **human confirms** it — this queue is the only thing that turns a `churn_label_suggestions` row into a real `CustomerChurnEvent` the calibrator fits on. Every other aspect (fetch, rule, harvest, backfill) is a volume feeder; pending suggestions never enter `customer_churn_events` (PRD M4), so without this surface the feature produces zero labels.

**Outcome.** An org admin opens `/customers`, sees "N CRM churn suggestions to review", skims the evidence, bulk-confirms the real churns and rejects the rest. Confirmed rows become `CustomerChurnEvent(source='manual', marked_by_user_id=<confirming user>)` — trainable, with provenance back to the suggestion. Rejected rows never re-appear.

## In scope

1. **`GET /api/v1/customers/churn-suggestions`** — `require_admin_or_owner` +
   `require_feature("advanced_churn_prediction")`, org-scoped. Query: `page` (≥1), `page_size`
   (1–100, default 20), `status=pending|confirmed|rejected` (default `pending`),
   `provider=hubspot|salesforce`, `search` (email substring). Response `{items, total, page,
   page_size}`; item = the suggestion row (`id, customer_email, provider, external_opportunity_id,
   suggested_churned_at, evidence, status, reviewed_by_user_id, reviewed_at, churn_event_id,
   created_at`). Order `suggested_churned_at DESC, id DESC`.
2. **`POST /api/v1/customers/churn-suggestions/{id}/confirm`** — same deps. Body
   `{reason_code: str REQUIRED ∈ CHURN_REASON_CODES, reason_text: str|None}` — no new enum value
   (Finding 6); the operator states *why*. Writes, via the **existing service path**,
   `CustomerChurnEvent(org, customer_email, churned_at=suggestion.suggested_churned_at,
   reason_code, reason_text, marked_by_user_id=current_user.id, source='manual')`; sets
   `status='confirmed'`, `reviewed_by_user_id`, `reviewed_at`, `churn_event_id` (provenance); then
   calls `_invalidate_probability(db, org.id, email)` as the shipped paths do
   (`churn_events.py:371,196,262`). Returns `{id, status: confirmed|skipped, churn_event_id, reason?}`.
3. **`POST .../{id}/reject`** — same deps. Body `{note: str|None}`. Sets `status='rejected'`,
   `reviewed_by_user_id`, `reviewed_at`; no event written, `churn_event_id` stays NULL. Never
   re-suggested: the harvester's `UNIQUE(org, provider, external_opportunity_id)` upsert must not
   resurrect a rejected row to `pending`.
4. **`POST .../bulk`** — same deps. Body `{action: 'confirm'|'reject', cohort: Cohort,
   reason_code?, reason_text?}`; `Cohort` is the shipped contract (`schemas/cohort.py`,
   `lib/api/customers.ts:52`): `{emails: string[]} | {filter: {status?, provider?, search?}}`,
   exactly one. `emails` resolves to that org's **pending** suggestions for those normalized
   emails; `filter` resolves to matching pendings. `reason_code` required when `action='confirm'`
   (else 422). Emails deduped, lowercased, order-preserving.
5. **Collision handling (non-negotiable).** `UNIQUE(organization_id, customer_email, churned_at)`
   (`models/churn_event.py:87-96`): confirming for a customer already hand-marked at the same
   close date raises `IntegrityError`. Confirm MUST (a) pre-check `_has_existing_active_event` →
   `skipped`, **and** (b) wrap the insert in `try/except IntegrityError → rollback → skipped` —
   both, since the pre-check is racy and the catch is the backstop. Never a 500, never a
   partial-bulk abort. A `skipped` suggestion still **resolves** — `status='confirmed'` with
   `churn_event_id` → the pre-existing event — so it leaves the queue.
6. **Bulk result shape** — reuse the shipped public-bulk contract exactly
   (`docs/planning/public-api-crud-v3/`): `{matched, confirmed, skipped, results: [{id, status:
   confirmed|skipped|error, reason?}]}` in **deduped input order**. Best-effort per item: each item
   commits (or SAVEPOINTs) independently — one collision must not roll back the other 40.
   `confirmed + skipped + errors == len(results) == matched`. For `action='reject'`, `confirmed`
   counts rejections (name kept for contract parity; noted in the docstring).
7. **Role posture (deliberate divergence).** The existing churn-event routes carry **no role dep** —
   any member can write labels. We do **not** replicate that; all four new routes are
   `require_admin_or_owner`. We also do not fix the old routes here.
8. **Frontend.** `lib/api/churn-suggestions.ts` — `listChurnSuggestions`, `confirmChurnSuggestion`,
   `rejectChurnSuggestion`, `bulkReviewChurnSuggestions`; types `ChurnSuggestion`,
   `SuggestionCohort`, `BulkReviewResult` (mirror `lib/api/churn-events.ts`). On `/customers`, a 5th
   `StatCard` — "CRM churn suggestions", value = pending count, `icon={Inbox}`, `color="yellow"` —
   navigating to the review view; zero pending → card absent (an org that never configured it sees
   nothing, per PRD personas). Review rows show `customer_email` + evidence (deal name, close date,
   amount, stage/type) + provider badge + checkbox, reusing the cohort selection machinery
   (`rowSelection` → `selectedEmails` → `cohort`) and the select-all-matching-filter banner
   (`customers/page.tsx:282-293`). Confirm reuses `MarkAsChurnedDialog` / `BulkMarkChurnedDialog`'s
   **required-reason-code UX** (`ReasonCodeSelect`; submit disabled until picked), with the
   churned-date input **replaced by a read-only CRM close date** (stability is what makes re-harvest
   idempotent, PRD M2). Toast states skips (`"41 confirmed, 6 skipped (already marked)"`).

## Out of scope

- The suggestions table + migration, harvester, provider fetch, opt-in config (waves 1–2);
  backfill (M7); readiness counting (M6).
- Pre-existing churn-event route gaps: missing role deps, inconsistent dedup across the three write
  paths, `recover`/`delete` not invalidating probability, `RecoverRequest.note` discarded
  (Finding 5). The 500/day churn-event rate limit (never built; our writes are human-gated).
- Auto-confirm above a confidence threshold; un-rejecting a rejected suggestion. Writing
  `source='auto_suggested'` — confirm writes `source='manual'`, always.

## Acceptance criteria (testable)

1. `GET` returns only the caller's org's suggestions — another org's rows absent even by id;
   `?status=pending` excludes confirmed/rejected; default status is `pending`.
2. `GET` as **member** → 403; as admin and owner → 200 (regression guard for the divergence).
3. Confirm creates exactly one `CustomerChurnEvent` with `source='manual'`, `marked_by_user_id ==`
   confirming user, `churned_at == suggestion.suggested_churned_at`; sets `status='confirmed'` **and**
   `churn_event_id == <new event>.id`; leaves `CustomerHealth.probability_computed_at` NULL.
4. Confirm without `reason_code`, or with one ∉ `CHURN_REASON_CODES` → 422; no event written,
   suggestion stays `pending`.
5. **Collision, pre-check path:** customer has an active event → `status='skipped'`, no second
   event, suggestion resolved (not left `pending`). **Race path:** with
   `_has_existing_active_event` patched to `False`, confirm still returns `skipped` — **not 500** —
   and the session stays usable (a later write in the same request succeeds).
6. Reject writes no event, sets `status='rejected'`, `churn_event_id IS NULL`; re-harvesting the
   same `external_opportunity_id` leaves it `rejected` and out of `?status=pending`.
7. **Bulk 41-of-42:** 42 pendings, 1 collides → `{matched:42, confirmed:41, skipped:1}`, 41 events
   exist, `len(results)==42` in deduped input order.
8. Bulk: duplicate email → deduped, `matched` counts it once; both `{emails}` and `{filter}` (or
   neither) → 422; `action='confirm'` without `reason_code` → 422, nothing written; a `filter`
   cohort touches only `pending` rows of the caller's org.
9. Frontend: StatCard hidden at 0 pending, visible with a count, navigates to the review view;
   confirm submit disabled until a reason code is selected (both dialogs).

## Dependencies & sequencing

- **Blocked by (wave 1–2):** `churn_label_suggestions` table + model + migration (PRD Data Model —
  the pre-existing 2-alembic-head fork, R6, is that aspect's) and the `evidence` JSON contract.
- **Reuses, does not modify:** `_get_active_churn_event`, `_has_existing_active_event`,
  `_invalidate_probability` (`churn_events.py:74-150`); `CHURN_REASON_CODES`
  (`models/churn_event.py:30-37`); `schemas/cohort.py`; `ReasonCodeSelect`, `MarkAsChurnedDialog`,
  `BulkMarkChurnedDialog`; `StatCard`.
- **Blocks:** M6 readiness copy ("N pending suggestions") reads the same status counts; the
  precision metric (confirmed ÷ reviewed) is only computable once this ships.
- **Parallel-safe with:** M1/M2/M4 (worker-side) — no shared files. New backend files:
  `src/api/routes/churn_suggestions.py`, `src/schemas/churn_suggestion.py`, + router registration in
  `src/api/main.py`. Tests: house style — real SQLite `db` fixture, no Celery, no patching except
  AC5's race sim.

## Risks

- **R-A — the feature's whole trust boundary is one endpoint.** If confirm ever writes without a
  human, false labels reach the calibrator silently (no source filter on readiness, cohorts, winback
  or timeline — Finding 3). **Mitigation:** `marked_by_user_id` non-negotiable and asserted (AC3);
  no path may set it NULL; no auto-confirm in v1.
- **R-B — `skipped` semantics could mis-attribute.** Resolving a collision to
  `confirmed + churn_event_id=<pre-existing>` clears the queue but attributes an event this action
  did not create. **Mitigation:** toast and `results[].reason` say `already_marked`; the alternative
  (leave `pending` forever) re-surfaces an unactionable row daily.
- **R-C — bulk over a `filter` cohort is unbounded.** A backfilled org could confirm thousands in
  one request (the 500/day cap was never built). **Mitigation:** cap the resolved cohort per request
  and report `matched` vs. cap — **no silent caps** (house rule); value set in the plan.
- **R-D — evidence is the operator's only basis for judgement**; a thin/null blob makes confirm a
  coin-flip. **Mitigation:** render an explicit "no CRM detail captured" state.
- **R-E — reason-code overloading.** CRM suggestions map to none of the six codes (Finding 6), so
  operators reach for `other`, diluting a bucket the fit filters on. Accepted for v1.
