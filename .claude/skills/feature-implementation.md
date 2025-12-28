# Feature Implementation Skill

Use this skill when implementing specific features from the roadmap.

## Process

### 1. Planning Phase

Before writing any code:

1. **Read the requirement** from [PRD.md](../../PRD.md) or [ROADMAP.md](../../ROADMAP.md)
2. **Check current codebase** - What exists? What can be reused?
3. **Design the solution**:
   - Database schema changes needed?
   - API endpoints needed?
   - Frontend components needed?
   - Background jobs needed?
4. **Identify dependencies** - What must be built first?
5. **Create task list** - Break into small, testable chunks

### 2. Implementation Phase

**Order of implementation**:
1. Database schema (migrations)
2. Backend models (SQLAlchemy/Pydantic)
3. API endpoints (FastAPI routes)
4. Background jobs (if needed)
5. Frontend components
6. Integration tests
7. Documentation

### 3. Testing Phase

**Must have**:
- Unit tests for business logic
- Integration tests for API endpoints
- Frontend component tests (if applicable)
- Manual testing checklist

### 4. Documentation Phase

**Update**:
- API documentation (OpenAPI/Swagger)
- User documentation (if user-facing)
- Code comments (for complex logic)
- Changelog entry

## Example: Implementing Slack Integration

### Step 1: Plan

**Goal**: Send urgent feedback alerts to Slack

**Requirements** (from PRD):
- Slack integration (webhook setup)
- Alert configuration UI (sentiment threshold, keywords)
- Urgent feedback Slack notifications

**Design**:
- Database: `integrations` table (store webhook URL)
- API: POST /api/v1/integrations/slack
- Background: Alert service checks urgent feedback every 5 min
- Frontend: Integration settings page

### Step 2: Database Schema

```python
# Create migration
alembic revision -m "Add integrations table"

# migrations/versions/002_add_integrations.py
def upgrade():
    op.create_table(
        'integrations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),  # 'slack', 'zendesk', etc
        sa.Column('config', sa.JSON(), nullable=False),  # webhook_url, api_key, etc
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'])
    )
    op.create_index('ix_integrations_org', 'integrations', ['organization_id'])

def downgrade():
    op.drop_table('integrations')
```

### Step 3: Backend Models

```python
# src/models/integration.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime

class Integration(Base):
    __tablename__ = "integrations"

    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    type = Column(String, nullable=False)  # 'slack', 'zendesk', etc
    config = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    organization = relationship("Organization", back_populates="integrations")

# Pydantic models
from pydantic import BaseModel, HttpUrl

class SlackIntegrationCreate(BaseModel):
    webhook_url: HttpUrl

class IntegrationResponse(BaseModel):
    id: int
    type: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
```

### Step 4: API Endpoints

```python
# src/api/routes/integrations.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import httpx

router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])

@router.post("/slack", response_model=IntegrationResponse)
async def create_slack_integration(
    data: SlackIntegrationCreate,
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Connect Slack workspace for alerts."""

    # Test webhook URL
    async with httpx.AsyncClient() as client:
        try:
            test_message = {
                "text": "🎉 Slack integration successfully connected!"
            }
            response = await client.post(str(data.webhook_url), json=test_message)
            response.raise_for_status()
        except httpx.HTTPError:
            raise HTTPException(
                status_code=400,
                detail="Invalid Slack webhook URL. Please check and try again."
            )

    # Save integration
    integration = Integration(
        organization_id=org.id,
        type="slack",
        config={"webhook_url": str(data.webhook_url)},
        is_active=True
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)

    return integration

@router.get("/", response_model=List[IntegrationResponse])
async def list_integrations(
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """List all integrations for this organization."""
    integrations = db.query(Integration).filter(
        Integration.organization_id == org.id
    ).all()
    return integrations

@router.delete("/{integration_id}")
async def delete_integration(
    integration_id: int,
    org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db)
):
    """Disconnect an integration."""
    integration = db.query(Integration).filter(
        Integration.id == integration_id,
        Integration.organization_id == org.id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    db.delete(integration)
    db.commit()

    return {"status": "deleted"}
```

### Step 5: Background Job (Alert Service)

