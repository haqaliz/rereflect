# PRD: Slack Integration

**Version**: 1.0
**Author**: Product Team
**Date**: 2026-01-31
**Status**: Draft - Pending Review

---

## Executive Summary

Enable Rereflect users to receive real-time feedback alerts in Slack, creating immediate value and driving daily engagement with the platform. This feature supports all Slack integration methods (Incoming Webhooks and OAuth App) with configurable triggers and customizable alert content.

---

## Problem Statement

### Current Pain Points
1. Users must manually check the dashboard to see new feedback
2. Urgent customer issues go unnoticed until the next login
3. No real-time visibility into customer sentiment for teams
4. Feedback analysis results aren't surfacing where teams actually work (Slack)

### User Stories
- *"As a CS Manager, I want to be alerted immediately when a customer expresses churn risk so I can intervene quickly."*
- *"As a Product Manager, I want daily feedback summaries in our #product channel so the team stays aligned."*
- *"As a Founder, I want to see every piece of negative feedback in real-time so nothing slips through."*

---

## Goals & Success Metrics

### Goals
1. **Immediate Value**: Users see feedback in Slack within 30 seconds of analysis completion
2. **Reduce Churn Risk**: Alert on urgent/negative feedback enables proactive intervention
3. **Increase Engagement**: Daily active engagement via Slack drives platform retention
4. **Flexibility**: Support multiple integration methods and configuration options

### Success Metrics
| Metric | Target | Measurement |
|--------|--------|-------------|
| Integration Setup Rate | 60% of orgs within 7 days | % of orgs with active Slack integration |
| Alert Delivery Time | < 30 seconds | Time from analysis complete → Slack message |
| Daily Active Slack Alerts | 5+ alerts/org/day | Average alerts sent per active org |
| Feature Retention | 80% still active after 30 days | % of integrations not disabled |

---

## Scope

### In Scope (v1.0)
- Slack Incoming Webhooks integration
- Slack OAuth App integration (channel picker)
- Configurable alert triggers per organization
- Customizable alert message fields
- Settings UI in dashboard
- Alert history/logs

### Out of Scope (Future)
- Discord integration (v1.1)
- Microsoft Teams integration (v1.2)
- Bi-directional Slack commands (v2.0)
- Thread replies to alerts (v2.0)
- Slack App Home tab (v2.0)

---

## User Experience

### Integration Setup Flow

#### Option A: Webhook URL (Simple)
```
1. User goes to Settings → Integrations → Slack
2. Clicks "Add Webhook"
3. Pastes Slack Incoming Webhook URL
4. Selects alert triggers (checkboxes)
5. Selects fields to include (checkboxes)
6. Clicks "Test & Save"
7. Receives test message in Slack
```

#### Option B: OAuth App (Rich)
```
1. User goes to Settings → Integrations → Slack
2. Clicks "Connect with Slack"
3. Redirected to Slack OAuth consent
4. Selects workspace and channel
5. Redirected back to Rereflect
6. Configures alert triggers and fields
7. Clicks "Save"
```

### Configuration Options

#### Alert Triggers (Checkboxes)
- [ ] **Urgent feedback** - Feedback flagged as urgent/churn risk
- [ ] **Negative sentiment** - Feedback with negative sentiment score
- [ ] **All new feedback** - Every analyzed feedback item
- [ ] **Daily digest** - Summary at configurable time (9 AM default)
- [ ] **Weekly digest** - Weekly summary (Monday 9 AM default)

#### Alert Fields (Customizable)
- [x] Feedback text (always included)
- [x] Sentiment label & score
- [ ] Pain point category
- [ ] Pain point severity
- [ ] Feature request (if detected)
- [ ] Urgency category
- [ ] Suggested response time
- [ ] Link to dashboard
- [ ] Customer info (if available)

### Alert Message Design

#### Real-time Alert (Urgent/Negative)
```
┌─────────────────────────────────────────────────────────┐
│ 🚨 Urgent Customer Feedback                             │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ "I've been waiting 3 days for support and still no     │
│ response. Considering switching to a competitor."       │
│                                                         │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│
│                                                         │
│ Sentiment: 🔴 Negative (-0.85)                         │
│ Category: Support Response Time                         │
│ Severity: Critical                                      │
│ Response Time: Immediate                                │
│                                                         │
│ [View in Dashboard]  [Mark Resolved]                    │
│                                                         │
│ via Rereflect • Today at 2:34 PM                       │
└─────────────────────────────────────────────────────────┘
```

