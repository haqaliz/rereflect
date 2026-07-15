# Aspect spec — provider-churn-fetch

**Parent PRD:** `../prd.md` (M1) · **Slug:** `provider-churn-fetch` · **Sequencing:** wave 1

## Problem slice & outcome

Neither CRM client can see a lost renewal today. HubSpot fetches `closedlost` and throws it away
(`clients/hubspot.py:280-284`); Salesforce excludes it at the API (`clients/salesforce.py:298-301`,
`IsClosed = false`) and never selects `IsWon`. The discriminator that separates a lost *renewal*
(churn) from a lost *new-business* deal (not churn) is unfetched on both sides: SF
`Opportunity.Type`, HubSpot deal `pipeline` (`hubspot.py:252` requests only
`dealname, dealstage, amount, closedate`).

**Outcome:** both clients expose sibling read methods for lost-renewal data and for the CRM
metadata a config picker needs — with the shipped enrichment path provably unchanged. This aspect
ships **client methods only**: no rule, no table, no task, no config, no UI.

## In scope

1. **`SalesforceClient.get_lost_opportunities(account_id: str) -> list[dict]`** — new sibling of
   `get_open_opportunities`. Calls `self._validate_sf_id(account_id)` first (`_SFID_RE`,
   `salesforce.py:43,238-249`) so a malformed id raises `SalesforceQueryError` with **no HTTP
   call**. Issues exactly:
   `SELECT Id, Name, StageName, Amount, CloseDate, IsClosed, IsWon, Type FROM Opportunity WHERE AccountId = '<id>' AND IsClosed = true AND IsWon = false`
   Returns `self.query(soql)` records verbatim (no client-side filtering, no normalization).
2. **`SalesforceClient.get_opportunity_type_values() -> list[dict]`** — `GET
   /services/data/{api_version}/sobjects/Opportunity/describe` via the existing bearer +
   401-refresh-once `_get` pattern; returns the `picklistValues` of the `Type` field
   (`[{"label","value","active"}, ...]`), `[]` when the field is absent or has no picklist.
   Describe-shape precedent: `backend-api/src/services/salesforce_writeback_validation.py:76-114`
   (`data["fields"]` → match on `name`).
3. **HubSpot: extract the unfiltered fetch.** Split `get_open_deals_for_company` (`hubspot.py:189`)
   into a private `_fetch_deals_for_company(company_id) -> list[dict]` holding Step 1 (paged
   associations) + Step 2 (batch read) **unchanged**, and keep `get_open_deals_for_company` as
   `_fetch_deals_for_company(...)` + the **existing, untouched** Step-3 `closed_stages` filter
   (`:280-284`).
4. **`HubSpotClient.get_closed_lost_deals_for_company(company_id: str) -> list[dict]`** — sibling
   accessor: `_fetch_deals_for_company(...)` filtered to `properties.dealstage == "closedlost"`.
   Retains what the open-deal path drops. Returns raw deal dicts.
5. **Add `pipeline` to the shared properties list** (`hubspot.py:252`) →
   `["dealname", "dealstage", "amount", "closedate", "pipeline"]`. Both accessors get it; the
   enrichment path ignores the extra key (locked by AC-1).
6. **`HubSpotClient.list_deal_pipelines() -> list[dict]`** — `GET /crm/v3/pipelines/deals`, returns
   `results` (`[{"id","label","stages":[...]}, ...]`), `[]` on 404.
7. **Error taxonomy on every new call** — reuse the shipped shape verbatim, no new exception types:
   429 → `int(resp.headers.get("Retry-After", "10"))` → `time.sleep` → `HubSpotTransientError` /
   `SalesforceTransientError`; 5xx → transient, **no sleep**; 403 → `HubSpotScopeError` /
   `SalesforceScopeError`; 401 (SF) → refresh once, then `SalesforceAuthError`; 404 → `[]`/`None`
   per method above. Callers own `self.retry`; clients never retry Celery-side and **never**
   touch `is_active`.
8. **Tokens never logged** — no new log line may interpolate a token; `repr` stays token-free.

## Out of scope

- Any change to `get_open_opportunities`, to `_pick_renewal_deal` (`tasks/hubspot_sync.py:56-63`),
  or to the `closed_stages` set itself.
- The churn rule / default-deny config matching (M2), `churn_labels_enabled` + `churn_label_config`
  columns and the picker endpoints/UI (M3), the suggestions table, harvester and adapters (M4),
  review queue (M5), readiness (M6), backfill paging & `queryMore` (M7).
