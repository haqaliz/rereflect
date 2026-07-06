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
```

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

- `read` — read feedback, customers, and analytics
- `ingest` — submit new feedback for AI analysis
- `write` — update or delete existing feedback (status, category/sentiment corrections,
  tags, urgency, delete); see **Feedback (write)** below

### Feedback (write)

```
PATCH  /api/public/v1/feedback/{id}   # Update an existing feedback item (scope: write)
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

## Common gotchas

- **Trailing slashes** — match the route exactly; a missing/extra `/` can return 422.
- **`page_size`** — keep it ≤ 100.
- **422 validation errors** — ensure all required fields are present and typed correctly.