#### Batch Alert (Multiple Items)
```
┌─────────────────────────────────────────────────────────┐
│ 📊 5 New Feedback Items Analyzed                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ 🔴 2 Negative  •  🟡 2 Neutral  •  🟢 1 Positive       │
│                                                         │
│ Top Issue: "Pricing" mentioned 3 times                  │
│                                                         │
│ [View All in Dashboard]                                 │
│                                                         │
│ via Rereflect • Today at 2:34 PM                       │
└─────────────────────────────────────────────────────────┘
```

#### Daily Digest
```
┌─────────────────────────────────────────────────────────┐
│ 📈 Daily Feedback Summary - Jan 31, 2026                │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Today's Stats:                                          │
│ • 47 feedback items analyzed                            │
│ • Sentiment: 62% positive, 28% neutral, 10% negative   │
│ • 3 urgent items requiring attention                    │
│                                                         │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│
│                                                         │
│ Top Pain Points:                                        │
│ 1. Mobile app performance (12 mentions)                 │
│ 2. Pricing concerns (8 mentions)                        │
│ 3. Missing dark mode (5 mentions)                       │
│                                                         │
│ Top Feature Requests:                                   │
│ 1. API access (7 requests)                              │
│ 2. Export to CSV (4 requests)                           │
│                                                         │
│ [View Full Report]                                      │
│                                                         │
│ via Rereflect • 9:00 AM                                │
└─────────────────────────────────────────────────────────┘
```

---

## Technical Design

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Settings → Integrations → Slack                          │   │
│  │  • Webhook URL input                                      │   │
│  │  • OAuth "Connect" button                                 │   │
│  │  • Trigger checkboxes                                     │   │
│  │  • Field selection                                        │   │
│  │  • Test button                                            │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Backend API                                │
│  ┌────────────────────┐  ┌────────────────────────────────────┐ │
│  │ /integrations/     │  │ /integrations/slack/oauth/         │ │
│  │   POST - Create    │  │   GET - Initiate OAuth             │ │
│  │   GET - List       │  │   GET /callback - OAuth callback   │ │
│  │   PATCH - Update   │  │                                    │ │
│  │   DELETE - Remove  │  │ /integrations/slack/test/          │ │
│  │                    │  │   POST - Send test message         │ │
│  └────────────────────┘  └────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Database                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  integrations table                                       │   │
│  │  • id, organization_id, type='slack'                     │   │
│  │  • config: {webhook_url, channel_id, triggers, fields}   │   │
│  │  • oauth_token (encrypted), is_active                    │   │
│  │  • created_at, last_used_at                              │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  slack_alert_logs table                                   │   │
│  │  • id, integration_id, feedback_id                       │   │
│  │  • status (sent, failed, pending)                        │   │
│  │  • sent_at, error_message                                │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Worker Service                               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Analysis Complete Event                                  │   │
│  │         │                                                 │   │
│  │         ▼                                                 │   │
│  │  Check Integration Triggers                               │   │
│  │         │                                                 │   │
│  │         ├── Urgent? → send_slack_alert.delay()           │   │
│  │         ├── Negative? → send_slack_alert.delay()         │   │
│  │         └── All? → send_slack_alert.delay()              │   │
│  │                                                           │   │
│  │  Celery Beat (scheduled):                                 │   │
│  │         ├── Daily digest (9 AM)                          │   │
│  │         └── Weekly digest (Monday 9 AM)                  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Database Schema

