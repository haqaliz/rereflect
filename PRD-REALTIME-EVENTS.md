# PRD: Real-Time Event System — Replace Polling with WebSocket Push

## Status: Draft — Pending Review

## 1. Problem Statement

The Rereflect frontend currently uses **5 independent polling loops**, all at 30-second intervals, to keep data fresh:

| # | Component | Mechanism | Endpoint | Impact |
|---|-----------|-----------|----------|--------|
| 1 | `NotificationBell` | `setInterval` | `GET /notifications/unread-count` | Always-on in header |
| 2 | `ActivityFeedWidget` | `setInterval` | `GET /dashboard/activity-feed` | Dashboard widget |
| 3 | `useActivityFeed` hook | React Query `refetchInterval` | `GET /dashboard/activity-feed` | Dashboard hook (duplicates #2) |
| 4 | Feedbacks page | React Query `refetchInterval` | `GET /feedback/?...` | Core data table |
| 5 | Workflow page | React Query `refetchInterval` | `GET /workflow/overview` + `GET /team/members` | Kanban + table view |

**Problems with polling:**
- **Wasted requests**: 2 API calls/minute per component, even when nothing changed
- **30s staleness**: Users see stale data for up to 30 seconds after changes
- **No cross-user awareness**: When a teammate changes a workflow status, other users don't see it until their next poll cycle
- **Duplicate fetches**: ActivityFeedWidget and useActivityFeed poll the same endpoint independently
- **Server load**: With N concurrent users, polling generates `N * (active_polls) * 2/min` unnecessary requests

## 2. Solution Overview

Replace all 5 polling patterns with a **real-time event push system** via a new `/ws/events` WebSocket endpoint. When data changes (feedback created, workflow status changed, notification fired), the backend pushes the event to all connected org members immediately.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend                                                    │
│                                                              │
│  RealtimeProvider (single WS connection to /ws/events)       │
│    │                                                         │
│    ├── useRealtimeEvents('notification:*') → NotificationBell│
│    ├── useRealtimeEvents('activity:*')     → ActivityFeed    │
│    ├── useRealtimeEvents('feedback:*')     → FeedbacksPage   │
│    └── useRealtimeEvents('workflow:*')     → WorkflowPage    │
│                                                              │
│  On event received → queryClient.invalidateQueries([key])    │
│  React Query refetches via existing REST endpoints           │
└───────────────────────────┬─────────────────────────────────┘
                            │ wss://
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend                                                     │
│                                                              │
│  /ws/events endpoint                                         │
│    ├── JWT auth via query param (same as /ws/copilot)        │
│    ├── Per-org connection tracking (EventConnectionManager)  │
│    ├── Heartbeat + idle timeout                              │
│    └── Broadcasts events to all org members                  │
│                                                              │
│  Event emitters (direct from route handlers + workers):      │
│    ├── POST /feedback/     → emit("feedback:created", data)  │
│    ├── POST /workflow/status → emit("workflow:updated", data) │
│    ├── Celery task done    → emit("feedback:analyzed", data)  │
│    └── notification created → emit("notification:new", data)  │
└─────────────────────────────────────────────────────────────┘
```

## 3. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| WS endpoint | Separate `/ws/events` | Keeps copilot streaming isolated; different scaling characteristics |
| Event trigger | Direct from route handlers | Simple, no extra infra (no Redis pub/sub needed yet) |
| Payload style | Full data payloads | No extra REST call needed on event receipt |
| Event scope | Per-organization | All org members see changes in real-time (collaborative) |
| Self-events | Exclude the actor | Frontend already handles optimistic updates; avoids flicker |
| Worker events | Workers push via ConnectionManager | Analysis completion triggers immediate UI update |
| Cache strategy | Invalidate React Query cache + refetch | Leverages existing REST API code; consistent data |
| Fallback on disconnect | Wait for reconnection (exponential backoff) | Simpler; existing WS reconnection logic is proven |
| Rollout | All at once | Single cohesive refactor across all 5 polling areas |
| Frontend hook | Single `useRealtimeEvents()` + event bus | One WS connection shared by all consumers |

## 4. Scope

### In Scope
- New `/ws/events` backend WebSocket endpoint
- `EventConnectionManager` with per-org connection tracking
- Event emission from 4 areas: notifications, activity feed, feedback, workflow
- Event emission from Celery workers (post-analysis)
- Frontend `RealtimeProvider` context + `useRealtimeEvents()` hook
- Remove all 5 polling patterns
- React Query cache invalidation on event receipt

### Out of Scope
- Redis pub/sub (single backend instance is sufficient for now)
- Copilot WebSocket changes (stays separate)
- Customer health score real-time updates
- Dashboard stats real-time updates (low frequency, stays on window focus refetch)
- Admin pages (low usage, stays REST-only)
- Settings/billing pages (rare changes)

## 5. Event Catalog

### 5.1 Notification Events

| Event Type | Trigger | Payload | Emitted From |
|------------|---------|---------|--------------|
| `notification:new` | New notification created | `{id, type, title, message, is_read, created_at}` | Notification creation service |
| `notification:read` | Notification marked read | `{id}` | `PATCH /notifications/:id/read` |
| `notification:read_all` | All marked read | `{}` | `POST /notifications/read-all` |
| `notification:count` | Unread count changed | `{unread_count: number}` | After any notification event |

**Frontend action**: Invalidate `['notifications']` query key. Update badge count directly from `notification:count` payload.

### 5.2 Activity Feed Events

| Event Type | Trigger | Payload | Emitted From |
|------------|---------|---------|--------------|
| `activity:new` | New activity item | `{id, type, description, user_name, created_at, metadata}` | Various route handlers |

**Triggers include**: feedback created/imported, analysis completed, workflow status change, team member joined, integration connected.

**Frontend action**: Invalidate `['activity-feed']` query key.

### 5.3 Feedback Events

| Event Type | Trigger | Payload | Emitted From |
|------------|---------|---------|--------------|
| `feedback:created` | New feedback submitted | `{id, title, source, sentiment, created_at}` | `POST /feedback/` |
| `feedback:imported` | CSV import completed | `{count, source}` | CSV import handler |
| `feedback:analyzed` | Analysis completed | `{id, sentiment, pain_points, features, is_urgent}` | Celery analysis task |
| `feedback:updated` | Feedback edited | `{id, fields_changed: string[]}` | `PATCH /feedback/:id` |
| `feedback:deleted` | Feedback removed | `{id}` | `DELETE /feedback/:id` |

**Frontend action**: Invalidate `['feedback', ...]` query keys.

### 5.4 Workflow Events

| Event Type | Trigger | Payload | Emitted From |
|------------|---------|---------|--------------|
| `workflow:status_changed` | Status updated | `{feedback_id, old_status, new_status, changed_by}` | `POST /workflow/status` |
| `workflow:assigned` | Item assigned | `{feedback_id, assignee_id, assignee_name, assigned_by}` | `POST /workflow/assign` |
| `workflow:note_added` | Note created | `{feedback_id, note_id, author_name}` | `POST /workflow/:id/notes` |

**Frontend action**: Invalidate `['workflow', ...]` query keys.

## 6. Technical Design

### 6.1 Backend: EventConnectionManager

**File**: `services/backend-api/src/services/event_connection_manager.py`

```python
class EventConnectionManager:
    """Manages WS connections for real-time event broadcasting, grouped by org."""

    def __init__(self):
        # org_id → list of (websocket, user_id) tuples
        self.org_connections: dict[int, list[tuple[WebSocket, int]]] = {}

    async def connect(self, ws: WebSocket, user_id: int, org_id: int):
        """Accept and register connection under the org."""

    async def disconnect(self, ws: WebSocket, user_id: int, org_id: int):
        """Remove connection from org group."""

    async def broadcast_to_org(
        self, org_id: int, event: dict, exclude_user_id: int | None = None
    ):
        """Send event to all org members, optionally excluding the actor."""

    async def send_to_user(self, user_id: int, event: dict):
        """Send event to a specific user (all their connections)."""
```

Key differences from existing `ConnectionManager`:
- **Grouped by org_id** (not just user_id)
- **`exclude_user_id`** parameter on broadcast (to skip the actor)
- **Singleton instance** importable by route handlers and workers

### 6.2 Backend: /ws/events Endpoint

**File**: `services/backend-api/src/api/routes/events_ws.py`

```
WS /ws/events?token={jwt}

Client → Server:
  { type: "ping" }                    # Client heartbeat (optional)

Server → Client:
  { type: "ping" }                    # Heartbeat every 30s
  {
    type: "event",
    event_type: "notification:new",   # Namespaced event type
    data: { ... },                    # Full payload
    timestamp: "2026-02-24T...",
    actor_user_id: 42                 # Who triggered it (for dedup)
  }
```

- **Auth**: JWT query param (same pattern as `/ws/copilot`)
- **Heartbeat**: 30-second ping interval
- **Idle timeout**: 10 minutes (longer than copilot since this is passive)
- **Reconnection**: Client handles via exponential backoff (1s → 30s)

### 6.3 Backend: Event Emission Helper

**File**: `services/backend-api/src/services/event_emitter.py`

```python
from src.services.event_connection_manager import event_manager

async def emit_event(
    org_id: int,
    event_type: str,
    data: dict,
    exclude_user_id: int | None = None,
):
    """Broadcast an event to all connected org members."""
    await event_manager.broadcast_to_org(
        org_id=org_id,
        event={
            "type": "event",
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        },
        exclude_user_id=exclude_user_id,
    )
```

Usage in route handlers:

```python
# In POST /api/v1/feedback/
@router.post("/")
async def create_feedback(...):
    feedback = ...  # create feedback
    db.commit()

    await emit_event(
        org_id=current_org.id,
        event_type="feedback:created",
        data={"id": feedback.id, "title": feedback.title, ...},
        exclude_user_id=current_user.id,  # skip the actor
    )
    return feedback
```

### 6.4 Backend: Worker Event Emission

Celery workers run in a separate process and can't directly access the async `EventConnectionManager`. Two options:

**Option A — HTTP callback (simpler)**:
Worker calls an internal REST endpoint after task completion:
```python
# In Celery task
requests.post("http://localhost:8000/api/internal/events/emit", json={
    "org_id": org_id,
    "event_type": "feedback:analyzed",
    "data": {...},
    "secret": INTERNAL_SECRET,
})
```

**Option B — Shared ConnectionManager via import** (if worker runs in same process):
Since the current setup uses `--reload` with uvicorn, the worker and API may share memory. If not, Option A is preferred.

**Recommendation**: Option A with an internal endpoint protected by a shared secret.

### 6.5 Frontend: RealtimeProvider

**File**: `services/frontend-web/contexts/RealtimeContext.tsx`

```typescript
interface RealtimeEvent {
  type: 'event';
  event_type: string;     // e.g. "notification:new"
  data: Record<string, unknown>;
  timestamp: string;
}

type EventHandler = (event: RealtimeEvent) => void;

interface RealtimeContextValue {
  connected: boolean;
  reconnecting: boolean;
  subscribe: (pattern: string, handler: EventHandler) => () => void;
}
```

- **Single WS connection** managed at app level (in dashboard layout)
- **Pattern matching**: `subscribe('notification:*', handler)` matches all notification events
- **Returns unsubscribe function** for cleanup in useEffect
- **Reconnection**: Exponential backoff (1s → 30s), same as copilot hook

### 6.6 Frontend: useRealtimeEvents Hook

**File**: `services/frontend-web/hooks/useRealtimeEvents.ts`

```typescript
export function useRealtimeEvents(
  pattern: string,
  handler: (event: RealtimeEvent) => void
): { connected: boolean; reconnecting: boolean }
```

Usage in components:

```typescript
// NotificationBell.tsx
const queryClient = useQueryClient();

useRealtimeEvents('notification:count', (event) => {
  // Direct update for simple count
  setUnreadCount(event.data.unread_count as number);
});

useRealtimeEvents('notification:*', () => {
  // Invalidate for full list refresh
  queryClient.invalidateQueries({ queryKey: ['notifications'] });
});
```

```typescript
// Feedbacks page
useRealtimeEvents('feedback:*', () => {
  queryClient.invalidateQueries({ queryKey: ['feedback'] });
});
```

### 6.7 Cache Invalidation Map

| Event Pattern | React Query Keys Invalidated |
|---------------|------------------------------|
| `notification:*` | `['notifications']` |
| `notification:count` | Direct state update (no refetch) |
| `activity:*` | `['activity-feed']`, `['team-activity']` |
| `feedback:created` | `['feedback']`, `['dashboard']`, `['activity-feed']` |
| `feedback:analyzed` | `['feedback']`, `['dashboard']` |
| `feedback:imported` | `['feedback']`, `['dashboard']`, `['activity-feed']` |
| `feedback:updated` | `['feedback']` |
| `feedback:deleted` | `['feedback']`, `['dashboard']` |
| `workflow:*` | `['workflow']`, `['activity-feed']` |

## 7. Files to Create

| File | Purpose |
|------|---------|
| `backend-api/src/services/event_connection_manager.py` | Per-org WebSocket connection tracking |
| `backend-api/src/services/event_emitter.py` | Helper to broadcast events from route handlers |
| `backend-api/src/api/routes/events_ws.py` | `/ws/events` WebSocket endpoint |
| `frontend-web/contexts/RealtimeContext.tsx` | React context provider for WS connection |
| `frontend-web/hooks/useRealtimeEvents.ts` | Hook for subscribing to event patterns |

## 8. Files to Modify

| File | Change |
|------|--------|
| `backend-api/src/api/main.py` | Register `/ws/events` route + internal events endpoint |
| `backend-api/src/api/routes/feedback.py` | Emit `feedback:created/updated/deleted` events |
| `backend-api/src/api/routes/workflow.py` | Emit `workflow:status_changed/assigned/note_added` events |
| `backend-api/src/api/routes/notifications.py` | Emit `notification:new/read/read_all/count` events |
| `backend-api/src/background/scheduler.py` or worker tasks | Emit `feedback:analyzed` after analysis |
| `frontend-web/app/(dashboard)/layout.tsx` | Wrap with `RealtimeProvider` |
| `frontend-web/components/NotificationBell.tsx` | Remove `setInterval`, add `useRealtimeEvents` |
| `frontend-web/components/dashboard/widgets/ActivityFeedWidget.tsx` | Remove `setInterval`, add `useRealtimeEvents` |
| `frontend-web/components/dashboard/hooks/useDashboardData.ts` | Remove `refetchInterval` from `useActivityFeed` |
| `frontend-web/app/(dashboard)/feedbacks/page.tsx` | Remove `refetchInterval`, add `useRealtimeEvents` |
| `frontend-web/app/(dashboard)/workflow/page.tsx` | Remove `refetchInterval`, add `useRealtimeEvents` |

## 9. Migration Plan

Since this is an all-at-once rollout:

1. **Build backend infrastructure** (EventConnectionManager, /ws/events, event_emitter)
2. **Add event emissions** to all relevant route handlers and worker tasks
3. **Build frontend infrastructure** (RealtimeContext, useRealtimeEvents hook)
4. **Migrate all 5 polling consumers** to use `useRealtimeEvents`
5. **Remove all polling code** (setInterval, refetchInterval)
6. **Test end-to-end** across multiple browser tabs / users

## 10. Testing Strategy

### Backend Tests
- `test_events_ws.py`: Connection auth, heartbeat, idle timeout, reconnection
- `test_event_connection_manager.py`: Org grouping, broadcast, exclude actor, cleanup
- `test_event_emitter.py`: Event emission from route handlers
- Update existing route handler tests to verify events are emitted

### Frontend Tests
- `RealtimeContext.test.tsx`: Provider mounting, WS lifecycle, reconnection
- `useRealtimeEvents.test.ts`: Pattern matching, subscribe/unsubscribe, handler invocation
- Update existing component tests: verify polling removed, verify invalidation on events
- Integration test: mock WS → push event → verify React Query invalidation → verify UI update

### Manual Testing
- Open 2 browser tabs with different org users
- Create feedback in tab 1 → verify it appears in tab 2's feedback list
- Change workflow status in tab 1 → verify kanban updates in tab 2
- Create notification → verify bell badge updates across all tabs
- Kill backend → verify frontend shows reconnecting state → restart → verify recovery

## 11. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| WS connection drops → stale data | Exponential backoff reconnection + refetchOnWindowFocus stays enabled as safety net |
| Too many events overwhelming clients | Batch/debounce events on frontend (e.g. coalesce multiple feedback:created within 500ms into one invalidation) |
| Worker can't access WS ConnectionManager | Internal HTTP endpoint for workers to trigger events |
| Memory leak from orphaned subscriptions | Subscribe returns unsubscribe fn, used in useEffect cleanup |
| Event ordering issues | Include timestamps; React Query refetch ensures consistency |

## 12. Success Metrics

- **Zero polling API calls** after migration (all 5 setInterval/refetchInterval removed)
- **< 1 second** latency from backend change to frontend update
- **Cross-user updates** work: changes by one org member appear for others instantly
- **No increase in error rates** after deployment
- **WS reconnection** recovers gracefully after network interruptions
