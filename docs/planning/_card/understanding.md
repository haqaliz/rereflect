# Understanding — feat/crm-churn-labels (Phase 2 dig)

**Date:** 2026-07-15 · **Branch:** `feat/crm-churn-labels`
**Method:** 5 parallel read-only dig agents (churn-label domain, calibration pipeline, CRM
enrichment layer, churn frontend surfaces, status-sync precedent). All claims below are
file:line-verified against the worktree.

---

## What the card assumed vs. what the code says

The handoff brief assumed the CRM churn signal was **already synced and merely unused**, so the
work would be: read `crm_enrichment`, write `auto_suggested` rows, add a review queue.

**That assumption is wrong in two independent ways.** Both are load-bearing.

### Finding 1 — the churn signal is not fetched; it is actively discarded

Neither provider stores anything that marks a customer as churned.

- **HubSpot.** `clients/hubspot.py:280-284` filters the deal list:
  `closed_stages = {"closedwon", "closedlost"}` → returns only deals **not** in that set.
  `tasks/hubspot_sync.py:56-63` (`_pick_renewal_deal`) re-applies the same exclusion. So
  `crm_enrichment.deal_stage` **can never hold `closedlost`**. The data is in the batch-read
  response and thrown away — recoverable without new scopes, but both filters must change.
- **Salesforce.** `clients/salesforce.py:298` never fetches it at all:
  `SELECT Id, Name, StageName, Amount, CloseDate, IsClosed FROM Opportunity
   WHERE AccountId = '...' AND IsClosed = false`.
  The `IsClosed = false` predicate excludes every closed opportunity **at the API**, and
  `IsWon` is never selected. `tasks/salesforce_sync.py:107` re-skips on `IsClosed`.
- **Lifecycle stage is not a churn marker either.** HubSpot's standard lifecycle picklist has
  no churned value (a churned marker would be a portal-custom stage). Salesforce's
  `lifecycle_stage` is `Account.Type` (`salesforce_sync.py:275`) — standard picklist
  (Customer/Prospect/Partner), no churned value.

**Consequence:** this is not a read-what's-there feature. It needs new/changed fetch paths per
provider, and the "detect churn signals" line in the brief hides real work.

### Finding 2 — "Closed Lost" is not churn (the semantic trap)

A Closed Lost opportunity most often means **a deal that never closed — a prospect who didn't
buy**. That is not churn; the customer never existed. Labelling those as churned injects
**false-positive labels**, precisely the "bad labels poison the model" failure the PRD names for
CSV import (`PRD-ADVANCED-CHURN-PREDICTION.md:455`).

Distinguishing a lost **renewal** (real churn) from a lost **new-business** deal requires a
field neither provider fetches today:
- Salesforce: `Opportunity.Type` (`New Business` / `Existing Business` / `Renewal`) — **not
  selected**; only `Account.Type` is (`salesforce.py:289`).
- HubSpot: deal `pipeline` — **not requested** (`hubspot.py:252` requests only
  `dealname, dealstage, amount, closedate`).

Both are per-org CRM configuration with no portable defaults. **This makes the churn definition
necessarily operator-configurable, and the default necessarily conservative.**

---

## Finding 3 — writing `auto_suggested` rows silently corrupts three consumers

The brief's caveat ("harvesting alone trains nothing") is real but **understated**. The
`source != "auto_suggested"` exclusion exists in exactly 4 places, **all in worker-service**:

| Ref | Query | Behavior |
|---|---|---|
| `tasks/churn_calibration.py:50` | `_count_org_labels` | auto excluded from the 20-label gate |
| `tasks/churn_calibration.py:125` | `refit_global_calibration` | auto-churned customers labelled **0.0 (negative)** |
| `services/calibration_refit.py:64` | `refit_org` gate | second gate, defense-in-depth |
| `services/calibration_refit.py:191` | `_collect_labels` | auto-churned enter training as **negatives** |

Everything **else** that reads `CustomerChurnEvent` has **no source filter**, so auto rows are
treated as real churn:

1. **M5.0 readiness lies.** `api/routes/ai_readiness.py:74-79` counts labels with **no source
   filter**; `churn_labels_ready = churn["total"] >= CHURN_LABEL_TARGET` (`:149`,
   `config/readiness_thresholds.py:8` = 500). So auto labels would flip
   `churn_labels_ready` **true** on labels the fit refuses to use — actively telling the
   operator they're ready for M5.3 when they are not. This is worse than an inert counter.
2. **Cohort analytics inflate.** `api/routes/churn_analytics.py:356-363` filters only on org +
   email — auto rows count as churned in every cohort.
3. **Winback notifications fire on unconfirmed guesses.**
   `worker-service/src/services/winback_detector.py:103-116` treats any `recovered_at IS NULL`
   row as an active churn, regardless of source.
4. **Timeline shows them as fact.** `services/customer_timeline_service.py:417` — no source filter.

Also note the PRD promised a **system-admin toggle** to include auto labels in training
(`PRD-ADVANCED-CHURN-PREDICTION.md:457`). It was never built — the exclusion is hard-coded.

---

## Finding 4 — there is no source-aware write path

`schemas/churn_event.py` defines and validates `ChurnEventCreate.source`, but
**`routes/churn_events.py:357` hardcodes `source="manual"`** and ignores `body.source`. The
validated field is dead on the only endpoint that accepts it. Bulk (`:190`) is also hardcoded
`"manual"`; CSV (`:256`) is `"csv_import"`. **Nothing writes `auto_suggested`** — the 4
exclusion filters guard a producer that does not exist.

## Finding 5 — dedup is already inconsistent, and the harvester will hit it

