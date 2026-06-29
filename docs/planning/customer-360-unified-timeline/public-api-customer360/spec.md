# Aspect Spec — `public-api-customer360`

**Parent PRD:** `../prd.md` · **Slug:** `customer-360-unified-timeline`
**Build order:** 2 of 3 (depends on `timeline-service-v1`)

## Problem slice & outcome

The public REST API exposes only a customers *list* and a thin `/customers/{email}/health`
(`routes/public_api.py:305-364`). M3.4 calls for a **Customer 360 API + health-score API +
timeline** for programmatic/self-host consumption. Outcome: read-only public endpoints, API-key
+ `read` scope, reusing the shared timeline service and the v1 profile shape.

## In scope

- `GET /api/public/v1/customers/{email}` — full Customer 360 profile. Mirror v1
  `CustomerProfileResponse` (health_score, risk_level, confidence, the 5 components incl. usage,
  churn_probability/bucket, LLM summary fields, feedback_count, last_feedback_at). Reuse the v1
  serialization — do not duplicate field logic.
- `GET /api/public/v1/customers/{email}/timeline?before=<iso>&limit=<n>` — same
  `{ events, next_cursor }` shape as v1, by calling `build_timeline` from aspect 1.
- Extend `GET /api/public/v1/customers/{email}/health` with the component breakdown +
  confidence if it is currently thin (additive only — don't break existing consumers).
- All three: `dependencies=[Depends(require_scope("read"))]` + `auth = Depends(verify_api_key)`,
  org from `auth.organization_id`. 404 when the customer doesn't exist in the org.
- OpenAPI: endpoints documented (auto), with at least a response example each (nice-to-have).

## Out of scope

- Any **write/CRUD** (read-only — consistent with shipped public API D4).
- New scopes, rate-limit tiers, per-endpoint quotas.
- Frontend.

## Acceptance criteria (testable, TDD)

1. With a valid `rrf_` key carrying `read` scope, each endpoint returns 200 with the documented
   shape for an existing customer.
2. A key **lacking** `read` scope → 403 (reuse `require_scope` test pattern).
3. No/invalid key → 401.
4. Cross-org isolation: a key for org A cannot read org B's customer (404, not another org's data).
5. The public profile fields match the v1 profile for the same customer (shared serialization).
6. The public timeline paginates identically to v1 (cursor in → next slice, no dup/skip).
7. Unknown customer email → 404 on all three.

## Dependencies & sequencing

- **Depends on aspect 1** (`build_timeline` + `TimelineEvent` schema, and a reusable profile
  serializer). Start after aspect 1's service contract is green.
- Reuse `api/public/auth.py` (`verify_api_key`, `require_scope`) — no auth changes.

## Risks

- Open question from PRD: redact LLM free-text in the public profile? Default **no** (operator's
  own self-hosted data); revisit if a consumer objects. Decide at review gate.
- Avoid drift between v1 and public profile shapes — share the serializer, test parity (AC5).
