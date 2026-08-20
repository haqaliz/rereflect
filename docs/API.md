# API Reference

Rereflect exposes a REST API under `/api/v1`. When the backend is running, the full
interactive OpenAPI/Swagger docs are at **http://localhost:8000/docs** — this page is a
quick map of the most common endpoints.

## Authentication

All protected endpoints require a JWT bearer token:

```
Authorization: Bearer <token>
```

```
POST /api/v1/auth/signup
POST /api/v1/auth/login
GET  /api/v1/auth/me
```

## Multi-tenancy

All data is scoped by `organization_id`, which is extracted from the JWT. You only ever
see and act on your own organization's data.

## Feedback

```
GET    /api/v1/feedback              # List (paginated, filterable)
POST   /api/v1/feedback              # Create
GET    /api/v1/feedback/{id}         # Get one
PUT    /api/v1/feedback/{id}         # Update
DELETE /api/v1/feedback/{id}         # Delete
POST   /api/v1/feedback/import       # CSV import
POST   /api/v1/feedback/{id}/issue-draft   # AI-draft an issue/task title+body (admin/owner)
```

### `POST /api/v1/feedback/{id}/issue-draft`

Generates an AI-drafted **title + body** from a feedback item, for use as a starting point in the
create-issue/create-task wizard (Jira / Asana). It only returns the draft — it never creates the
work item. Requires the **admin** or **owner** role.

```
POST /api/v1/feedback/{id}/issue-draft
Body: { "target": "jira" | "asana", "tone"?: string }

200 { "title": "...", "body": "..." }
404  feedback not found in your organization
409  no LLM configured for the organization (configure a provider in Settings → AI, or a local LLM)
422  invalid/unknown fields (e.g. bad `target`)
502  the model returned an unusable draft, or the provider call failed
```

The draft uses the org's configured LLM (cloud BYOK or local Ollama / OpenAI-compatible) and the
org's tone / brand voice. When no LLM is configured it returns `409` and the wizard hides the
"Draft with AI" action — the wizard still works with manually-entered text.

### Pagination

```
GET /api/v1/feedback?page=1&page_size=20&sort_by=created_at&sort_order=desc
```

`page_size` must not exceed 100.

### Filtering

```
GET /api/v1/feedback?sentiment=negative&is_urgent=true&search=payment
```

## Dashboard

```
GET /api/v1/dashboard                # Aggregated analytics data
```

## Team management

```
GET    /api/v1/team                  # List members
POST   /api/v1/team/invite           # Send invite
PATCH  /api/v1/team/{id}/role        # Change role
DELETE /api/v1/team/{id}             # Remove member
```

## Public API (API keys)

In addition to the JWT-authenticated `/api/v1` routes above, Rereflect exposes a
**public API** under `/api/public/v1` for programmatic access, supporting reading, ingesting,
and writing (updating/deleting) feedback. Authenticate with an API key (`rrf_…`, created in
**Settings → API Keys**) instead of a JWT:

```
Authorization: Bearer rrf_xxxxxxxx        # or:  X-API-Key: rrf_xxxxxxxx
```

Keys carry scopes; each endpoint below notes the scope it requires (the read endpoints
require `read`). As always, data is scoped to the key's organization.

- `read` — read feedback, customers, analytics, and custom categories
- `ingest` — submit new feedback for AI analysis
- `write` — update, bulk-update, or delete existing feedback (status, category/sentiment
  corrections, tags, urgency, delete) and manage custom categories; see
  **Feedback (write)** and **Custom categories** below

### Feedback (write)

```
PATCH  /api/public/v1/feedback/{id}   # Update an existing feedback item (scope: write)
POST   /api/public/v1/feedback/bulk   # Bulk-update up to 500 feedback items (scope: write)
DELETE /api/public/v1/feedback/{id}   # Delete a feedback item (scope: write)
```

#### `PATCH /api/public/v1/feedback/{id}`

Requires the `write` scope. The body is JSON with any combination of:

- `workflow_status` — one of `new`, `in_review`, `resolved`, `closed`. Setting the item to
  its current status is a no-op. An optional `resolution_note` is attached when the status
  is `resolved`.
- `correction` — record a category/sentiment correction as a training signal (the AI value
  is **not** overwritten): `{"field": "pain_point" | "feature_request" | "sentiment", "corrected_value": "<value>"}`.
