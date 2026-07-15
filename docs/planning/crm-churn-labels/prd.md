# PRD — CRM-Sourced Churn Labels (lost-renewal suggestions + operator review)

**Slug:** `crm-churn-labels`
**Branch:** `feat/crm-churn-labels`
**Type:** feat (freeform — no GitHub issue)
**Status:** Draft (pre-review-gate)
**Author:** `rereflect-begin-fast` pipeline, 2026-07-15
**Sources:** `docs/planning/_card/card.md` (brief), `docs/planning/_card/understanding.md`
(5-agent dig), `PRD-ADVANCED-CHURN-PREDICTION.md` §9, `AI-TRACKING.md` M3.1/M3.1b/M5.0/M5.3

---

## Problem Statement

Rereflect's stated killer feature is "churn prediction that actually works"
(`AI-TRACKING.md:5`). The honest version shipped in M4.1 is a **calibrated heuristic**, and the
roadmap's upgrade to a real per-org ML model (**M5.3**) is **data-gated at ~500 labels per org**
(`AI-TRACKING.md` M5.3; `config/readiness_thresholds.py:8` `CHURN_LABEL_TARGET = 500`).

**Today an org can only produce churn labels by hand.** The only two producers are the manual
"Mark as churned" dialog (`routes/churn_events.py:357`) and CSV import (`:256`). Hand-entry at
500 labels/org is not a path anyone walks. M5.3 is therefore blocked not on code, but on data —
and nothing in the product generates that data.

Meanwhile the org's CRM already knows who churned. `PRD-ADVANCED-CHURN-PREDICTION.md:469`
explicitly parked this:

> **External label sources** (Stripe webhook, HubSpot CRM, Segment). Future integration
> milestones (M3.1, M3.2).

Those milestones have since shipped — M3.1 HubSpot COMPLETE, M3.1b Salesforce COMPLETE
(2026-07-01), M3.2 usage COMPLETE (2026-06-29) — but nobody returned for the item they were
blocking. **This PRD returns for it.**

**Who feels it.** The self-host operator's CS/RevOps team, who already maintain churn truth in
their CRM and are asked to re-key it into Rereflect by hand; and every org whose churn
prediction stays a heuristic forever because the label gate is unreachable.

**Evidence it's real (file:line):**
- The deferral is written down: `PRD-ADVANCED-CHURN-PREDICTION.md:469`.
- The gate is real and surfaced to operators: `readiness_thresholds.py:8`,
  `routes/ai_readiness.py:149` (`churn_labels_ready`).
- The only label producers are manual: `routes/churn_events.py:190,256,357`.
- The `auto_suggested` source value has existed unused since M4.1
  (`models/churn_event.py:42`) — four calibration filters guard a producer that was never built
  (`tasks/churn_calibration.py:50,125`; `services/calibration_refit.py:64,191`).

### What the dig changed (do not skip)

The brief assumed the CRM churn signal was synced-but-unused. **It is neither.**

1. **The signal is actively discarded.** HubSpot filters `closedlost` out at
   `clients/hubspot.py:280-284` and again at `hubspot_sync.py:56-63`, so
   `crm_enrichment.deal_stage` can never hold it. Salesforce never fetches it —
   `...FROM Opportunity WHERE AccountId='...' AND IsClosed = false` (`clients/salesforce.py:298`);
   `IsWon` is never selected. Neither CRM has a native "churned" lifecycle value.
2. **Closed Lost ≠ churn.** A lost opportunity is usually a *prospect who never bought*, not a
   customer who left. Labelling those churned injects the false positives
   `PRD-ADVANCED-CHURN-PREDICTION.md:455` warns poison the model. Telling a lost **renewal**
   from a lost **new-business** deal needs `Opportunity.Type` (SF) / deal `pipeline` (HubSpot) —
   **neither is fetched**, and both are per-org CRM modelling with no portable default.

Both facts push the same way: **be conservative, be configured, and never let a guess reach the
training set.**

---

## Goals & Success Metrics

**Goal.** Make the ~500-label gate reachable for an org that keeps churn truth in its CRM,
**without** lowering label quality — every label that reaches the calibrator is still
human-confirmed.