```python
# src/services/alert_service.py
import httpx
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

async def send_urgent_feedback_alerts():
    """Check for urgent feedback and send Slack alerts."""
    db = SessionLocal()

    try:
        # Get all active Slack integrations
        integrations = db.query(Integration).filter(
            Integration.type == "slack",
            Integration.is_active == True
        ).all()

        for integration in integrations:
            # Get urgent feedback from last 5 minutes (not yet alerted)
            five_min_ago = datetime.utcnow() - timedelta(minutes=5)

            urgent_feedback = db.query(FeedbackItem).filter(
                FeedbackItem.organization_id == integration.organization_id,
                FeedbackItem.is_urgent == True,
                FeedbackItem.created_at >= five_min_ago,
                FeedbackItem.alerted_at == None  # Not yet alerted
            ).all()

            if urgent_feedback:
                await send_slack_message(
                    webhook_url=integration.config["webhook_url"],
                    feedback_items=urgent_feedback
                )

                # Mark as alerted
                for item in urgent_feedback:
                    item.alerted_at = datetime.utcnow()

                db.commit()

    finally:
        db.close()

async def send_slack_message(webhook_url: str, feedback_items: List[FeedbackItem]):
    """Send formatted message to Slack."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🚨 {len(feedback_items)} Urgent Feedback Alert(s)"
            }
        }
    ]

    for item in feedback_items[:5]:  # Max 5 per message
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Issue:* {item.extracted_issue}\n*Sentiment:* {item.sentiment_label}\n*Source:* {item.source}"
            }
        })
        blocks.append({"type": "divider"})

    message = {
        "blocks": blocks,
        "text": f"{len(feedback_items)} urgent feedback items need attention"
    }

    async with httpx.AsyncClient() as client:
        await client.post(webhook_url, json=message)

# Celery task
from celery import Celery

celery_app = Celery('tasks', broker='redis://localhost:6379')

@celery_app.task
def check_urgent_alerts():
    """Run every 5 minutes."""
    import asyncio
    asyncio.run(send_urgent_feedback_alerts())

# In celerybeat_schedule.py
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'check-urgent-alerts': {
        'task': 'src.services.alert_service.check_urgent_alerts',
        'schedule': 300.0,  # Every 5 minutes
    },
}
```

### Step 6: Frontend Component

```typescript
// app/integrations/slack/page.tsx
'use client'

import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { toast } from '@/components/ui/use-toast'

const slackSchema = z.object({
  webhook_url: z.string().url('Must be a valid URL')
    .startsWith('https://hooks.slack.com/', 'Must be a Slack webhook URL')
})

type SlackForm = z.infer<typeof slackSchema>

export default function SlackIntegrationPage() {
  const [isConnecting, setIsConnecting] = useState(false)

  const { register, handleSubmit, formState: { errors } } = useForm<SlackForm>({
    resolver: zodResolver(slackSchema)
  })

  const onSubmit = async (data: SlackForm) => {
    setIsConnecting(true)

    try {
      const response = await fetch('/api/v1/integrations/slack', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail)
      }

      toast({
        title: "Success!",
        description: "Slack integration connected. Check your channel for a test message.",
      })

    } catch (error) {
      toast({
        title: "Error",
        description: error instanceof Error ? error.message : "Failed to connect Slack",
        variant: "destructive"
      })
    } finally {
      setIsConnecting(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-8">
      <h1 className="text-3xl font-bold mb-2">Connect Slack</h1>
      <p className="text-gray-600 mb-8">
        Get real-time alerts when urgent feedback arrives
      </p>

      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-6">
        <h3 className="font-semibold mb-2">📝 How to get your webhook URL:</h3>
        <ol className="list-decimal list-inside space-y-1 text-sm">
          <li>Go to <a href="https://api.slack.com/apps" className="text-blue-600 underline" target="_blank">api.slack.com/apps</a></li>
          <li>Create a new app or select existing</li>
          <li>Enable "Incoming Webhooks"</li>
          <li>Add new webhook to workspace</li>
          <li>Copy the webhook URL and paste below</li>
        </ol>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-2">
            Webhook URL
          </label>
          <Input
            {...register('webhook_url')}
            placeholder="https://hooks.slack.com/services/..."
            disabled={isConnecting}
          />
          {errors.webhook_url && (
            <p className="text-red-500 text-sm mt-1">{errors.webhook_url.message}</p>
          )}
        </div>

        <Button type="submit" disabled={isConnecting}>
          {isConnecting ? 'Connecting...' : 'Connect Slack'}
        </Button>
      </form>
    </div>
  )
}
```