- `tags` — **replaces** the item's stored tag list. Omit the field to leave tags unchanged;
  send `[]` to clear all tags. Each tag is trimmed of surrounding whitespace and duplicates
  (post-trim) are removed. Validation: at most 20 tags, each at most 50 characters, and no
  tag may be empty after trimming — violations return `422`.
- `is_urgent` — `true`/`false`. Omit the field to leave the urgency flag unchanged.

The request model uses `extra="forbid"`, so any unknown field in the body returns `422`.

An empty body (no recognized fields set) returns `400`. A key without the `write` scope
returns `403`. A feedback id outside the key's organization returns `404`. Returns the
updated feedback item.

You can combine fields in one request, e.g. update status and replace tags together:

```bash
curl -X PATCH https://<host>/api/public/v1/feedback/123 \
  -H "Authorization: Bearer rrf_xxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"workflow_status": "resolved", "tags": ["billing", "refund"], "is_urgent": false}'
```

**Note:** when a request combines `workflow_status`/`correction` with `tags`/`is_urgent`,
the two groups are applied and committed in **separate database transactions** — the write
is best-effort, not atomic. A crash between the two commits can leave the status/correction
change applied without the tags/`is_urgent` change (or vice versa). This is a known
limitation carried from the initial write-scope release; retries are safe since each group
is idempotent given the same input.

#### `POST /api/public/v1/feedback/bulk`

Requires the `write` scope. Applies the same patch shape as the single `PATCH` above to up
to 500 ids in one request:

```json
{ "ids": [101, 102, 103], "patch": { "workflow_status": "resolved", "tags": ["billing"] } }
```

- `ids` — 1–500 ids (deduped, order preserved). Ids not owned by this org (or non-existent)
  are `skipped`, not errors.
- `patch` — same body shape as the single `PATCH` (`workflow_status`/`resolution_note`,
  `correction`, `tags`, `is_urgent`); at least one recognized field is required (`400`
  otherwise).
- `workflow_status` is applied via one batched call; `tags`/`is_urgent`/`correction` are
  applied per item inside a `SAVEPOINT` each — a per-item failure is non-contagious and
  doesn't roll back the rest of the batch.
- Pass `?count_only=true` to dry-run: returns only the match count and mutates nothing.

Response:

```json
{
  "matched": 3,
  "updated": 2,
  "skipped": 1,
  "results": [
    { "id": 101, "status": "updated" },
    { "id": 102, "status": "noop" },
    { "id": 103, "status": "skipped", "reason": "not_found" }
  ]
}
```

`results[].status` is one of `updated`, `noop` (matched but nothing changed), `skipped`
(not owned by this org / doesn't exist), or `error` (per-item field write failed — retry-safe,
since re-applying the same patch is idempotent). Fires the same webhooks/events as the single
`PATCH` for the ids that actually changed.

```bash
curl -X POST https://<host>/api/public/v1/feedback/bulk \
  -H "Authorization: Bearer rrf_xxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"ids": [101, 102, 103], "patch": {"workflow_status": "resolved"}}'
```

#### `DELETE /api/public/v1/feedback/{id}`

Requires the `write` scope (there is no separate `delete` scope). Permanently deletes the
feedback item. Mirrors the internal dashboard delete: archives the customer's health record
if this was their last feedback item, invalidates dashboard/analytics caches, and emits a
`feedback:deleted` event.

A feedback id outside the key's organization (or that doesn't exist) returns `404`. On
success, returns `204 No Content` with an empty body.

```bash
curl -X DELETE https://<host>/api/public/v1/feedback/123 \
  -H "Authorization: Bearer rrf_xxxxxxxx"
```

### Custom categories

```
GET    /api/public/v1/categories             # List custom categories (scope: read)
POST   /api/public/v1/categories             # Create a custom category (scope: write)
PATCH  /api/public/v1/categories/{id}        # Update name/description/is_active (scope: write)
DELETE /api/public/v1/categories/{id}        # Delete a custom category (scope: write)
```