> **Why backfill is must-have, not v2 (self-critique, folded in 2026-07-15).** Both the readiness
> report (`ai_readiness.py:74-79`) and the calibrator gate (`churn_calibration.py:50`) count
> **`CustomerChurnEvent` rows** — i.e. *actual churn events*. So the gate means ~500 real churns
> in one org. An org with 1,000 customers at 5% annual churn produces ~50/year: **forward-only
> harvesting would take ~10 years to reach 500**. Forward-only replaces typing with reviewing and
> does **not** meet this PRD's own goal. The volume lives in the CRM's *history* — years of
> closed-lost renewals already sitting there, harvestable in one bounded pass. Backfill (M7) is
> therefore a must-have, not a nice-to-have.

| Metric | Target | Measured by |
|---|---|---|
| Suggestion precision (confirmed ÷ reviewed) | ≥ 0.8 on a configured org | `churn_label_suggestions.status` counts |
| Labels produced per review-minute vs. hand-entry | ≥ 10× | review queue is bulk; hand-entry is 1-at-a-time |
| False labels reaching the calibrator | **0 by construction** | pending suggestions never enter `customer_churn_events` |
| Readiness honesty | `churn_labels_ready` counts only trainable labels | `routes/ai_readiness.py` |

**Non-metrics (honesty, per house style).** We do **not** claim improved churn AUC/accuracy in
v1. This PRD produces *labels*; whether more labels improve the model is M5.3's question, and
asserting it now would be exactly the unearned confidence the churn PRD was written to avoid.
We also do not promise any org reaches 500 — an org's real lost-renewal count is whatever it is.

---

## User Personas & Scenarios

> **Evidence tag: `assumed`.** Rereflect is self-hosted OSS with no telemetry. We cannot verify
> that any org has a CRM connected, has lost renewals, or models an opportunity-type
> discriminator. These personas are **hypothesized from the product's ICP, not validated with
> users.** The first configured org is the experiment that tests them.

- **CS/RevOps lead (org admin).** Connects HubSpot, opens Settings → Integrations → HubSpot,
  enables "Suggest churn labels from lost renewals", picks their `Renewals` pipeline from a live
  list. Next morning: "47 CRM churn suggestions to review" on `/customers`. Skims the evidence
  (deal name, close date, amount), bulk-confirms 41, rejects 6 (a lost upsell, a duplicate).
  Those 41 become real labels the calibrator trains on.
- **Self-host operator evaluating M5.3 readiness.** Opens Settings → AI → Readiness. Sees
  "312 trainable labels / 500" **and separately** "47 CRM suggestions awaiting review" — and is
  never told they're ready on labels the fit would reject.
- **Org that has not configured it.** Sees nothing. No suggestions, no noise, no behaviour
  change anywhere. Default off.

---

## Requirements

### Must-have

**M1 — Provider churn-signal fetch (both providers).**
Fetch lost-renewal opportunities/deals without disturbing the existing enrichment path.
- Salesforce: new query — `SELECT Id, Name, StageName, Amount, CloseDate, IsClosed, IsWon, Type
  FROM Opportunity WHERE AccountId = '...' AND IsClosed = true AND IsWon = false`. Must **not**
  alter `get_open_opportunities` (the renewal-proxy enrichment depends on `IsClosed = false`);
  add a sibling method.
- HubSpot: `closedlost` is already in the batch-read response and dropped by
  `clients/hubspot.py:280`. Add a sibling accessor that keeps it, and request `pipeline` in the
  properties list (`hubspot.py:252`). Must **not** change `_pick_renewal_deal`'s exclusion
  (enrichment depends on it).
- Both: **characterization-test the existing enrichment output first** — byte-identical before
  and after (house rule: the CRM provider generalization was locked this way).

**M2 — Conservative, config-driven churn rule (default-deny).**
A suggestion is produced **only** when: the opportunity/deal is closed **and** not won, **and**
its `Type`/`pipeline` is in the org's configured renewal set, **and** the contact email already
matches a known Rereflect customer (reuse the existing `known_emails` match at
`hubspot_sync.py:179-199` / `salesforce_sync.py:218-245`).
- Unconfigured, unknown, or unrecognised discriminator → **no suggestion**. No heuristic, no
  regex guess at pipeline names.
