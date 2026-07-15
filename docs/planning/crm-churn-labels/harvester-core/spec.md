# Aspect spec — harvester-core

**Parent PRD:** `../prd.md` (M2, M4) · **Slug:** `harvester-core` · **Sequencing:** wave 2 (after data-model + provider-churn-fetch)

## Problem slice & outcome

`provider-churn-fetch` makes lost-renewal records reachable; `data-model` makes suggestions
storable. This aspect is the decision + wiring between them: given a closed-lost HubSpot deal or
Salesforce Opportunity, decide whether it is a churn suggestion and write it — **once** — into
`churn_label_suggestions`. An org with `churn_labels_enabled=True` and a configured renewal set
wakes to pending suggestions from the daily CRM sync it already runs; an org without that config
sees **nothing** (default-deny; R2). The discipline: **a guess must never reach the training set.**
This aspect writes suggestions only — it has no path to `customer_churn_events`.

## In scope

1. **Pure decision core** — `worker-service/src/services/churn_harvest_core.py`. Stdlib-only; MUST
   NOT import Celery, SQLAlchemy, FastAPI, httpx, or any client (mirrors `status_sync_core.py:1-8`).

   ```python
   SUGGESTION_DENY_REASONS = ("not_closed", "won", "discriminator_not_configured",
                              "no_discriminator", "unknown_customer")

   def decide_suggestion(
       *,
       is_closed: bool, is_won: bool,
       discriminator: str | None,            # SF Opportunity.Type / HubSpot deal pipeline id
       renewal_set: frozenset[str] | None,   # org's configured renewal types/pipelines
       customer_email: str | None,           # already lowercased by the adapter
       known_emails: frozenset[str],
   ) -> tuple[bool, str | None]:
       """(suggest, deny_reason). DEFAULT-DENY: suggest only when closed AND not won AND
       discriminator in renewal_set AND email in known_emails. Any None/unknown/unconfigured
       input -> (False, <reason>). Never raises."""
   ```

   Deny order is fixed and asserted so the logged reason is deterministic, in the tuple's order:
   `not_closed` → `won` → `discriminator_not_configured` (None/empty `renewal_set`) →
   `no_discriminator` (None/blank discriminator — R5) → `unknown_customer`. Matching against
   `renewal_set` is exact: **no regex, no normalization, no prefix match** on pipeline names (M2).

2. **Two thin adapters** — `worker-service/src/services/churn_harvest_adapters.py`. Pure,
   stdlib-only. `hubspot_deal_to_candidate(deal, contact_email)` and
   `salesforce_opportunity_to_candidate(opp, contact_email)` each return one shape —
   `{customer_email, external_opportunity_id, suggested_churned_at, evidence, is_closed, is_won,
   discriminator}` — or `None` when the record lacks an id or a usable close date.
   - `suggested_churned_at` = the **CRM close date** (`closedate` / `CloseDate`), ISO-8601 with
     `Z` → `+00:00` (reuse `hubspot_sync.py:239-244`). **Never the detection date** — stability is
     what makes re-harvest idempotent (understanding.md Finding 5). Unparseable → `None`, dropped.
   - `is_won`: HubSpot `dealstage == "closedwon"`; SF the `IsWon` boolean. `discriminator`: HubSpot
     `properties.pipeline`; SF `Type`. `evidence`: `{name, stage, type, amount, close_date,
     provider}` — what the reviewer sees.

3. **Wiring — no new beat.** Called from inside the existing `_sync_org(org_id, db, client)` of
   `hubspot_sync.py` / `salesforce_sync.py`, where `known_emails` is already built
   (`hubspot_sync.py:179-199`, `salesforce_sync.py:218-245`) and the live client + decrypted token
   are already held — under the existing `sync_hubspot_org` (03:15 UTC) / `sync_salesforce_org`
   (03:45 UTC) beats. Skipped unless `churn_labels_enabled` **and** a non-empty renewal set.

   ```python
   # worker-service/src/services/churn_suggestion_harvester.py
   def harvest_org_suggestions(
       org_id: int, db, client, *, provider: str,
       renewal_set: frozenset[str], known_emails: frozenset[str],
       cap: int = PER_RUN_SUGGESTION_CAP,
   ) -> dict:  # {"scanned","suggested","skipped_existing","denied","dropped_by_cap"}
   ```

   Celery-free, injectable `client`, caller owns the transaction — the `_sync_org` contract.
   Harvest must **not** fail enrichment: exception-wrapped, logged, recorded
   (`last_harvest_status='error'`), leaving the sync's `success` intact (R4).

4. **Idempotency + suppression.** Per candidate, before insert:
   - Look up `(organization_id, provider, external_opportunity_id)`. **Row exists → skip, in any
     status** — a `rejected` suggestion is never re-suggested, a `confirmed` one never duplicated.
     Existing rows are **not** updated; re-harvest is a no-op, not a refresh.
   - Skip when the customer already has an active `CustomerChurnEvent` — reuse
     `_has_existing_active_event` semantics (`routes/churn_events.py:74-88,148-150`:
     `org + email + recovered_at IS NULL`), reimplemented in the worker (cannot import backend).
   - Insert via pre-check + `IntegrityError` catch → skip. No `ON CONFLICT` (SQLite-safe, matching
     `_upsert_enrichment`). The DB UNIQUE is the guarantee; the pre-check is the fast path.