- Mirroring these clients into backend-api. The worker owns them; the M3 options endpoint decides
  its own transport.
- Normalizing provider payloads into a suggestion shape — that is M4's adapter seam.

## Acceptance criteria (testable)

- **AC-1 (characterization lock, gate on everything else).** Before any production edit, tests pin
  the **existing** enrichment output byte-identical: for a fixed fake payload containing
  `closedwon` + `closedlost` + open deals, `get_open_deals_for_company` returns exactly the same
  list (same order, same dicts) before and after; `_pick_renewal_deal` picks the same deal; the
  `crm_enrichment` row written by the sync task (`deal_stage`, `deal_amount`, `deal_close_date`,
  `deal_name`) is field-identical. Same lock on the Salesforce side for `get_open_opportunities`
  (SOQL string and returned records unchanged). House precedent: the CRM provider generalization
  shipped with exactly this lock.
- **AC-2.** `get_lost_opportunities` emits the SOQL in §1 **character-for-character** (asserted on
  the captured query string), including `IsWon` and `Type` in the SELECT and both
  `IsClosed = true AND IsWon = false` predicates.
- **AC-3.** `get_lost_opportunities("'; DROP--")` (and `""`, and a 14-char id) raises
  `SalesforceQueryError` and issues **zero** HTTP requests.
- **AC-4.** `get_closed_lost_deals_for_company` returns the `closedlost` deals for the same fake
  payload where `get_open_deals_for_company` returns none of them — the two are disjoint over
  `closedlost`, and the open path's result is unchanged by AC-1.
- **AC-5.** Both HubSpot deal accessors request `pipeline` (asserted on the batch-read body), and
  the returned deal dicts expose `properties.pipeline`; a deal whose `pipeline` is missing or
  `None` is still returned unaltered — the client never filters on it (default-deny is M2's job,
  PRD R5).
- **AC-6.** `list_deal_pipelines` returns parsed `results`; `get_opportunity_type_values` returns
  `Type`'s `picklistValues`, and `[]` when `Type` is absent from the describe response.
- **AC-7 (taxonomy).** Per new method: 429 with `Retry-After: 7` sleeps 7 and raises the transient
  error; 429 without the header defaults to 10; 500/503 raise transient **without** sleeping; 403
  raises the scope error; SF 401 refreshes once then raises `SalesforceAuthError`. No new method
  mutates `is_active`.
- **AC-8.** No token substring appears in any captured log record or in `repr(client)`.

**Test style.** Strict TDD, tests first. Client-level tests follow the cited precedent
`services/worker-service/tests/test_jira_client_worker.py` (stubbed transport, response objects
built by a local `_make_resp` helper) — extend `test_hubspot_client.py` / `test_salesforce_client.py`.
The AC-1 sync-level lock uses the house seam instead: a hand-written Fake client injected through
the existing client seam plus the real SQLite `db` fixture — no Celery, no httpx, no patching of
production code.

## Dependencies & sequencing

**Wave 1 — nothing blocks it.** No migration, no new table, no config column; the pre-existing
2-head alembic fork (PRD R6) does not touch this aspect. Every later aspect depends on it: M2's
rule reads `Type`/`pipeline`, M3's picker calls `list_deal_pipelines` /
`get_opportunity_type_values`, M4's adapters call the two lost-* accessors, M7 extends them with
paging. Merge order: AC-1 lands and is green **before** any production edit in this aspect.

## Risks

- **R4 (PRD) — regressing enrichment.** The `crm_component` is load-bearing and shipped. Mitigated
  by AC-1 as a hard gate and by sibling-only methods; the only edit to a shipped code path is the
  §3 extraction plus one added property. If AC-1 cannot be made green first, stop.
- **Extraction is a real refactor, not a no-op.** `_fetch_deals_for_company` moves ~90 lines of
  paging/429 handling. Move verbatim; no behaviour change in the same commit as the move.
- **The extra `pipeline` property widens the enrichment response.** Harmless only because the sync
  reads named keys; AC-1 + AC-5 assert it. Do not let it reach `crm_enrichment`.
- **R5 (PRD) — `Type`/`pipeline` are org-customizable and nullable.** This aspect deliberately does
  not interpret them; AC-5 pins pass-through so the default-deny decision stays in M2.
- **Describe/pipelines calls may 403 on a narrow-scoped connected app.** Surfaces as the shipped
  scope error; the picker aspect renders it, this one only classifies it.