- `suggested_churned_at` = the **CRM close date** (never detection date — stability is what
  makes re-harvest idempotent).

**M3 — Per-org opt-in + configuration.**
Mirrors the shipped status-sync opt-in shape (`models/jira_integration.py:32-33`).
- New columns on **both** `hubspot_integrations` and `salesforce_integrations`:
  `churn_labels_enabled` (Boolean, NOT NULL, default **False**, server_default) and
  `churn_label_config` (JSON, nullable) holding the renewal pipeline ids / opportunity types.
- `PATCH /api/v1/integrations/{hubspot|salesforce}/churn-labels`, `require_admin_or_owner`.
- A read endpoint to populate the picker from live CRM metadata (HubSpot
  `GET /crm/v3/pipelines/deals`; Salesforce `Opportunity.Type` picklist via describe — the
  writeback validators already do describe calls, see `salesforce_writeback_validation.py`).
- Settings UI card per provider, copying `components/settings/HubSpotWritebackCard.tsx`
  (Switch + config input locked while enabled + status/error copy maps + stats grid).

**M4 — Suggestions store + harvester (provider-agnostic core, two adapters).**
- New table `churn_label_suggestions` — see Data Model. **Pending suggestions never enter
  `customer_churn_events`**, so no existing consumer changes behaviour (blast radius zero).
- Harvest runs **inside the existing per-org sync tasks** (`sync_hubspot_org` at 03:15,
  `sync_salesforce_org` at 03:45) — they already hold the decrypted token, the live client, and
  the `known_emails` set. **No new beat.** Guarded by `churn_labels_enabled`.
- Core is Celery-free with an **injectable client**, mirrored into worker + backend per house
  rule (the worker cannot import backend code); two thin adapters normalize each provider into
  one suggestion shape.
- Idempotent: re-harvesting the same lost renewal must not duplicate. Unique
  `(organization_id, provider, external_opportunity_id)`.
- A **rejected** suggestion is never re-suggested. A suggestion whose customer already has an
  active `CustomerChurnEvent` is not suggested (reuse `_has_existing_active_event` semantics).

**M5 — Review queue (org-level).**
- `GET /api/v1/customers/churn-suggestions` (paginated, filterable by status) —
  `require_admin_or_owner`, org-scoped.
- `POST .../churn-suggestions/{id}/confirm` → writes a real
  `CustomerChurnEvent(source='manual', marked_by_user_id=<confirming user>)` through the existing
  service path, sets `status='confirmed'`. **A human confirmed it, so it trains** — that is the
  entire point of the queue.
- `POST .../churn-suggestions/{id}/reject` → `status='rejected'`, no event written.
- Bulk confirm/reject over the existing `Cohort` contract shape used by `/customers` bulk
  actions.
- **Collision handling (non-negotiable).** `UNIQUE(organization_id, customer_email, churned_at)`
  (`models/churn_event.py:87-96`) means confirming a suggestion for a customer already
  hand-marked at the same close date raises `IntegrityError`. Confirm must pre-check for an
  existing active event **and** catch the integrity error → resolve to `skipped`, never a 500 and
  never a partial-bulk abort.
- **Bulk result shape.** Reuse the shipped public-bulk contract exactly (house precedent,
  `docs/planning/public-api-crud-v3/`): `{matched, confirmed, skipped, results: [{id, status:
  confirmed|skipped|error, reason?}]}` in deduped input order. Bulk is best-effort per item; one
  collision must not roll back the other 40.
- UI: StatCard on `/customers` → review view; confirm reuses `MarkAsChurnedDialog`'s
  reason-code requirement (`reason_code` is required — the operator states *why*, so no new
  reason-code enum value is needed).

**M6 — Readiness honesty.**
`routes/ai_readiness.py` must count only labels the calibrator will actually train on, and
report pending suggestions as a **separate** number:
- `churn_labels_ready = trainable >= CHURN_LABEL_TARGET`, where `trainable` excludes
  `source = 'auto_suggested'` (defensive: aligns the report with the four calibration filters
  even though this PRD writes no auto rows).
- Surface `pending_suggestions` separately on the Readiness card. Never let a suggestion count
  toward readiness.

