# PRD: Custom Webhooks & Technical Debt (M3.1)

**Status**: Planned
**Priority**: High
**Owner**: Full-stack
**Date**: 2026-03-15
**Estimated Effort**: 2.5 weeks
**Milestone**: M3.1

---

## Part A: Custom Webhooks

### 1. Problem Statement

Rereflect users who want to automate workflows based on feedback events (e.g., post to Discord, trigger a Zapier flow, update an internal dashboard, page oncall) currently have no way to receive real-time notifications programmatically. They must manually poll the API or check the dashboard.

**Impact**: Power users and teams with custom tooling cannot integrate Rereflect into their automation pipelines. This blocks adoption for ops-heavy teams and limits expansion revenue.

---

### 2. Goals

1. Let orgs register HTTP endpoints that receive real-time POST requests when feedback events occur
2. Support 5 event types: feedback created, feedback analyzed, status changed, urgent flagged, category match
3. Category match fires based on user-selected tags (multi-select from org's known tags)
4. Configurable retry behavior per webhook (fire-and-forget OR exponential backoff)
5. HMAC-SHA256 signature verification for payload authenticity
6. Custom HTTP headers per webhook (up to 5) for auth tokens, API keys
7. Delivery log with last 50 deliveries per webhook (status, response code, timestamp)
8. Test button sending realistic sample payload
9. Plan-gated endpoint limits (Free: 2, Pro: 5, Business: 10, Enterprise: unlimited)
10. Management via Settings > Webhooks page

### 3. Non-Goals

- No webhook transformation/mapping (payload is fixed schema)
- No conditional logic beyond event type + category match
- No WebSocket alternative (HTTP POST only)
- No webhook chaining (one event = one delivery per endpoint)
- No GraphQL subscriptions
- No batch delivery (each event fires individually)

---

### 4. Event Types

| Event ID | Fires When | Payload Includes |
|----------|------------|------------------|
| `feedback.created` | New feedback item created (any source) | Full feedback object |
| `feedback.analyzed` | AI analysis completes on a feedback item | Feedback object with sentiment, categories, churn risk, tags |
| `feedback.status_changed` | Workflow status changes | Feedback ID, old_status, new_status, changed_by |
| `feedback.urgent` | Feedback flagged as urgent by AI | Feedback object with urgent_category, response_time |
| `feedback.category_match` | Feedback tags match any of the user-selected categories | Feedback object, matched_categories array |

---

### 5. Payload Schema

All webhook deliveries use a fixed JSON schema:

```json
{
  "event": "feedback.created",
  "timestamp": "2026-03-15T14:30:00Z",
  "webhook_id": 42,
  "organization_id": 1,
  "data": {
    "feedback": {
      "id": 2207,
      "text": "The login page is broken...",
      "sentiment_label": "negative",
      "sentiment_score": -0.85,
      "tags": ["authentication", "bug"],
      "is_urgent": false,
      "churn_risk_score": 45,
      "pain_point_category": "authentication",
      "feature_request_category": null,
      "workflow_status": "new",
      "assigned_to": null,
      "customer_email": "user@example.com",
      "source": "slack",
      "created_at": "2026-03-15T14:29:55Z"
    },
    "changes": {
      "old_status": "new",
      "new_status": "in_review",
      "changed_by": "admin@company.com"
    },
    "matched_categories": ["authentication"]
  }
}
```

- `data.changes` is only present for `feedback.status_changed`
- `data.matched_categories` is only present for `feedback.category_match`
- `data.feedback` is always present

---

### 6. Security

#### HMAC-SHA256 Signing

Every webhook has a unique signing secret (generated on creation, rotatable).

Delivery includes header:
```
X-Rereflect-Signature: sha256=<hex_digest>
```

Computed as:
```python
hmac.new(signing_secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
```

Receivers verify by computing the same HMAC and comparing.

#### Custom Headers

Up to 5 custom headers per webhook. Stored Fernet-encrypted in the database (same pattern as BYOK API keys). Common use cases:
- `Authorization: Bearer <token>`
- `X-API-Key: <key>`

---

### 7. Retry Behavior

Configurable per webhook endpoint:

| Mode | Behavior |
|------|----------|
| **Fire and forget** | Single POST attempt. No retries. Delivery logged as `sent` or `failed`. |
| **Exponential backoff** | Up to 3 retries: 1 min, 5 min, 30 min. Delivery logged as `sent`, `retrying`, or `failed`. |

Retry is handled by Celery tasks with countdown scheduling.

A webhook is auto-disabled after **10 consecutive failures** (across any events). User gets an in-app notification. Can be re-enabled manually.

---

### 8. Plan Limits

| Plan | Max Webhooks | Events | Custom Headers | Retry |
|------|-------------|--------|----------------|-------|
| Free | 2 | All 5 | 2 headers | Fire and forget only |
| Pro | 5 | All 5 | 5 headers | Both modes |
| Business | 10 | All 5 | 5 headers | Both modes |
| Enterprise | Unlimited | All 5 | 5 headers | Both modes |

Feature ID for plan gating: `custom_webhooks`

---

### 9. User Flow

#### 9.1 Create Webhook

```
User navigates to Settings > Webhooks
  -> Sees list of existing webhooks (name, URL, events, status badge)
  -> Clicks "Add Webhook"
  -> Form:
     - Name (required, e.g., "Slack Bot", "Internal Dashboard")
     - URL (required, HTTPS validated)
     - Events: multi-select checkboxes for 5 event types
     - Category match: if selected, shows tag multi-select picker
     - Retry mode: radio (fire-and-forget / exponential backoff)
     - Custom headers: key-value pairs (add/remove, up to limit)
  -> Clicks "Create"
  -> Webhook created, signing secret shown once (copy button)
  -> Redirect to webhook list
```

#### 9.2 Test Webhook

```
User clicks "Test" button on a webhook row
  -> System sends sample payload to the URL
  -> UI shows: response status code, response body (truncated), latency
  -> Success: green toast. Failure: red toast with error details.
```

#### 9.3 View Delivery Log

```
User clicks webhook name in list
  -> Detail page shows:
     - Webhook config (name, URL, events, status)
     - Edit / Delete / Rotate Secret buttons
     - Last 50 deliveries table:
       | Timestamp | Event | Status | Response Code | Latency |
     - Each row expandable to show request payload + response body
```

---

### 10. Database Schema

#### `webhook_endpoints` table

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| organization_id | Integer FK | organizations.id, CASCADE |
| name | String(200) | User-friendly label |
| url | String(2048) | HTTPS endpoint URL |
| signing_secret | String(500) | Fernet-encrypted HMAC secret |
| events | JSON | Array of event IDs, e.g., `["feedback.created", "feedback.urgent"]` |
| category_filters | JSON | Array of tag strings for category_match, e.g., `["authentication", "billing"]` |
| custom_headers | Text | Fernet-encrypted JSON of key-value pairs |
| retry_mode | String(50) | `fire_and_forget` or `exponential_backoff` |
| is_active | Boolean | Default true. Auto-disabled after 10 consecutive failures. |
| consecutive_failures | Integer | Reset on successful delivery. Auto-disable at 10. |
| created_at | DateTime | |
| updated_at | DateTime | |

Indexes: `(organization_id)`, `(organization_id, is_active)`

#### `webhook_deliveries` table

| Column | Type | Notes |
|--------|------|-------|
| id | Integer PK | |
| webhook_id | Integer FK | webhook_endpoints.id, CASCADE |
| event | String(100) | Event ID that triggered delivery |
| feedback_id | Integer | FK to feedback_items.id (nullable for test deliveries) |
| status | String(50) | `sent`, `failed`, `retrying` |
| attempt | Integer | 1-4 (1 = first attempt, 4 = final retry) |
| response_code | Integer | HTTP status code from receiver (nullable if network error) |
| response_body | Text | First 1KB of response body |
| error_message | Text | Network error or timeout message |
| latency_ms | Integer | Round-trip time in milliseconds |
| payload | JSON | The exact payload sent (for debugging) |
| created_at | DateTime | |

Indexes: `(webhook_id, created_at DESC)` for delivery log queries

Retention: deliveries older than 30 days are purged by a weekly Celery task.

---

### 11. API Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/webhooks` | List org's webhook endpoints | JWT |
| POST | `/api/v1/webhooks` | Create webhook endpoint | JWT, Admin+ |
| GET | `/api/v1/webhooks/{id}` | Get webhook details | JWT |
| PUT | `/api/v1/webhooks/{id}` | Update webhook config | JWT, Admin+ |
| DELETE | `/api/v1/webhooks/{id}` | Delete webhook | JWT, Admin+ |
| POST | `/api/v1/webhooks/{id}/test` | Send test delivery | JWT, Admin+ |
| POST | `/api/v1/webhooks/{id}/rotate-secret` | Rotate signing secret | JWT, Admin+ |
| GET | `/api/v1/webhooks/{id}/deliveries` | List deliveries (last 50) | JWT |

---

### 12. Dispatch Architecture

Webhook dispatch happens asynchronously via Celery tasks to avoid slowing down API responses.

```
API/Worker completes action (e.g., feedback created)
  -> Calls dispatch_webhook_event(org_id, event_type, feedback)
  -> Queries active webhooks for org matching event_type
  -> For category_match: filters by tag intersection
  -> Enqueues Celery task per webhook: deliver_webhook(webhook_id, payload)
  -> Task POSTs to URL with HMAC signature + custom headers
  -> Logs delivery result
  -> On failure + exponential_backoff: re-enqueues with countdown
  -> On 10th consecutive failure: auto-disable + notification
```

Dispatch points (where `dispatch_webhook_event` is called):
1. `POST /api/v1/feedback` — after feedback creation → `feedback.created`
2. Worker analysis task — after AI analysis completes → `feedback.analyzed` + `feedback.urgent` (if urgent) + `feedback.category_match` (if tags match)
3. `PATCH /api/v1/feedback/{id}/status` — after status change → `feedback.status_changed`

---

### 13. Frontend Pages

#### Settings > Webhooks (list)
- Table: Name, URL (truncated), Events (badge chips), Status (green/red/yellow badge), Last Delivery
- Actions: Edit, Test, Delete
- "Add Webhook" button (disabled if at plan limit with upgrade CTA)
- Plan limit indicator: "2/5 webhooks used"

#### Webhook Detail (edit + delivery log)
- Tabs: Configuration | Delivery Log
- Configuration tab: editable form (same as create)
- Delivery Log tab: table of last 50 deliveries with expandable rows
- Header: webhook name, status badge, "Rotate Secret" and "Delete" buttons

---

## Part B: Technical Debt

### 14. Sentry Error Tracking (Free Tier)

**Scope**: All 3 services (backend-api, frontend-web, worker-service)

#### Backend API (FastAPI)
- Install `sentry-sdk[fastapi]`
- Initialize in `main.py` with DSN from env var `SENTRY_DSN`
- Auto-captures unhandled exceptions, 500 responses
- Attach org_id and user_id to Sentry scope for context
- Environment tag: `RAILWAY_ENVIRONMENT` or `development`

#### Frontend (Next.js)
- Install `@sentry/nextjs`
- Configure `sentry.client.config.ts` and `sentry.server.config.ts`
- Wrap app with Sentry error boundary
- Capture React component errors, chunk load failures, API 500s
- Source maps uploaded during build

#### Worker Service (Celery)
- Install `sentry-sdk[celery]`
- Initialize in worker entry point
- Auto-captures task failures with task name, args, traceback
- Tags: task_name, org_id

#### Configuration
```env
SENTRY_DSN=https://xxx@xxx.ingest.sentry.io/xxx
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
```

**Free tier limits**: 5,000 errors/month, 1 user, 30-day retention. Sufficient for current scale.

### 15. Monitoring (Railway + Health Endpoint)

- Existing `/health` endpoint already returns `{"status": "healthy"}`
- Add `/health/detailed` endpoint (system-admin only) returning:
  - Database connectivity (SELECT 1)
  - Redis connectivity (PING)
  - Celery worker status (existing `/worker/status`)
  - Memory usage
  - Uptime
- Railway provides built-in CPU, memory, network metrics — no extra tooling needed
- No additional monitoring services required at current scale

---

## 16. Implementation Phases

### Phase 1: Database + Backend (3-4 days)
- Alembic migration for `webhook_endpoints` + `webhook_deliveries` tables
- SQLAlchemy models
- CRUD API endpoints (list, create, get, update, delete)
- Fernet encryption for signing_secret + custom_headers
- Test endpoint with sample payload
- Rotate secret endpoint
- Deliveries list endpoint
- Plan gating: `custom_webhooks` feature + endpoint limits per plan

### Phase 2: Dispatch Engine (2-3 days)
- `dispatch_webhook_event()` function (queries matching webhooks, enqueues tasks)
- Celery task `deliver_webhook()` with HMAC signing, custom headers, timeout
- Retry logic (exponential backoff via Celery countdown)
- Auto-disable after 10 consecutive failures + notification
- Delivery logging (status, response code, latency, payload)
- Wire dispatch into: feedback creation, analysis task, status change endpoint
- Weekly purge task for deliveries > 30 days

### Phase 3: Frontend (2-3 days)
- Settings > Webhooks list page
- Add/Edit webhook form (name, URL, events, category picker, retry mode, headers)
- Webhook detail page with Configuration + Delivery Log tabs
- Test button with result display
- Plan limit indicator + upgrade CTA
- Signing secret display (show-once on create, masked on edit, rotate button)

### Phase 4: Sentry Integration (1 day)
- Install + configure Sentry SDK in all 3 services
- Verify error capture in staging
- Add SENTRY_DSN to Railway env vars

### Phase 5: Health Endpoint Enhancement (0.5 day)
- Add `/health/detailed` with DB, Redis, Celery, memory checks
- System-admin gated

---

## 17. Testing Strategy

- Backend: CRUD endpoints, dispatch logic, retry behavior, HMAC verification, plan limits, auto-disable
- Worker: delivery task, retry countdown, failure counting, purge task
- Frontend: webhook list, create form validation, delivery log display, test button
- Integration: end-to-end from feedback creation to webhook delivery

---

## 18. Key Files (Expected)

### Backend
- `src/models/webhook_endpoint.py` — SQLAlchemy model
- `src/models/webhook_delivery.py` — SQLAlchemy model
- `src/api/routes/webhooks.py` — CRUD + test + rotate endpoints
- `src/services/webhook_dispatcher.py` — dispatch_webhook_event + deliver_webhook task
- `alembic/versions/xxx_add_webhook_tables.py` — migration

### Worker
- `src/tasks/webhook_delivery.py` — Celery task for HTTP delivery + retry

### Frontend
- `app/(dashboard)/settings/webhooks/page.tsx` — webhook list
- `app/(dashboard)/settings/webhooks/[id]/page.tsx` — webhook detail + delivery log
- `lib/api/webhooks.ts` — API client
- `components/webhooks/WebhookForm.tsx` — create/edit form
