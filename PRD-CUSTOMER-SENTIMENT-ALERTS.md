# PRD: Customer Sentiment Alerts

**Product**: Rereflect
**Author**: Rereflect Team
**Date**: 2026-02-20
**Timeline**: 1 week (Feb 21 - Feb 28, 2026)
**Status**: Draft
**Milestone**: AI-TRACKING M1.3

---

## 1. Overview

Proactively alert users when a customer's health score deteriorates. Today, users must manually check the Customer 360 page or dashboard widget to discover at-risk customers. This feature triggers automatic notifications when health scores drop below thresholds, decline by a significant number of points, or when a customer's risk level downgrades — surfacing churn risk before it's too late.

### Current State
- `CustomerHealth` model exists with 4-component weighted scores and risk levels (healthy/moderate/at_risk/critical)
- Health scores are recomputed inline after each feedback analysis in `update_customer_health()`
- `CustomerHealthHistory` records score changes (≥2 point delta)
- Notification system supports 7 alert types with per-user preferences (channels: in-app, email, Slack)
- Alert dispatch engine (`notification_dispatch.py`) handles org-wide and targeted notifications
- Alert preferences UI exists on settings page with per-type rows (toggle + channels + threshold)
- No alert type currently monitors health score changes

### Success Criteria
- Users receive in-app, email, and/or Slack alerts when a customer's health score drops significantly
- Risk level downgrades (e.g., healthy→moderate) always trigger alerts regardless of threshold config
- Risk level upgrades (e.g., at_risk→moderate) trigger positive recovery notifications
- 24h per-customer deduplication prevents alert fatigue during bulk imports
- Alert links to Customer 360 profile and auto-triggers LLM analysis if stale (>24h)
- Configurable per-user thresholds (absolute threshold + point-drop amount)
- Feature gated to Pro+ (same as customer health scores)
- Zero new Alembic migrations — uses existing schema

---

## 2. Data Model

### 2.1 No Schema Changes Required

The existing models are sufficient:

**UserAlertPreference** already supports:
- `alert_type = "customer_health_drop"` (string, arbitrary)
- `threshold_value` (float) — used for the absolute threshold (default: 50)
- `is_enabled`, `channel_email`, `channel_slack`, `channel_inapp`
- `retention_days` for notification expiry

**Notification** already supports:
- `type = "customer_health_drop"` (string)
- `metadata` (JSON) — stores score details, risk level, component breakdown
- `link` — Customer 360 URL
- `expires_at` — based on retention preference

### 2.2 Threshold Encoding

Since `UserAlertPreference` has a single `threshold_value` column, encode both values:

| Field | Storage | Default |
|-------|---------|---------|
| Absolute threshold | `threshold_value` | `50.0` |
| Point-drop amount | `metadata` JSON on the preference | `15.0` |

The preference's `threshold_value` stores the absolute threshold (alert when score drops below X). The point-drop amount is stored as JSON in the notification `metadata` or, more practically, as a convention: the alert dispatch code reads `threshold_value` for the absolute threshold and uses a fixed default for the drop amount (15 points), allowing future per-user configuration.

**Alternative approach** (preferred for simplicity): Use `threshold_value` for the absolute threshold. Store the drop amount as a second key in the alert preferences API response, derived from a `drop_threshold` field added to the preferences API schema (not the DB — computed from a JSON config column or a convention).

**Chosen approach**: Extend the preferences API to accept and return `drop_threshold` alongside `threshold_value` for `customer_health_drop` type only. On the backend, store `drop_threshold` in a JSON `extra_config` approach: use the existing `threshold_value` for absolute threshold and encode drop amount in Notification metadata at dispatch time. The drop threshold default of 15 is applied in the dispatch logic when no user preference overrides it.

### 2.3 Deduplication Strategy

Use **Redis** (DB 2, same as cache) to track per-customer alert cooldowns:

```
Key:    health_alert_cooldown:{org_id}:{customer_email}
Value:  {last_alerted_score}
TTL:    86400 (24 hours)
```

**Logic**:
1. Before dispatching, check if cooldown key exists
2. If exists: only re-alert if new score < last alerted score (score dropped further)
3. If not exists: dispatch alert and set cooldown key
4. Risk level downgrades always bypass cooldown (critical transitions must never be suppressed)

---

## 3. Alert Trigger Logic

### 3.1 Trigger Point

**File**: `services/backend-api/src/services/health_score_service.py` → `update_customer_health()`

Insert alert check after the score comparison (around line 120 where old vs new score is compared):