**M7 — Bounded historical backfill (the volume driver).**
Forward-only harvesting cannot meet the goal (see Goals). On enable, the operator can run a
backfill over a chosen window (default e.g. 24 months, explicit max).
- Same conservative rule, same suggestions table, same review queue — backfill produces
  *suggestions*, never labels. It is a volume change, not a trust change.
- Paginated/throttled against both providers (SF `queryMore`, HubSpot paging); respects the 429 →
  `Retry-After` taxonomy; resumable and idempotent via
  `UNIQUE(organization_id, provider, external_opportunity_id)`.
- Explicit progress + a **logged, surfaced count of anything dropped by the cap** (house rule: no
  silent caps).
- Run as a distinct, cancellable task — **not** inside the daily sync (a multi-year page-through
  must not stall the 03:15 enrichment beat).

**M8 — Docs + tracking (repo convention).**
Every recent feature ships `docs(...)` commits; this one must too: `docs/SELF_HOSTING.md`
(operator setup: which pipeline/type config, what backfill does), `CHANGELOG.md`,
`AI-TRACKING.md` (new capability row + the M5.3 label-supply note), `README.md` and the landing
page's integration copy where CRM capabilities are listed.

### Should-have

- `evidence` JSON on each suggestion (deal/opp id, name, stage, type, amount, close date) shown
  in the review row — the operator cannot confirm responsibly without seeing why.
- Per-run suggestion cap + a logged count of what was dropped (house rule: **no silent caps**).
- `last_harvest_at` / `last_harvest_status` / `last_harvest_error` on the integration row,
  surfaced on the settings card like the status-sync cards do.

### Nice-to-have (explicitly deferrable)

- HubSpot custom **lifecycle-stage** churn marker as a second signal (portal-specific).
- Auto-confirm above an operator-set confidence rule. (Deliberately not v1 — it re-introduces
  exactly the unreviewed-label risk the queue exists to remove.)
- Suggestion → `recovered_at` reconciliation (a Closed Lost renewal later reopened).
- *(Historical backfill was here; promoted to must-have M7 after the self-critique showed
  forward-only cannot meet the goal.)*

---

## Technical Considerations

**Rough size.** ~2–3 weeks equivalent: 8 milestones across 3 services, 2 providers, 1 new table +
migration, 1 new backfill task, ~6 endpoints, 2 settings cards + 1 review view. M1/M2/M4/M7
(worker + core) are the bulk; M3/M5 (routes + UI) follow shipped patterns closely. Sequencing is
dependency-led — see aspect decomposition.

**Services touched.** `services/worker-service` (clients, sync tasks, harvester core),
`services/backend-api` (model, migration, routes, readiness), `services/frontend-web`
(settings cards, review queue). `analysis-engine` untouched.

**Multi-tenancy.** Every query scoped by `organization_id`; suggestions are org-scoped and the
review endpoints are `require_admin_or_owner`. Note the existing churn-event routes have **no
role dependency** (any member can write labels) — we do **not** replicate that; new routes are
admin/owner.

**The worker cannot import backend code.** `churn_label_suggestions` must be mirrored (no FK) in
`worker-service/src/models/__init__.py`, and the harvester core mirrored byte-identically, as
`status_sync_core.py` already is in both services. A parity test exists for `CrmEnrichment` —
copy that pattern.

**Migrations — single head, `e6f7a8b9c0d1`.** The new revision chains off
**`e6f7a8b9c0d1`** (urgency classifier mode), which is the sole current head. The plan must
**re-run `alembic heads` at write time** and stop to re-plan if it returns more than one.

> **Correction (2026-07-15).** An earlier draft of this PRD claimed a pre-existing **two-head
> fork** (`c4d5e6f7a8b9` + `e6f7a8b9c0d1`) and told the plan to consider a merge revision. **That
> was wrong** — it came from a file-scraping heuristic that mis-parsed
> `d5e6f7a8b9c0:24` (`down_revision = "c4d5e6f7a8b9"   # VERIFIED with ...`), keeping the
> trailing comment as part of the value so `c4d5e6f7a8b9` never matched and falsely looked like a
> head. `c4d5e6f7a8b9` is an **ancestor** (`c4d5e6f7a8b9 → d5e6f7a8b9c0 → f1a2b3c4d5e6 → … →
> e6f7a8b9c0d1`). Acting on the false claim would have **fabricated the fork it purported to
> fix**. Caught by the `data-model` dig. Fittingly, `c4d5e6f7a8b9`'s own docstring (lines 9-17)
> warns about exactly this failure mode: trusting a plan's assumed head instead of running
> `alembic heads`. **Lesson for the plan: run the tool, don't grep the files.**