#### integrations table (update existing)
```sql
CREATE TABLE integrations (
    id SERIAL PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    type VARCHAR(50) NOT NULL,  -- 'slack', 'discord', etc.
    name VARCHAR(255),          -- User-defined name "Engineering Channel"

    -- Connection details
    config JSONB DEFAULT '{}',  -- {webhook_url, channel_id, channel_name}
    oauth_access_token TEXT,    -- Encrypted
    oauth_refresh_token TEXT,   -- Encrypted
    oauth_expires_at TIMESTAMP,

    -- Alert configuration
    triggers JSONB DEFAULT '["urgent"]',  -- ["urgent", "negative", "all", "daily_digest", "weekly_digest"]
    included_fields JSONB DEFAULT '["text", "sentiment"]',  -- Fields to include in alerts
    digest_time TIME DEFAULT '09:00:00',  -- Time for daily/weekly digest (UTC)

    -- Status
    is_active BOOLEAN DEFAULT true,
    last_used_at TIMESTAMP,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(organization_id, type, config->>'channel_id')
);
```

#### slack_alert_logs table (new)
```sql
CREATE TABLE slack_alert_logs (
    id SERIAL PRIMARY KEY,
    integration_id INTEGER NOT NULL REFERENCES integrations(id),
    feedback_id INTEGER REFERENCES feedback_items(id),  -- NULL for digests
    alert_type VARCHAR(50) NOT NULL,  -- 'urgent', 'negative', 'batch', 'daily_digest', 'weekly_digest'

    status VARCHAR(20) NOT NULL,  -- 'sent', 'failed', 'pending'
    slack_response JSONB,         -- Slack API response
    error_message TEXT,

    sent_at TIMESTAMP DEFAULT NOW(),

    INDEX(integration_id, sent_at)
);
```

### API Endpoints

#### GET /api/v1/integrations/
List all integrations for current organization.

**Response:**
```json
{
  "integrations": [
    {
      "id": 1,
      "type": "slack",
      "name": "Engineering Alerts",
      "channel_name": "#engineering",
      "triggers": ["urgent", "negative"],
      "included_fields": ["text", "sentiment", "pain_point_category"],
      "is_active": true,
      "last_used_at": "2026-01-31T14:30:00Z"
    }
  ]
}
```

#### POST /api/v1/integrations/slack/webhook/
Create webhook-based Slack integration.

**Request:**
```json
{
  "name": "Engineering Alerts",
  "webhook_url": "https://hooks.slack.com/services/T00/B00/XXX",
  "triggers": ["urgent", "negative"],
  "included_fields": ["text", "sentiment", "pain_point_category", "link"]
}
```

#### GET /api/v1/integrations/slack/oauth/
Initiate Slack OAuth flow.

**Response:**
```json
{
  "redirect_url": "https://slack.com/oauth/v2/authorize?client_id=...&scope=...&state=..."
}
```

#### GET /api/v1/integrations/slack/oauth/callback/
Handle OAuth callback from Slack.

#### POST /api/v1/integrations/slack/test/
Send a test message to verify integration.

**Request:**
```json
{
  "integration_id": 1
}
```

#### PATCH /api/v1/integrations/{id}/
Update integration settings.

#### DELETE /api/v1/integrations/{id}/
Remove integration.

### Slack App Configuration

#### Required Scopes (OAuth)
```
chat:write          - Post messages
channels:read       - List public channels
groups:read         - List private channels (optional)
incoming-webhook    - Webhook access
```

#### Slack App Manifest
```yaml
display_information:
  name: Rereflect
  description: Customer feedback alerts from Rereflect
  background_color: "#f97316"  # Sunset Horizon orange

features:
  bot_user:
    display_name: Rereflect
    always_online: true

oauth_config:
  scopes:
    bot:
      - chat:write
      - channels:read
      - incoming-webhook

settings:
  org_deploy_enabled: false
  socket_mode_enabled: false
```

---

## Implementation Plan

### Phase 1: Database & Backend (Week 1)

#### Day 1-2: Database Migration
- [ ] Create Alembic migration for `integrations` table updates
- [ ] Create `slack_alert_logs` table
- [ ] Add encryption for OAuth tokens (use Fernet)

#### Day 3-4: API Endpoints
- [ ] `POST /integrations/slack/webhook/` - Create webhook integration
- [ ] `GET /integrations/` - List integrations
- [ ] `PATCH /integrations/{id}/` - Update settings
- [ ] `DELETE /integrations/{id}/` - Remove integration
- [ ] `POST /integrations/slack/test/` - Send test message