```python
# After computing new health_score and before saving
old_score = existing_record.health_score  # or None if new customer
old_risk_level = existing_record.risk_level
new_score = health_score
new_risk_level = risk_level

# Check if alert should fire
if old_score is not None:
    _check_health_drop_alert(
        org_id=org_id,
        customer_email=customer_email,
        customer_name=existing_record.customer_name,
        old_score=old_score,
        new_score=new_score,
        old_risk_level=old_risk_level,
        new_risk_level=new_risk_level,
        components={
            "churn_risk": churn_component,
            "sentiment": sentiment_component,
            "resolution": resolution_component,
            "frequency": frequency_component,
        },
        db=db,
    )
```

### 3.2 Alert Conditions

An alert fires when **any** of these conditions are met:

| Condition | Description | Dedup Bypass |
|-----------|-------------|--------------|
| **Threshold crossing** | `new_score < user.threshold_value` AND `old_score >= user.threshold_value` | No |
| **Point drop** | `old_score - new_score >= drop_threshold` (default 15) | No |
| **Risk level downgrade** | `new_risk_level` is worse than `old_risk_level` (healthy→moderate, moderate→at_risk, at_risk→critical) | Yes |
| **Risk level upgrade** (recovery) | `new_risk_level` is better than `old_risk_level` | Yes (separate alert) |

**Risk level ordering** (for comparison):
```python
RISK_LEVEL_ORDER = {"healthy": 0, "moderate": 1, "at_risk": 2, "critical": 3}
```

### 3.3 Recovery Alerts

When a customer's risk level **improves** (e.g., at_risk→moderate):
- Dispatch with `alert_type = "customer_health_drop"` but with `metadata.is_recovery = true`
- Title: "Customer health improved: {customer_email}"
- Message: "Health score recovered from {old_score} to {new_score} ({old_risk_level} → {new_risk_level})"
- Same channels as health drop alerts (uses same preference row)
- No deduplication (recovery alerts are rare and always welcome)

### 3.4 Auto-Trigger LLM Analysis

When a health drop alert is dispatched (not recovery):
1. Check `existing_record.llm_analyzed_at`
2. If `None` or older than 24 hours: queue `generate_churn_insights` Celery task for this customer
3. This ensures the Customer 360 profile has fresh AI analysis when the user clicks through

---

## 4. Alert Dispatch

### 4.1 Dispatch Function

**File**: `services/worker-service/src/notification_dispatch.py` (or a new helper in the same directory)

```python
def dispatch_health_drop_alert(
    org_id: int,
    customer_email: str,
    customer_name: Optional[str],
    old_score: int,
    new_score: int,
    old_risk_level: str,
    new_risk_level: str,
    components: Dict[str, int],
    is_recovery: bool = False,
) -> Dict[str, int]:
```

