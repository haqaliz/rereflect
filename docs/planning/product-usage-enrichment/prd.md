# PRD — Product Usage Enrichment

**Status:** Draft (pre review-gate)
**Slug:** `product-usage-enrichment`
**Type:** feat (freeform; no GitHub issue)
**Branch:** `feat/product-usage-enrichment`
**Roadmap:** AI-TRACKING.md **M3.2 — Segment Product Usage Integration** (pending); DEV-TRACKING.md integration backlog.
**Source artifacts:** `docs/planning/_card/card.md`, `docs/planning/_card/understanding.md` (Phase 2 dig).

---

## Problem Statement

Rereflect's stated killer feature is "churn prediction that actually works," but the prediction has **no product-usage signal** — the single most predictive leading indicator of SaaS churn (a customer who stops logging in is churning, regardless of whether they file feedback).

Evidence from the code (Phase 2 dig):
- The customer health score has 4 components; the only usage-*sounding* one, "frequency" (`health_score_service.py:435-471`), actually measures **feedback complaint cadence**, not product usage.
- The 9-factor churn scorer (`worker-service/src/tasks/analysis.py:566-833`) likewise has a `feedback_frequency` factor — again feedback cadence.
- The customers list "Last Active" column is `last_feedback_at` (`customers/page.tsx:304`) — feedback-derived, not product activity.

So a customer who has gone silent in the product but hasn't filed feedback looks **neutral/healthy** today. That is exactly the silent-churner the product claims to catch.

**Who has the problem:** the self-hosted operator (CS lead / founder) running Rereflect who wants health scores and churn risk to reflect real engagement, not just complaint volume.

## Goals & Success Metrics

**Goal:** Let an operator feed per-customer product-usage events into Rereflect and have those events (a) visible on the Customer 360 profile and (b) optionally factored into the health score — without changing any existing org's scores until they opt in.

| Metric | Target |
|---|---|
| Usage events ingested → reflected on customer profile | An `identify`/`track` POST appears in the customer's usage rollup within one Celery cycle |
| Zero-surprise upgrade | With default usage weight = 0, every existing customer's `health_score` is **byte-for-byte unchanged** after migration (verifiable test) |
| Opt-in activation | An operator can set a non-zero usage weight (5 weights sum to 100) and see usage move the score |
| No-usage degradation | Customers/orgs with no usage events get a neutral usage component (50) and are never penalized to 0 |
| Self-hosted setup | An operator can enable ingestion with only an existing ingest-scoped API key — no new env var, no OAuth |

**Non-goals for metrics:** we do not promise a churn-accuracy lift number in slice 1 (honest-OSS brand — usage→accuracy is a v2 measurement once labels accumulate).

## User Personas & Scenarios

- **Operator / CS lead (primary):** Connects their app or CDP (Segment, or a cron/script) to POST usage events. Opens a customer's profile and sees "Usage Activity" — last active, logins/week, features used — alongside health. Later raises the usage weight so quiet customers surface as at-risk.
- **Developer (secondary):** Reads the OpenAPI for `POST /api/v1/webhooks/usage`, wires their backend's `user.login` / feature events to it with an ingest API key.

## Requirements

### Must-have (slice 1)

1. **Inbound usage receiver** — `POST /api/v1/webhooks/usage`, authenticated with the existing public API key + `require_scope("ingest")` (org-scoped via `auth.organization_id`). Accepts a **normalized, Segment-compatible** body (see API Contract). Validates, dedups, enqueues to Celery, returns `202` with `{accepted, skipped}` counts.
2. **Customer matching = email.** Resolve each event to `customer_email` from `email` (or `traits.email`). Events with **no resolvable email are dropped** and counted in `skipped` (no anonymous identity stitching in slice 1).
3. **Usage storage** — a raw `usage_event` log (dedup key, JSON properties) + a per-customer `customer_usage` rollup (last_active_at, login/session counts, distinct-feature set/count, derived `usage_score` 0-100).
4. **Usage score (0-100)** from **recency + frequency + breadth**, mapped like the existing component functions; neutral **50** when no data.
5. **5th health component, opt-in.** Add `health_weight_usage` to `org_ai_config` **defaulting to 0**. Extend `_get_org_weights`, `compute_health_score`, and the sum-to-100 validation to 5 weights. Persist `usage_component` on `customer_health_scores` and `customer_health_history`.
6. **Customer 360 surface** — a "Usage Activity" card on the profile (last active, logins, features, a usage-over-time chart) + the 5th bar in `ComponentProgressBars`.
7. **Operator setup UI** — a settings section documenting the ingest endpoint, the normalized schema, and pointing to API-key creation (inbound; distinct from the existing outbound `settings/webhooks`).
8. **Graceful degradation everywhere** — no usage data ⇒ neutral component; weight 0 ⇒ no score change. Mirrors the analyzer's VADER / embedding degrade-to-None pattern.
9. **Score-stability guarantee (testable).** A characterization test must assert that, with `health_weight_usage = 0`, `compute_health_score()` returns **identical** scores/components to pre-change for a fixture org — written **RED first** in Phase 6, before the component code exists.
10. **Payload bounds.** Cap batch size (max **1000 events/request**; oversized → `413`) and per-event `properties` size (e.g. **16 KB**, excess dropped/truncated and counted). Reject unknown `type` values. Prevents ingestion DoS / unbounded storage.

### Should-have

- Usage column ("Last active (product)") on the customers list, distinct from the existing feedback-based `last_feedback_at`.
- Recompute the usage component on a schedule (so a customer going quiet lowers their score even with no new feedback), in addition to recompute-on-feedback.
- `last_seen`/recency surfaced on the profile header.

### Nice-to-have (explicit v2)