**Encryption.** Reuses `LLM_ENCRYPTION_KEY` via each task's local `_decrypt`. Missing key →
`{"status":"error","reason":"missing_encryption_key"}`, **no retry** (existing convention).

**Throttle/error taxonomy.** Reuse the shipped shape: 429 → `Retry-After` sleep → transient →
`self.retry`; 401/403 → recorded, no retry, **never auto-disconnect** (`is_active` untouched).

**One CRM per org** is already guarded (`crm_integration_common.py:18`), so in practice only one
adapter is live per org — but the core stays provider-agnostic because the guard is
application-level with a documented TOCTOU race.

### API Contracts (summary)

| Method | Path | Auth | Purpose |
|---|---|---|---|
| PATCH | `/api/v1/integrations/{provider}/churn-labels` | admin/owner | `{enabled, config}` |
| GET | `/api/v1/integrations/{provider}/churn-labels/options` | admin/owner | live pipelines / opp types for the picker |
| GET | `/api/v1/customers/churn-suggestions` | admin/owner | paginated, `?status=pending` |
| POST | `/api/v1/customers/churn-suggestions/{id}/confirm` | admin/owner | → `CustomerChurnEvent(source='manual')` |
| POST | `/api/v1/customers/churn-suggestions/{id}/reject` | admin/owner | → `status='rejected'` |
| POST | `/api/v1/customers/churn-suggestions/bulk` | admin/owner | bulk confirm/reject over a `Cohort` |

### Data Model

```sql
churn_label_suggestions
  id                        INTEGER PK
  organization_id           INTEGER NOT NULL FK organizations(id) ON DELETE CASCADE
  customer_email            VARCHAR(255) NOT NULL          -- normalized lowercase
  provider                  VARCHAR(50)  NOT NULL          -- 'hubspot' | 'salesforce'
  external_opportunity_id   VARCHAR(64)  NOT NULL          -- SF Opportunity.Id / HubSpot deal id
  suggested_churned_at      TIMESTAMP    NOT NULL          -- CRM close date (stable => idempotent)
  evidence                  JSON         NULL              -- {name, stage, type, amount, ...}
  status                    VARCHAR(20)  NOT NULL DEFAULT 'pending'  -- pending|confirmed|rejected
  reviewed_by_user_id       INTEGER      NULL FK users(id) ON DELETE SET NULL
  reviewed_at               TIMESTAMP    NULL
  churn_event_id            INTEGER      NULL FK customer_churn_events(id) ON DELETE SET NULL
  created_at                TIMESTAMP    NOT NULL DEFAULT NOW()
  updated_at                TIMESTAMP    NOT NULL DEFAULT NOW()

  UNIQUE (organization_id, provider, external_opportunity_id)   -- idempotent re-harvest
  INDEX  (organization_id, status)
  INDEX  (organization_id, customer_email)
```

Enum values follow house convention: module-level Python lists validated in Pydantic, **no DB
CHECK** (matches `CHURN_EVENT_SOURCES` / `CHURN_REASON_CODES` at `models/churn_event.py:30-43`).

---

## Risks & Open Questions

- **R1 — Volume may still not reach 500.** Lost *renewals* are rarer than lost deals; the
  conservative rule is precise but low-yield, and v1 harvests forward only. **Mitigation:**
  honest empty/low states; historical backfill is the named v2 that actually moves volume. We do
  not claim any org reaches the gate.
- **R2 — Config burden is real.** Default-deny means zero value until the operator names their
  renewal pipelines. **Mitigation:** live picker (not free-text), explicit empty-state copy
  stating why there are no suggestions.
