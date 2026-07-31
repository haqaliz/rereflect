# Aspect Spec — `tenancy-discriminator`

**Feature:** `intercom-selfhost-ingestion`
**PRD:** `../prd.md` (requirement **R3**; risk **K1**)
**Date:** 2026-07-31
**Size:** S (one function, one `or_`) — **but the highest-risk aspect in the feature**
**Depends on:** `token-paste-connect` (the table it must match against)

---

## Problem slice

`token-paste-connect` shipped a working connect flow that **ingests nothing**.

`_find_matching_sources` (`services/worker-service/src/tasks/source_events.py`) resolves an
inbound Intercom event to feedback sources by matching the payload's `app_id` against
`Integration.config["workspace_id"]` — the **OAuth** row. A token-paste org has no such
row, and its auto-provisioned source carries `integration_id=None`, so it matches neither
the OAuth filter nor anything else. Every delivery returns `no_sources`.

Until this lands, the token-paste path has exactly the property this whole feature exists
to eliminate: **it looks connected and produces nothing.**

## Why this aspect is handled separately and carefully

This is the function the P0 `intercom-webhook-unauthenticated-cross-org-write` fix
hardened. Before that fix, a payload without `app_id` fell through to a query filtered only
by `source_type` and `is_active` — matching **every active Intercom source in every
organization on the instance**.

This aspect **widens** that function to a second credential source. Widening the code that
was the site of an unauthenticated cross-tenant write is not a routine edit:

- the existing guarantees are **characterized first**, in tests that would fail if the
  widening regressed them;
- the widening is additive (`or_` of two narrow clauses), never a relaxation of the
  outer filter;
- a missing or empty `workspace_id` must **still** return `[]` — before either lookup runs.

## In scope

Rewrite the `intercom` branch of `_find_matching_sources` to match **either**:

1. **OAuth** — `Integration.type == "intercom"`, `is_active`, `config["workspace_id"] == workspace_id`
   → filter `FeedbackSource.integration_id.in_(...)` (unchanged semantics), **or**
2. **Token-paste** — `IntercomIntegration.workspace_id == workspace_id`, `is_active`
   → filter `FeedbackSource.organization_id.in_(...)`, mirroring the Zendesk branch shape.

If neither yields a match, return `[]`.

## Out of scope

- The Slack / email / webhook / Zendesk branches. Untouched, and characterization tests
  prove it.
- The pull path (`pull-sync`) — it will call this same function, which is precisely why it
  must be correct first.
- Deduplicating the two credential paths (D4 keeps both).

## Acceptance criteria

| # | Criterion | Why |
|---|---|---|
| C1 | Token-paste org: event with its `workspace_id` resolves to that org's source | The whole point |
| C2 | OAuth org: existing behaviour **byte-identical** | Characterization; no regression |
| C3 | Missing `workspace_id` → `[]` | The P0 guarantee, re-pinned |
| C4 | Empty-string `workspace_id` → `[]` | `""` is the OAuth callback's stored default — `not x`, not `is None` |
| C5 | Unknown `workspace_id` → `[]` | No fall-through |
| C6 | Org A's event never returns org B's sources, in any combination of the two paths | The cross-tenant guarantee |
| C7 | Inactive `IntercomIntegration` does not match | Disconnect must actually stop ingestion |
| C8 | Inactive OAuth `Integration` does not match | Existing behaviour, re-pinned |
| C9 | Slack / email / webhook / Zendesk branches unchanged | Blast-radius containment |
| C10 | End-to-end: token-paste org + `process_source_event` → a `FeedbackItem` | Proves the feature works, not just the query |

## Known and accepted semantics

Two organizations on one instance that connect **the same** Intercom workspace will both
receive its events. That is pre-existing for the OAuth path and identical to how Zendesk
treats a shared subdomain (`source_events.py`, Zendesk branch). It is a property of
workspace-keyed tenancy, not a defect introduced here — **documented by a test** so the
next reader does not mistake it for one.

## Risks

| Risk | Mitigation |
|---|---|
| The `or_` widens beyond the two intended clauses | Both clauses are `IN` over id lists already narrowed by `workspace_id`; C6 tests the combination directly |
| A token-paste org's filter matches sources it should not own | `organization_id` scoping is strictly narrower than the org itself; identical to Zendesk |
| Someone later "simplifies" the empty-string check to `is None` | C4 exists precisely to fail if they do |