5. **Per-run cap, never silent.** `PER_RUN_SUGGESTION_CAP` (module constant, default 200). On hit:
   stop inserting, count the remainder, emit a **WARNING** naming `org_id`, `provider`, cap and
   `dropped_by_cap`, and return that count. House rule: **no silent caps**.

6. **Mirroring — decided: NO backend mirror.** `status_sync_core.py` is mirrored because *both*
   services apply status. Here only the worker harvests; the backend's review queue reads rows and
   never re-decides. So core + adapters live in **worker-service only**, with no parity test. If a
   backend caller ever needs `decide_suggestion`, mirror it byte-identically **then** —
   extract-on-second-use, not on speculation.

## Out of scope

- `churn_label_suggestions` table, model, migration, worker model mirror — `data-model`.
- Client methods / SOQL / `pipeline` property + enrichment characterization tests — `provider-churn-fetch` (M1).
- `churn_labels_enabled` / `churn_label_config` columns, PATCH + options endpoints, settings UI — `integration-config` (M3).
- Review queue, confirm/reject/bulk, **any** `CustomerChurnEvent` write — `review-queue` (M5).
- Readiness counting (M6), historical backfill (M7), docs (M8).

## Acceptance criteria (testable)

1. `decide_suggestion` → `(True, None)` only for closed + not-won + discriminator in `renewal_set`
   + email in `known_emails`. Pure asserts, no I/O, no fixtures.
2. Each deny path asserted with its exact reason, **R5 explicitly**: `discriminator=None` →
   `no_discriminator`; `renewal_set` None/empty → `discriminator_not_configured`; closed-lost deal
   for an unknown email → `unknown_customer`.
3. Adapters map a fixture HubSpot deal and SF Opportunity to identical-shaped dicts;
   `suggested_churned_at` equals the CRM close date and is **stable across two calls**. Missing or
   unparseable close date / missing id → `None`.
4. `harvest_org_suggestions` with a hand-written **Fake client** + real SQLite `db` fixture inserts
   N pending rows; **a second run inserts zero** (`scanned` > 0, `suggested == 0`).
5. A `rejected` existing suggestion is not re-suggested; a customer with an active
   `CustomerChurnEvent` is skipped; a **recovered** (`recovered_at` set) one is **not** skipped.
6. 250 candidates with `cap=200` → 200 rows, `dropped_by_cap == 50`, WARNING logged (`caplog`).
7. `churn_labels_enabled=False` (default) → zero suggestion rows and `_sync_org`'s enrichment
   result dict **unchanged** from the pre-change baseline.
8. A raising Fake client inside harvest leaves enrichment output intact and
   `last_sync_status == 'success'`.
9. **No `customer_churn_events` row is ever written by this aspect** — asserted directly (count
   before == count after) on the happy path.
10. Zero Celery, zero httpx, zero `patch` in this aspect's tests; worker suite green.

## Dependencies & sequencing

- **After** `data-model` (table + worker mirror) and `provider-churn-fetch` (sibling client methods
  returning closed-lost records with `pipeline` / `Type` / `IsWon`).
- **Before** `review-queue` (M5), which consumes the rows, and `backfill` (M7), which reuses
  `decide_suggestion` + the adapters unchanged in its own cancellable task.
- Config columns land in `integration-config` (M3); until then tests pass `renewal_set` directly —
  the harvester never reads config, it is handed a `frozenset`.
- **Signature deviation, flagged:** the CRM tasks use the older
  `_sync_x_org_body(task_self, integration_id)` shape (own session, no injectable client), unlike
  jira's `_sync_jira_org_body(integration_id, db, client=None)`. Do **not** refactor them here
  (blast radius, R4). Test at `_sync_org(org_id, db, client)` — already the injectable seam.

## Risks

- **R4 (regression) — the live one.** Harvest runs inside the load-bearing enrichment loop.
  Mitigation: additive call site, exception-isolated (AC 8), enrichment output characterized
  byte-identical (AC 7); never touch `_pick_renewal_deal` / `get_open_opportunities`.
- **R5 — null/custom `Type`/`pipeline`.** Default-deny, asserted (AC 2). The cost is silence, not
  false labels; that is the intended trade.
- **Sync duration.** Harvest adds closed-lost fetches to a 03:15/03:45 beat. The per-run cap bounds
  it; reuse the per-account memoization (`salesforce_sync.py:251-252`). If it still stalls the
  beat, that is the signal to split it out — not to raise the cap silently.
- **Deny reasons are counters, not rows.** "Why no suggestions?" gets a log aggregate, not
  per-record detail. Accepted for v1; R2's empty-state copy is the real answer.