- **R3 — A lost renewal is not always a churn.** Downgrades, partial non-renewals, and
  re-signed-later all read as lost. **Mitigation:** that is precisely what human confirm is for;
  we never auto-confirm.
- **R4 — Touching the shared CRM clients could regress enrichment.** `_pick_renewal_deal` /
  `get_open_opportunities` are load-bearing for the shipped `crm_component`.
  **Mitigation:** characterization-test enrichment output first; add sibling methods, never
  mutate the existing filters.
- **R5 — SF `Type` and HubSpot `pipeline` are customizable and may be null.** Null/unknown →
  default-deny (no suggestion). Explicitly asserted in tests.
- **R6 — ~~Two alembic heads pre-exist~~ (withdrawn — the claim was false).** There is exactly
  **one** head, `e6f7a8b9c0d1`; chain off it. See the Correction note in Technical
  Considerations. Residual risk is only the ordinary one: another feature merges a migration
  first, so **re-run `alembic heads` at write time**.
- **R7 — Existing dedup is inconsistent across the three churn-event write paths**
  (`understanding.md` Finding 5). Confirm writes through one path only; we neither fix nor
  inherit the inconsistency, but the confirm path must pre-check for an existing active event.
- **R8 — the 500-label gate may itself be a pre-pivot artifact (open, deliberately not blocking).**
  The threshold comes from `PRD-ADVANCED-CHURN-PREDICTION.md:463` — "labels ≥ 500/org **or ≥ 5,000
  globally**". The "globally" half is meaningless post-OSS-pivot: single-tenant self-hosting has no
  cross-org pool (the same reason M4.3 benchmarks were dropped). So the number was calibrated for a
  hosted multi-tenant product that no longer exists, and nobody has re-derived what a per-org
  logistic/GBM churn model actually needs single-tenant (100? 200?).
  **Why this does not block:** more human-confirmed labels improve any threshold, so this feature's
  value is threshold-independent — and M7 backfill makes 500 reachable for a mid-size org rather
  than a decade away. **But** if the honest answer is that 500 is wrong, then re-deriving it is
  higher-leverage than feeding it. *Recommended follow-up: a separate M5.3-scoped investigation to
  re-derive the single-tenant threshold. Do not silently keep quoting 500.*
- **(resolved) Where do suggestions live?** Separate table — blast radius zero.
- **(resolved) Does confirming mutate `source`?** No. Confirm writes a fresh
  `CustomerChurnEvent(source='manual')`; the suggestion keeps provenance via `churn_event_id`.
- **(resolved) New `reason_code` value?** No. The confirm dialog requires the operator to pick an
  existing reason code.
- **(resolved) Own beat?** No. Harvest runs inside the existing per-org CRM sync tasks.
- **(resolved) Readiness fix in scope?** Yes — M6.

---

## Out of Scope

- **Writing `source='auto_suggested'` rows.** The chosen design makes the rail unnecessary; it
  stays unused. (Noted honestly: this contradicts the card's "the rail is built and unused"
  framing — the rail's *design* assumed unreviewed labels land in the table, which we reject.)
- **The system-admin toggle to train on auto labels** promised at
  `PRD-ADVANCED-CHURN-PREDICTION.md:457` — moot under this design.
- **Usage/Segment-derived churn labels.** Blocked: `customer_usage` keeps only current 7d/30d
  counters with no history (`customer-360-unified-timeline` R1, "we will not fabricate a drop
  event").
- **Stripe-webhook labels.** Dead post-OSS-pivot; there is no Stripe billing.
- **The real ML churn model (M5.3).** This PRD produces labels; it does not train anything.
- **Fixing the missing 500/day churn-event rate limit** (`PRD-ADVANCED-CHURN-PREDICTION.md:456`,
  never implemented). Pre-existing; our writes are human-gated and capped per run.
- **Fixing the pre-existing churn-event route gaps** — no role dependency, inconsistent dedup,
  `recover`/`delete` not invalidating probability, `RecoverRequest.note` silently discarded.
  Logged in `understanding.md`, not fixed here.
- **Historical backfill on first enable**, auto-confirm, lifecycle-stage signal, winback
  reconciliation — all named v2 above.
- **Claiming churn accuracy improvement.** No metric claims.