`UniqueConstraint(organization_id, customer_email, churned_at)` — **3 columns**
(`models/churn_event.py:87-96`). There is **no** uniqueness on `(org, email)`, so a customer can
hold several simultaneously-active rows at different dates. The three existing write paths each
dedup differently:
- single create: no pre-check, relies on the index → `IntegrityError` → 409
- bulk: pre-checks `_has_existing_active_event` → skips
- CSV: checks exact `(org,email,churned_at)` → skips, but **not** active-event → duplicate active row

A harvester re-running daily against a stable CRM close date is idempotent via the 3-col index
**only if `churned_at` is stable**. If `churned_at` were detection-date, every run creates a new
row. This forces `churned_at = CRM close date`, not detection date.

## Finding 6 — `reason_code` has no CRM-shaped value

`CHURN_REASON_CODES` (`models/churn_event.py:30-37`) = `price | competitor | product_quality |
no_longer_needed | silent_churn | other`. Plain Python list, **enforced only in Pydantic — no DB
CHECK**. A CRM-sourced suggestion maps naturally to none of them. This matters beyond cosmetics:
the PRD's silence-proxy mitigation (`:450`) is "filter `silent_churn` at fit time", i.e.
reason_code is a training-filter dimension, so mapping CRM suggestions to `other` overloads a
bucket that is currently semantic.

---

## What is genuinely reusable (house pattern is a strong fit)

The **status-sync family** (jira/zendesk/asana) is a near-exact precedent for "opt-in per org,
off by default, poll-first, non-destructive first-poll baseline seed, manual Sync now":

- **Opt-in shape:** `status_sync_enabled = Column(Boolean, nullable=False, default=False,
  server_default=...)` + `status_mapping = Column(JSON, nullable=True)` on the integration row
  (`models/jira_integration.py:32-33`), `PATCH /api/v1/integrations/{p}/status-sync` behind
  `require_admin_or_owner`, toggle card `components/settings/JiraStatusSyncCard.tsx`.
- **Task shape:** Celery-free `_sync_x_org_body(integration_id, db, client=None)` core with an
  **injectable client** + thin `@shared_task` wrappers; fan-out filters
  `is_active.is_(True), status_sync_enabled.is_(True)`; `_persist_terminal_status` on a **fresh
  session**; `_decrypt` via `LLM_ENCRYPTION_KEY`, missing key → error, **no retry**.
- **Throttle taxonomy:** 429 → `Retry-After` sleep → `TransientError` → `self.retry`; 401/403 →
  recorded, no retry, **never auto-disconnects**.
- **Provider-agnostic core, mirrored:** `status_sync_core.py` exists **byte-identically** in
  backend-api and worker-service (the worker cannot import backend code). Extract-on-second-use,
  guarded by a characterization test.
- **Test style (matters for TDD):** real SQLite via the `db` fixture + a hand-written
  `FakeJiraClient` injected through the client seam. No Celery, no httpx, no patching.

Existing CRM assets to build on: `services/crm_integration_common.py` (`another_crm_active`,
`purge_crm_enrichment`) is the whole provider-agnostic seam today; the writeback cards
(`components/settings/HubSpotWritebackCard.tsx`) are the exact opt-in-toggle UI precedent;
`/customers` already has cohort selection + bulk dialogs to reuse for a review queue, and
`PotentialWinbackBanner` is a full-width suggestion-prompt precedent.

Beats: `sync-hubspot-daily` **03:15** UTC, `sync-salesforce-daily` **03:45** UTC
(`celery_app.py:218-229`). (`hubspot_sync.py:18` docstring claims 03:00 — stale.)

---

## Contradictions with the card / brief, stated plainly

1. **"Detect churn signals (Closed Lost / churned lifecycle stage)"** — not available; must be
   fetched anew, and Closed Lost ≠ churn without an opportunity-type/pipeline discriminator.
2. **"Go provider-agnostic via the existing `provider` discriminator on `crm_enrichment`"** —
   `crm_enrichment` is a **snapshot** table, `UNIQUE(organization_id, customer_email)`, no
   history, last-write-wins, and `provider` is a bare `String(50)` with no enum/CHECK
   (`models/crm_enrichment.py:39`). It cannot express dated churn transitions. The harvester
   likely reads the **provider API**, not `crm_enrichment`.
3. **"The rail is built and unused"** — half-true. The `auto_suggested` *value* exists; the
   *write path* does not (Finding 4), and 4 consumers will misread it (Finding 3).
4. **Rate limit** (PRD: max 500 churn events/day/org) — **not implemented anywhere**; bulk and
   CSV are unbounded. A harvester is exactly the mass-writer that limit was designed for.

## Open questions for the PRD (cannot be resolved from the code)

- **Q1 (biggest).** What counts as churn from a CRM? Options: lost **renewal** opp only; any
  Closed Lost on an **existing customer** (Account.Type = Customer); a custom lifecycle stage.
  Per-org configurable? What's the conservative default?
- **Q2.** Does confirming a suggestion **mutate** `source` (`auto_suggested → manual`) or write
  a new row? Mutating changes what the calibrator trains on and loses provenance.
- **Q3.** Do we fix the readiness-count bug (Finding 3.1) in this feature, or is it out of scope?
  Shipping the harvester without fixing it makes M5.0 dishonest.
- **Q4.** Should auto rows be suppressed from winback/timeline/cohorts until confirmed?
- **Q5.** New `reason_code` value (e.g. `crm_closed_lost`) vs. reuse `other`? New value touches
  a Pydantic-validated list + the frontend `ChurnReasonCode` union + filters.
- **Q6.** Where does the review queue live — org-level (`/customers`) or the existing
  system-admin `/system/churn-events` page (which is cross-org, read-only in v1)?
- **Q7.** Own beat or piggyback the existing daily CRM sync (03:15 / 03:45)?