### Step 7: Tests

```python
# tests/test_slack_integration.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

def test_create_slack_integration_success(client: TestClient, auth_headers: dict):
    """Test successful Slack integration creation."""

    with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200

        response = client.post(
            "/api/v1/integrations/slack",
            json={"webhook_url": "https://hooks.slack.com/services/TEST"},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "slack"
        assert data["is_active"] == True

def test_create_slack_integration_invalid_url(client: TestClient, auth_headers: dict):
    """Test with invalid webhook URL."""

    with patch('httpx.AsyncClient.post', new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.HTTPError("Invalid URL")

        response = client.post(
            "/api/v1/integrations/slack",
            json={"webhook_url": "https://hooks.slack.com/services/INVALID"},
            headers=auth_headers
        )

        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()

@pytest.mark.asyncio
async def test_urgent_alert_service():
    """Test urgent feedback alert service."""
    # Create test data
    org = create_test_organization()
    integration = create_test_integration(org.id, "slack")
    urgent_feedback = create_test_feedback(org.id, is_urgent=True)

    with patch('src.services.alert_service.send_slack_message') as mock_send:
        await send_urgent_feedback_alerts()

        # Verify Slack message was sent
        mock_send.assert_called_once()
        args = mock_send.call_args
        assert len(args[0][1]) == 1  # One urgent feedback
        assert args[0][1][0].id == urgent_feedback.id
```

### Step 8: Documentation

```markdown
# Slack Integration

## Setup

1. Go to Settings → Integrations
2. Click "Connect Slack"
3. Follow instructions to get webhook URL
4. Paste URL and click "Connect"
5. Check your Slack channel for confirmation message

## How It Works

- Checks for urgent feedback every 5 minutes
- Sends alert to configured Slack channel
- Includes feedback details and sentiment
- Max 5 alerts per message

## Alert Criteria

Feedback is marked as urgent if:
- Sentiment score < -0.7 (very negative)
- Contains churn indicators ("cancel", "switching")
- Mentions critical issues (data loss, security)
- Part of sudden spike (5+ similar issues)

## Customization

Configure alert rules in Settings → Alerts:
- Sentiment threshold
- Keywords to watch
- Alert frequency
- Quiet hours

## Troubleshooting

**Not receiving alerts?**
- Check webhook URL is correct
- Verify Slack app has permissions
- Ensure integration is Active
- Check Usage logs for errors
```

## Feature Template Checklist

When implementing any feature:

- [ ] Database migration created and tested
- [ ] Backend models defined (SQLAlchemy + Pydantic)
- [ ] API endpoints implemented
- [ ] Authentication/authorization added
- [ ] Input validation implemented
- [ ] Error handling complete
- [ ] Background jobs configured (if needed)
- [ ] Frontend UI implemented
- [ ] Form validation added (frontend)
- [ ] Loading/error states handled
- [ ] Unit tests written (>80% coverage)
- [ ] Integration tests written
- [ ] API documentation updated
- [ ] User documentation added
- [ ] Changelog entry created
- [ ] Code review requested
- [ ] Manual testing completed
- [ ] Performance tested
- [ ] Security reviewed

## Common Patterns by Feature Type

### Integration Feature
1. Database: `integrations` table entry
2. API: POST /integrations/{type}
3. Service: Pull/push data from external API
4. UI: OAuth flow or API key input
5. Background: Sync job (Celery task)

### Analytics Feature
1. Database: Aggregate query or materialized view
2. API: GET /analytics/{metric}
3. Cache: Redis for expensive queries
4. UI: Chart component (recharts, victory)
5. Background: Pre-compute daily (if expensive)

### Workflow Feature
1. Database: Status field + audit log
2. API: PATCH /resource/{id}/status
3. Service: State machine logic
4. UI: Status badges + action buttons
5. Background: Scheduled status changes

### Notification Feature
1. Database: `notification_preferences` table
2. API: Webhook or email service
3. Service: Template rendering
4. UI: Notification settings page
5. Background: Queue + batch sending

## When to Use This Skill

Use when implementing:
- New user-facing features
- API endpoints
- Database changes
- Background jobs
- Frontend components
- Third-party integrations