#### Day 5: Worker Integration
- [ ] Update `process_unanalyzed_feedback` to check triggers after analysis
- [ ] Update `send_slack_alert` task with configurable fields
- [ ] Add alert logging

### Phase 2: OAuth & Rich Messages (Week 2)

#### Day 6-7: Slack OAuth
- [ ] Register Slack App in Slack API dashboard
- [ ] `GET /integrations/slack/oauth/` - Initiate flow
- [ ] `GET /integrations/slack/oauth/callback/` - Handle callback
- [ ] Store encrypted tokens
- [ ] Channel selection endpoint

#### Day 8-9: Enhanced Messages
- [ ] Rich Block Kit message formatting
- [ ] Customizable field rendering
- [ ] Action buttons (View in Dashboard)
- [ ] Batch message for multiple items

### Phase 3: Frontend UI (Week 3)

#### Day 10-12: Settings UI
- [ ] Integrations settings page
- [ ] Slack integration card component
- [ ] Webhook URL form
- [ ] OAuth "Connect with Slack" button
- [ ] Trigger checkboxes
- [ ] Field selection UI
- [ ] Test button with feedback

#### Day 13-14: Polish & Testing
- [ ] Integration status indicators
- [ ] Error handling UI
- [ ] Alert history view
- [ ] E2E tests
- [ ] Documentation

### Phase 4: Digests (Week 4)

#### Day 15-16: Daily/Weekly Digests
- [ ] Celery Beat schedule for digests
- [ ] Digest message template
- [ ] Aggregation queries (top pain points, trends)
- [ ] Timezone handling for digest time

#### Day 17-18: Testing & Launch
- [ ] Load testing (100 orgs sending alerts)
- [ ] Failure handling (retry, circuit breaker)
- [ ] Monitoring (alert latency, failure rate)
- [ ] Documentation update
- [ ] Feature announcement

---

## Technical Considerations

### Rate Limiting
- Slack webhooks: 1 request/second per webhook
- Batch multiple feedback items into single message when possible
- Queue messages and send with delay if hitting limits

### Error Handling
- Retry failed webhooks 3 times with exponential backoff
- Disable integration after 10 consecutive failures
- Notify user via email when integration disabled

### Security
- Encrypt OAuth tokens at rest (Fernet encryption)
- Validate webhook URLs (must be hooks.slack.com)
- Rate limit test message endpoint (5/minute/org)
- CSRF protection on OAuth callback

### Performance
- Alert sending is async (Celery task)
- Batch alerts when multiple items analyzed together
- Cache integration configs (Redis, 5-minute TTL)

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Slack API changes | Low | High | Use official SDK, monitor deprecations |
| Webhook URL abuse | Medium | Medium | Validate URL format, rate limit |
| Alert fatigue | Medium | High | Default to "urgent only", clear settings |
| OAuth token expiry | Medium | Medium | Refresh token flow, notify on failure |

---

## Future Enhancements (v2.0)

1. **Bi-directional commands**: `/rereflect status` in Slack
2. **Thread replies**: Reply to alert to add notes
3. **Slack App Home**: Dashboard view in Slack
4. **Interactive buttons**: Mark resolved directly from Slack
5. **Smart batching**: AI-powered grouping of related feedback
6. **Scheduled reports**: Custom report schedules

---

## Appendix

### Competitor Analysis

| Feature | Rereflect | Productboard | Canny | Intercom |
|---------|-----------|--------------|-------|----------|
| Webhook support | ✅ | ✅ | ✅ | ✅ |
| OAuth app | ✅ | ❌ | ✅ | ✅ |
| Custom triggers | ✅ | ❌ | ❌ | ✅ |
| Custom fields | ✅ | ❌ | ❌ | ❌ |
| Digests | ✅ | ✅ | ❌ | ✅ |
| AI categorization | ✅ | ❌ | ❌ | ❌ |

### Slack Block Kit Reference
- [Block Kit Builder](https://app.slack.com/block-kit-builder)
- [Message Formatting](https://api.slack.com/reference/surfaces/formatting)
- [OAuth Flow](https://api.slack.com/authentication/oauth-v2)

---

**Document Status**: Draft
**Next Review**: Pending user approval
**Approvals Required**: Product Owner, Engineering Lead