Mirrors the internal `/api/v1/categories/custom` CRUD. `GET` accepts an optional
`category_type` filter. `POST` requires `name` and `category_type`
(`pain_point`/`feature_request`/`urgency`/`general`); a duplicate `(org, category_type, name)`
returns `409`. `PATCH` accepts `name`/`description`/`is_active` — `category_type` is
immutable (sending it returns `422`, unknown field); a rename collision returns `409`. Both
`PATCH` and `DELETE` return `404` for a missing or other-org id.

`DELETE` hard-deletes the category (`204`, no cascade). If the category's name is referenced
by an *active* `feedback_category_match` automation rule, the response carries an advisory
`X-Rereflect-Warning` header naming the category and the referencing rule(s) — the delete
still succeeds either way.

```bash
curl -X DELETE https://<host>/api/public/v1/categories/42 \
  -H "Authorization: Bearer rrf_xxxxxxxx"
# → 204, X-Rereflect-Warning: category 'Billing' is referenced by 1 automation rule(s): Billing escalation
```

### Customer 360

```
GET /api/public/v1/customers                      # List customers (health-scored)
GET /api/public/v1/customers/{email}              # Full Customer 360 profile (health, components, churn, LLM summary)
GET /api/public/v1/customers/{email}/health       # Health score + component breakdown (incl. usage)
GET /api/public/v1/customers/{email}/timeline     # Unified activity timeline (cursor-paginated)
```

The timeline merges feedback, product-usage, churn and health-score events in reverse-chronological
order. Page with an opaque cursor:

```
GET /api/public/v1/customers/{email}/timeline?limit=20
GET /api/public/v1/customers/{email}/timeline?before=<next_cursor>&limit=20
→ { "events": [ … ], "next_cursor": "<cursor|null>" }
```

`limit` must be 1–100 (default 20). When `next_cursor` is `null`, there are no more events.

#### Customer segments

Both `GET /api/public/v1/customers/{email}` (profile) and the internal `GET /api/v1/customers/`
(list) responses include a `segment` field — a single, rule-based classification assigned to
each customer (see `services/backend-api/src/services/segment_service.py`). It is **not** an
ML model; it's a top-down priority rule engine evaluated on ingest and refreshed nightly.

The list endpoint (`GET /api/v1/customers/?segment=<slug>`) also accepts a `segment` query
filter; an unrecognized slug returns `422`.

Slugs (priority order — first matching rule wins):

| Slug | Meaning |
|------|---------|
| `at_risk` | High churn risk (risk level `at_risk`/`critical`, or churn probability ≥ 0.5) |
| `silent_churner` | Low product usage + declining sentiment + stale/no recent feedback |
| `dormant` | No recent product activity (or, without usage data, stale feedback) |
| `power_user` | High usage score and frequent active days in the last 30 days |
| `happy_advocate` | High health score with stable/improving sentiment |
| `new` | Recently created customer with little feedback history yet |
| `unsegmented` | None of the above rules matched |

`segment` is nullable — `null` means the segment hasn't been computed yet for that customer
(pre-ingest/pre-nightly-recompute), which is distinct from the `unsegmented` slug (computed,
but no rule matched).

### Customer bulk actions (segment-actions)

Operator-triggered actions over a **cohort** of customers — either an explicit list of emails
or the same filter vocabulary as the list endpoint. Exactly one of `emails`/`filter` must be
set on the `cohort` object, else `422`.

```json
{ "cohort": { "emails": ["a@acme.com", "b@acme.com"] } }
{ "cohort": { "filter": { "segment": "at_risk", "risk_level": "critical", "search": "acme", "include_archived": false } } }
```

#### `GET /api/v1/customers/export`

Streams a CSV of customers matching the same query params as the list endpoint (`segment`,
`risk_level`, `search`, `include_archived`, `sort_by`, `sort_order`). Requires the
`customer_health_scores` feature (Pro+); any authenticated role may export. Paginates
internally (batches of 500 rows) — never loads the whole organization into memory.

```
GET /api/v1/customers/export?segment=at_risk
→ 200 text/csv
  Content-Disposition: attachment; filename="customers-at_risk.csv"
```

Columns: `email, name, health_score, risk_level, segment, confidence_level, feedback_count,
last_feedback_at, last_active_at, churn_probability, tags, cs_owner_email`. `tags` is
pipe-joined (`"vip|expansion"`). `sentiment_trend` is intentionally **omitted** — computing it
per row is an N+1 the list endpoint pays for one page at a time; not worth it for a
potentially org-wide export.