- Add a usage factor to the 9-factor churn scorer.
- Anonymous→email identity stitching.
- Frequency/breadth weighting tunable per org.
- Backfill/import endpoint for historical usage.

## Technical Considerations

**Services touched:** `backend-api` (route, models, health service, migration, API client surface), `worker-service` (Celery task + scheduled recompute), `frontend-web` (profile card, component bar, API client, settings copy). `analysis-engine` unaffected.

**Multi-tenancy:** every row carries `organization_id`; the API key resolves the org. Matching is `(organization_id, customer_email)` — same key as `customer_health_scores` (`models/customer_health.py:78`). **Email is namespaced per org**: an ingest key can only write usage for its own `auth.organization_id`, and a `customer_email` in org A never collides with the same email in org B. There is no global email namespace — a usage event can only ever attach to a customer in the key's org. State this explicitly so reviewers don't assume cross-tenant leakage.

**GTM / docs:** update `SELF_HOSTING` (or equivalent) with a "Send product-usage events" section (endpoint, ingest-key creation, normalized schema, a curl example) and an operator "how do I verify it's working?" note (POST an event → see it on the customer profile). README capability line if warranted.

**Reuse (from dig):**
- Auth: `api/public/auth.py:74-129` (`verify_api_key`, `require_scope`).
- Webhook→Celery pattern: `source_webhooks.py:67-93`; dedup via unique constraint like `feedback_source_event.py:35-40`.
- Task: mirror `source_events.py:18-30`; enqueue by name via `get_celery_app().send_task(...)`.
- Health recompute path: `update_customer_health()` (`analysis.py:408-416`) → `compute_health_score()`.
- Frontend: `ComponentProgressBars.tsx:16-21`, `HealthTimeline.tsx` (→ `UsageTimeline.tsx`), `lib/api/customers.ts:163-231`.

**Migration:** Alembic head = `y4z5a6b7c8d9` (new `down_revision`). Three concerns: `org_ai_config.health_weight_usage INT DEFAULT 0 NOT NULL`; `customer_health_scores.usage_component` + `customer_health_history.usage_component` (nullable or default neutral); new `usage_event` + `customer_usage` tables. **The default-0 weight is what guarantees existing scores are unchanged** — no data backfill required.

### Data Model (proposed)

- **`usage_event`** (raw log): `id`, `organization_id` (FK, idx), `customer_email` (nullable until resolved — but slice-1 drops unresolved, so effectively set), `event_type` (`identify`|`track`), `event_name`, `external_event_id` (dedup), `occurred_at`, `properties` (JSON), `received_at`. Unique `(organization_id, external_event_id)`. Retention: rolling **90 days** (raw); rollup is the durable record.
- **`customer_usage`** (rollup, one per `(org, email)`): `last_active_at`, `login_count_7d`/`30d` (or sessions), `active_days_7d`/`30d`, `distinct_features` (JSON/int), `usage_score` (0-100), `events_total`, `first_seen_at`, `updated_at`. Unique `(organization_id, customer_email)`.

### API Contract (proposed)

`POST /api/v1/webhooks/usage` — header `X-API-Key: rrf_...` (ingest scope). Body (normalized, batchable):
```json
{
  "events": [
    {"type": "track",  "email": "a@co.com", "event": "feature_used",
     "name": "export_csv", "timestamp": "2026-06-28T10:00:00Z",
     "messageId": "evt_123", "properties": {"plan": "team"}},
    {"type": "identify", "email": "a@co.com", "timestamp": "...",
     "messageId": "evt_124", "traits": {"name": "Ada"}}
  ]
}
```
`202` → `{"accepted": 1, "skipped": 1, "skipped_reasons": {"no_email": 1}}`. Idempotent on `messageId` → `external_event_id`.

Read endpoint: `GET /api/v1/customers/{email}/usage?days=30` → rollup + a time series for the chart. Health-weights GET/PUT (`categories.py:193-238`) extended to 5 fields.

## Risks & Open Questions

- **Adoption friction (top risk):** value requires the operator to emit events. Mitigated by ingest-key reuse, normalized schema, and weight-0 default (no downside to having it installed). *Accepted.*
- **Score-stability regression:** adding a component must not shift existing scores. Mitigated by default weight 0 + a characterization test asserting unchanged scores post-migration. *Must be a RED test in Phase 6.*
- **Recency staleness:** if the usage component only recomputes on new feedback, a quiet customer's score won't drop. Addressed by the should-have scheduled recompute; if cut from slice 1, document the limitation honestly.
- **Open:** exact recency/frequency/breadth → 0-100 mapping curve (define in the aspect spec, mirror `_compute_resolution_component`).
- **Open:** raw-event retention default (proposed 90d) — confirm acceptable.
- **Open:** dedup window — rely solely on `messageId` uniqueness, or also a time-bound hash for sources that omit `messageId`?

## Out of Scope

- HubSpot / CRM enrichment (M3.1) — separate feature.
- Vendor OAuth / Segment Connections management UI — receiver is a plain authenticated POST.
- Anonymous identity stitching (`userId`/`anonymousId` → email reconciliation).
- Usage factor inside the 9-factor churn scorer (v2).
- Enhanced Customer 360 unified timeline (M3.4) — this slice provides the usage source it will later consume.
- Any plan-tier gating — OSS self-hosted, all features unlocked.

## Decisions locked (interview)

1. Usage health weight **defaults to 0** (opt-in; zero-surprise upgrade).
2. Receiver accepts a **normalized, Segment-compatible subset**, not raw Segment payloads.
3. Events with **no resolvable email are dropped** and reported in a skipped count (no anonymous storage in slice 1).
4. `usage_score` combines **recency + frequency + breadth**.