**Flow**:
1. Check Redis dedup (skip if cooldown active and score hasn't dropped further, unless risk level change)
2. Check plan gate: org must have `customer_health_scores` feature (Pro+)
3. Fetch all org users' `UserAlertPreference` for `alert_type = "customer_health_drop"`
4. For each user with `is_enabled = True`:
   - Evaluate threshold conditions against user's `threshold_value` and drop amount
   - Create `Notification` record (in-app channel)
   - Queue Slack message (Slack channel)
   - Flag for email digest (email channel)
5. Set Redis cooldown key with new score
6. Return dispatch counts

### 4.2 Notification Metadata

```json
{
    "customer_email": "john@acme.com",
    "customer_name": "John Smith",
    "old_score": 65,
    "new_score": 42,
    "old_risk_level": "moderate",
    "new_risk_level": "at_risk",
    "is_recovery": false,
    "components": {
        "churn_risk": 78,
        "sentiment": 35,
        "resolution": 60,
        "frequency": 45
    },
    "top_risk_drivers": ["churn_risk", "sentiment"]
}
```

### 4.3 Notification Content

**Drop Alert**:
- **Title**: "Customer health drop: {customer_email}"
- **Message**: "Health score dropped from {old_score} to {new_score} ({old_risk_level} → {new_risk_level}). Top risk drivers: {driver1}, {driver2}."
- **Link**: `/customers/{encoded_email}`

**Recovery Alert**:
- **Title**: "Customer health improved: {customer_email}"
- **Message**: "Health score recovered from {old_score} to {new_score} ({old_risk_level} → {new_risk_level})."
- **Link**: `/customers/{encoded_email}`

---

## 5. Slack Block Kit Message

### 5.1 Drop Alert Template

```json
{
    "blocks": [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "⚠️ Customer Health Drop",
                "emoji": true
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": "*Customer:*\njohn@acme.com"
                },
                {
                    "type": "mrkdwn",
                    "text": "*Risk Level:*\n🔴 at_risk"
                },
                {
                    "type": "mrkdwn",
                    "text": "*Score Change:*\n65 → 42 (-23)"
                },
                {
                    "type": "mrkdwn",
                    "text": "*Top Risk Drivers:*\nChurn Risk (78), Sentiment (35)"
                }
            ]
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View Customer Profile"
                    },
                    "url": "https://app.rereflect.com/customers/john%40acme.com",
                    "style": "primary"
                }
            ]
        }
    ]
}
```

### 5.2 Recovery Alert Template

Same structure but with green styling:
- Header: "✅ Customer Health Improved"
- Risk level badge shows the improved level
- Score change shows positive delta

---

## 6. Email Digest Integration

### 6.1 Digest Format

Customer health drop alerts appear in daily/weekly digests alongside other alert types.

**Digest entry format** (headline + top 2 risk drivers):
```
Customer Health Drop: john@acme.com
Score: 65 → 42 (at_risk) | Top risks: Churn Risk (78), Sentiment (35)
[View Customer →]
```

Recovery alerts:
```
Customer Health Improved: john@acme.com
Score: 42 → 58 (moderate) | Previously at_risk
[View Customer →]
```

### 6.2 Digest Aggregation

If multiple customers have health drops in the same digest window:
- Group under a "Customer Health Alerts" section
- Sort by severity (largest score drops first)
- Cap at 10 customers per digest (link to notifications page for more)

---

## 7. Alert Preferences UI

### 7.1 Settings Page Update

**File**: `services/frontend-web/app/(dashboard)/settings/notifications/page.tsx`

Add a new row in the existing alert preferences table:

| Alert Type | Enabled | In-App | Slack | Email | Threshold |
|------------|---------|--------|-------|-------|-----------|
| ... existing rows ... | | | | | |
| Customer Health Drop | Toggle | ✓ | ✓ | ✓ | Score < `[50]`, Drop ≥ `[15]` pts |

**Threshold controls** (unique to this alert type):
- **Absolute threshold**: Number input, label "Alert when score drops below", default 50, range 1-99
- **Drop threshold**: Number input, label "Alert on drop of", suffix "or more points", default 15, range 5-50

Both controls appear inline when the alert type is expanded/configured.

### 7.2 Default Preferences

When a user has no `UserAlertPreference` record for `customer_health_drop`:

| Field | Default |
|-------|---------|
| `is_enabled` | `true` |
| `channel_inapp` | `true` |
| `channel_slack` | `true` |
| `channel_email` | `false` |
| `threshold_value` | `50.0` |
| Drop threshold | `15` (applied in dispatch logic) |
| `retention_days` | `30` |

---

## 8. Plan Gating

| Feature | Free | Pro | Business | Enterprise |
|---------|------|-----|----------|------------|
| Customer health drop alerts | - | Yes | Yes | Yes |
| Configurable thresholds | - | Yes | Yes | Yes |
| Recovery notifications | - | Yes | Yes | Yes |
| Auto-trigger LLM analysis | - | Yes | Yes | Yes |

**Feature ID**: `customer_health_scores` (existing — no new feature ID needed)

The alert type row in preferences UI is hidden for Free plan users (same as the Customer 360 page).

---

## 9. Implementation Phases

### Phase 1: Backend Alert Dispatch (2 days)

**Files to modify**:
- `services/backend-api/src/services/health_score_service.py` — Add alert trigger check in `update_customer_health()`
- `services/worker-service/src/notification_dispatch.py` — Add `dispatch_health_drop_alert()` function
- `services/worker-service/src/tasks/analysis.py` — Queue LLM analysis on health drop (if stale)

**New files**:
- None (all logic fits in existing files)

**Tasks**:
1. Add `_check_health_drop_alert()` to `health_score_service.py`
   - Compare old vs new score and risk level
   - Determine which conditions are met (threshold, drop, risk change, recovery)
   - Call dispatch function
2. Add `dispatch_health_drop_alert()` to `notification_dispatch.py`
   - Redis dedup check (24h cooldown per customer per org)
   - Plan gate check (`customer_health_scores` feature)
   - Fetch user preferences for `customer_health_drop`
   - Create notifications, queue Slack, flag email digest
   - Set Redis cooldown key
3. Add Slack Block Kit template for health drop/recovery
4. Queue `generate_churn_insights` task when health drop alert fires and LLM analysis is stale

### Phase 2: Preferences API Extension (1 day)

**Files to modify**:
- `services/backend-api/src/api/routes/notifications.py` — Handle `customer_health_drop` type in preferences endpoints, return `drop_threshold` in response

**Tasks**:
1. Add `customer_health_drop` to the alert types list in the preferences API
2. Extend GET preferences response to include `drop_threshold` field for this type (default 15)
3. Extend PUT preferences to accept `drop_threshold` for this type
4. Store drop threshold: use `threshold_value` for absolute threshold, add drop threshold logic in dispatch (read from preference or use default)

### Phase 3: Frontend Preferences UI (1 day)

**Files to modify**:
- `services/frontend-web/app/(dashboard)/settings/notifications/page.tsx` — Add new alert type row with dual threshold controls

**Tasks**:
1. Add "Customer Health Drop" row to alert preferences table
2. Add inline threshold controls (absolute threshold input + drop amount input)
3. Wire up to preferences API (GET/PUT)
4. Hide row for Free plan users
5. Show defaults when no preference exists

### Phase 4: Notification Display (1 day)

**Files to modify**:
- `services/frontend-web/app/(dashboard)/notifications/page.tsx` — Handle `customer_health_drop` type in notification list
- `services/frontend-web/components/NotificationBell.tsx` (or equivalent) — Render health drop notifications in popover

**Tasks**:
1. Add icon and color for `customer_health_drop` type in notification list (red for drops, green for recovery)
2. Render score change and risk level in notification detail
3. Ensure "View Customer" link navigates to `/customers/{email}`
4. Add `customer_health_drop` to notification type filter dropdown

### Phase 5: Testing (1 day)

**Backend tests**:
- `_check_health_drop_alert()`: threshold crossing, point drop, risk downgrade, risk upgrade (recovery), no alert when conditions not met
- `dispatch_health_drop_alert()`: dedup (24h cooldown, re-alert on further drop, bypass on risk change), plan gating, channel dispatch
- Preferences API: GET/PUT with `drop_threshold`

**Frontend tests**:
- Preferences UI: render new row, threshold inputs, plan gating visibility
- Notification list: render health drop type with correct icon/color

---

## 10. Risk & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Alert fatigue from bulk CSV imports | High — hundreds of health recalculations at once | 24h Redis cooldown per customer; risk level downgrades bypass but are naturally limited |
| Health score service becomes slow with dispatch logic | Medium — dispatch involves DB queries + Redis | Dispatch is async-safe; consider queuing via Celery if latency is noticeable |
| Redis unavailable | Low — dedup fails, alerts may duplicate | Graceful fallback: if Redis is down, skip dedup and dispatch (better to over-alert than miss) |
| Stale LLM analysis not regenerated | Low — auto-trigger may fail silently | Log errors, analysis is still accessible manually from Customer 360 |

---

## 11. Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `services/backend-api/src/services/health_score_service.py` | Modify | Add alert trigger check |
| `services/worker-service/src/notification_dispatch.py` | Modify | Add `dispatch_health_drop_alert()` |
| `services/worker-service/src/tasks/analysis.py` | Modify | Queue LLM analysis on health drop |
| `services/backend-api/src/api/routes/notifications.py` | Modify | Handle new alert type in preferences API |
| `services/frontend-web/app/(dashboard)/settings/notifications/page.tsx` | Modify | Add alert type row with threshold controls |
| `services/frontend-web/app/(dashboard)/notifications/page.tsx` | Modify | Render health drop notifications |

---

## 12. Success Metrics

| Metric | Target |
|--------|--------|
| Alert delivery latency (from score change to notification) | < 5 seconds (in-app), < 30 seconds (Slack) |
| False positive rate (alerts for insignificant changes) | < 5% (threshold + dedup should filter noise) |
| User engagement (click-through from alert to Customer 360) | > 60% |
| Recovery alert accuracy (customer actually improved) | 100% (based on score, deterministic) |

---

## Related

- [AI-TRACKING.md](AI-TRACKING.md) — M1.3 milestone
- [PRD-CUSTOMER-360.md](PRD-CUSTOMER-360.md) — Customer 360 page (dependency, completed)
- [PRD-PREDICTIVE-ANALYTICS.md](PRD-PREDICTIVE-ANALYTICS.md) — Health score model origin