#### `POST /api/v1/customers/bulk/tags`

Requires **admin/owner**. Adds or removes tags across a resolved cohort.

```
POST /api/v1/customers/bulk/tags
Body: { "cohort": {...}, "tags": ["vip", "expansion"], "mode": "add" | "remove" }

200 { "matched": 12, "updated": 11, "skipped": 1, "errors": [] }
```

Tags are trimmed, deduped, and empty strings dropped; each tag is capped at 50 characters.
`add` is a set union, `remove` is a set difference, applied per customer. A customer whose tag
count would exceed **20** after `add` is **not** silently truncated — it's left unchanged and
reported in `errors` (and not counted in `updated`).

#### `POST /api/v1/customers/bulk/assign-owner`

Requires **admin/owner**. Sets (or clears, with `user_id: null`) the CS owner across a
resolved cohort.

```
POST /api/v1/customers/bulk/assign-owner
Body: { "cohort": {...}, "user_id": 42 }

200 { "matched": 12, "updated": 12, "skipped": 0, "errors": [] }
```

`user_id` must be an **active** member of the caller's organization (role irrelevant); a
non-member or deactivated `user_id` returns `422` before any rows are touched. `null` clears
the owner for every customer in the cohort.

### Churn playbook cohort run (segment-actions)

`POST /api/v1/playbooks/{id}/run-batch` runs a churn playbook against a set of customers,
gated by `churn_playbooks` (Business+). Requires `filters` in the body; two independent,
combinable selection axes:

- **Probability band** — `probability_min`/`probability_max` (defaults to the playbook's own
  band when omitted) and `time_to_churn_bucket`. This is the original targeting mode.
- **Cohort** — `emails: list[str]` OR `segment: str` (validated against the same
  [segment slugs](#customer-segments); an unrecognized value returns `422`). Resolved via the
  same shared filter logic as `GET /api/v1/customers/` — never a second implementation.

When a cohort (`emails`/`segment`) is combined with a probability band, they **AND** —
customers must match both. A request with neither `emails` nor `segment` behaves exactly as
before this extension (probability-only, back-compat).

```
POST /api/v1/playbooks/42/run-batch
Body: { "filters": { "segment": "at_risk", "probability_min": 0.60 } }

200 { "queued": 7, "execution_ids": [101, 102, ...], "matched": 7 }
```

**Queue-safety cap.** The resolved cohort size (`matched`) is computed up front. If it exceeds
`RUN_BATCH_MAX_CUSTOMERS` (500), the request is rejected atomically:

```
422 "cohort of 812 exceeds batch cap of 500; narrow the filter"
```

Nothing is queued when the cap is hit — no partial batches. The plan's daily execution limit
(`_BATCH_RUN_DAILY_LIMITS`, e.g. 50/day on Business) is also checked against the **full**
resolved cohort size up front (`today_count + matched`), not incrementally while queuing, so a
large cohort can't partially queue before the daily allowance is exhausted.

**Affected-count preview.** Pass `?count_only=true` to resolve and return `{matched}` without
queuing anything — no cap or daily-limit checks apply, it's a pure dry-run for a UI
"N customers will be affected" confirmation step:

```
POST /api/v1/playbooks/42/run-batch?count_only=true
Body: { "filters": { "segment": "dormant" } }

200 { "queued": 0, "execution_ids": [], "matched": 34 }
```

Every normal (non-`count_only`) run-batch response also includes `matched`, so the caller can
show "queued N of N" without a separate request.

Unknown emails in the `emails` cohort are simply not matched (skipped, not an error) — same
semantics as `resolve_cohort`.

### Customer outreach (customer-outreach-email-actions)

Sends customer-facing email through your own **Resend key** (`RESEND_API_KEY`; no key ⇒
every send records a loud `failed: email not configured`). Opted-out customers and
recipients inside the shared 24h cooldown (`OUTREACH_COOLDOWN_HOURS`) are skipped loudly.
All mutations below are **admin/owner**.

**Bulk campaign** — `POST /api/v1/customers/bulk/outreach` (admin/owner). Body
`{ "cohort": {...}, "subject": "…", "body": "…" }` — the same [cohort contract](#customer-bulk-actions-segment-actions)
as tag/assign; `subject` 1–200 chars, `body` 1–20,000. Resolved cohort must be ≤ 500
(422 over cap) and non-empty (422). Blank/invalid emails, opted-out customers and archived
customers are counted into `skipped` with reasons. Creates an `outreach_campaign` + one
recipient row per email and enqueues a per-recipient Celery send:

```
POST /api/v1/customers/bulk/outreach
Body: { "cohort": { "segment": "at_risk" }, "subject": "…", "body": "…" }

202 { "matched": 12, "queued": 12, "skipped": 2, "errors": [] }
```

`?count_only=true` is a pure dry-run — resolves the cohort and returns the same shape with
`queued: 0` and zero rows created (no cap/empty checks apply).

**AI draft** — `POST /api/v1/customers/bulk/outreach/draft` (admin/owner). Body
`{ "cohort"?: {...}, "tone"?: "professional"|"friendly"|"empathetic"|"concise"|"technical" }`.
Drafts `{ "subject", "body" }` via the org's configured LLM (BYOK or local; `409` when no
LLM is configured). **Never sends** — the draft populates editable fields and a human
triggers the campaign.

**Campaigns** — `GET /api/v1/outreach/campaigns` (admin/owner, `page`/`page_size` ≤ 100):

```
200 { "items": [ { "id": 1, "subject": "…", "status": "done",
      "recipient_count": 3, "counts": { "queued": 0, "sent": 1, "skipped": 1, "failed": 1 },
      "created_at": "…" } ], "total": 2, "page": 1, "page_size": 20 }
```

**Retry** — `POST /api/v1/outreach/campaigns/{id}/retry` (admin/owner) re-enqueues
recipients still `queued` (terminal rows are never resent) and returns the same
`{matched, queued, skipped, errors}` shape; unknown/cross-org id → 404.

**Templates** — `GET /api/v1/outreach/templates` (any role) lists the built-in outreach
templates (`re_engagement`, `weekly_digest_entry`) used by playbook `send_email` steps:
`[{ "key", "label", "description", "subject", "body" }]`.

**Unsubscribe** — `GET /api/v1/outreach/unsubscribe?token=…` (public). A stateless
HMAC-signed token (minted per send, carried in the email's `List-Unsubscribe` header as
`{APP_URL}/outreach/unsubscribe?token=…`) flips the customer's `outreach_opt_out` flag;
invalid token → 400.

**Opt-out** — `PATCH /api/v1/customers/{email}` (admin/owner) accepts
`{ "outreach_opt_out": bool }` (extra fields 422) and returns the updated profile (which
now includes the flag).

### Automation customer email (`send_customer_email` action)

**Action config** — an automation rule (admin/owner, `POST`/`PUT /api/v1/automations`) can
carry an action of the form:

```json
{
  "type": "send_customer_email",
  "config": { "template": "re_engagement", "recipient": "customer" }
}
```

`template` must be a key of the built-in outreach registry
(`GET /api/v1/outreach/templates` — `re_engagement`, `weekly_digest_entry`); `recipient` is
`customer` (default) or `cs_assignee` (the CS owner on the customer's health row). Any other
key in `config` → 422 (the model is `extra="forbid"`), as is an unknown template or
recipient.

**Deliveries** — `GET /api/v1/automations/{rule_id}/deliveries` (admin/owner, org-scoped,
newest first, `page` / `page_size` ≤ 100) returns
`{ "deliveries": [...], "total", "page", "page_size" }` where each row is
`{ id, rule_id, organization_id, customer_email, to_email, template_key, subject, status,
reason, created_at }` and `status` is one of `queued | sent | skipped | failed`. A rule the
caller's org does not own → 404; a member → 403.

**Semantics** — a rule in `shadow` mode evaluates and logs but never creates a delivery or
sends. On an active rule the evaluator writes a `queued` row and enqueues the send; the
worker flips it to `sent`, or to `skipped` / `failed` with the reason (`opted out`,
`in cooldown`, `email not configured`, a provider error). A skip is always recorded — it is
never reported as a success. With `RESEND_API_KEY` unset, no send is enqueued at all and the
row is written directly as `skipped: email not configured`.

## Common gotchas

- **Trailing slashes** — match the route exactly; a missing/extra `/` can return 422.
- **`page_size`** — keep it ≤ 100.
- **422 validation errors** — ensure all required fields are present and typed correctly.
