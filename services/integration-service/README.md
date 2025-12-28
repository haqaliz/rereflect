# Integration Service

**Third-party API connectors for Customer Feedback Analyzer**

---

## Purpose

Manages integrations with external platforms:
- **Intercom**: Pull customer conversations
- **Zendesk**: Pull support tickets
- **Slack**: Send alerts and notifications
- **Salesforce**: Pull cases and feedback
- **HubSpot**: Pull customer interactions
- **App Store Connect**: Pull iOS reviews
- **Google Play Console**: Pull Android reviews
- **Generic Webhook**: Receive feedback via webhook

---

## Tech Stack

- **Language**: Python 3.9+
- **HTTP Client**: httpx (async support)
- **OAuth**: authlib
- **Rate Limiting**: Custom rate limiter
- **Storage**: PostgreSQL (integration configs)
- **Cache**: Redis (API response cache)

---

## Quick Start

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set environment variables
export INTERCOM_CLIENT_ID=...
export ZENDESK_CLIENT_ID=...

# Run connector test
python src/connectors/intercom.py
```

---

## Supported Integrations

### 1. Intercom

**What it does**: Pull customer conversations from Intercom

**API**: https://developers.intercom.com/docs/references/rest-api

**Config**:
```json
{
  "access_token": "dG9rOjEyMzQ1...",
  "workspace_id": "abc123"
}
```

**Connector**:
```python
# src/connectors/intercom.py
from .base import BaseConnector
import httpx

class IntercomConnector(BaseConnector):
    base_url = "https://api.intercom.io"

    async def fetch_new_items(self, since: datetime):
        headers = {
            "Authorization": f"Bearer {self.config['access_token']}",
            "Accept": "application/json"
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/conversations",
                headers=headers,
                params={
                    "updated_since": int(since.timestamp()),
                    "per_page": 150
                }
            )
            response.raise_for_status()
            data = response.json()

        # Transform to feedback items
        items = []
        for conversation in data["conversations"]:
            items.append({
                "text": self._extract_text(conversation),
                "created_at": datetime.fromtimestamp(conversation["created_at"]),
                "external_id": conversation["id"],
                "metadata": {
                    "customer_email": conversation["contacts"]["email"],
                    "tags": conversation["tags"]
                }
            })

        return items
```

---

### 2. Zendesk

**What it does**: Pull support tickets from Zendesk

**API**: https://developer.zendesk.com/api-reference/

**Config**:
```json
{
  "subdomain": "yourcompany",
  "email": "admin@yourcompany.com",
  "api_token": "abc123..."
}
```

**Connector**:
```python
# src/connectors/zendesk.py
class ZendeskConnector(BaseConnector):
    @property
    def base_url(self):
        return f"https://{self.config['subdomain']}.zendesk.com/api/v2"

    async def fetch_new_items(self, since: datetime):
        auth = (f"{self.config['email']}/token", self.config['api_token'])

        async with httpx.AsyncClient(auth=auth) as client:
            response = await client.get(
                f"{self.base_url}/tickets.json",
                params={
                    "updated_since": since.isoformat(),
                    "per_page": 100
                }
            )
            data = response.json()

        items = []
        for ticket in data["tickets"]:
            # Get ticket comments
            comments = await self._fetch_comments(ticket["id"])

            items.append({
                "text": self._combine_text(ticket, comments),
                "created_at": datetime.fromisoformat(ticket["created_at"]),
                "external_id": str(ticket["id"]),
                "metadata": {
                    "priority": ticket["priority"],
                    "status": ticket["status"],
                    "tags": ticket["tags"]
                }
            })

        return items
```

---

### 3. Slack (Outbound)

**What it does**: Send alerts to Slack channels

**API**: Incoming Webhooks

**Config**:
```json
{
  "webhook_url": "https://hooks.slack.com/services/T00/B00/XXX"
}
```

**Connector**:
```python
# src/connectors/slack.py
class SlackConnector(BaseConnector):
    async def send_alert(self, feedback_items: list):
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚨 {len(feedback_items)} Urgent Feedback Alert(s)"
                }
            }
        ]

        for item in feedback_items[:5]:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Issue:* {item.extracted_issue}\n*Sentiment:* {item.sentiment_label}\n*Source:* {item.source}"
                }
            })

        async with httpx.AsyncClient() as client:
            await client.post(
                self.config["webhook_url"],
                json={"blocks": blocks}
            )
```

---

### 4. App Store Connect (iOS Reviews)

**What it does**: Pull iOS app reviews

**API**: App Store Connect API

**Config**:
```json
{
  "issuer_id": "abc-123",
  "key_id": "KEY123",
  "private_key": "-----BEGIN PRIVATE KEY-----\n..."
}
```

---

### 5. Google Play Console (Android Reviews)

**What it does**: Pull Android app reviews

**API**: Google Play Developer API

**Config**:
```json
{
  "package_name": "com.yourapp",
  "service_account_json": "{...}"
}
```

---

## Base Connector

All connectors inherit from `BaseConnector`:

```python
# src/connectors/base.py
from abc import ABC, abstractmethod
from datetime import datetime

class BaseConnector(ABC):
    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    async def fetch_new_items(self, since: datetime) -> list[dict]:
        """Fetch new feedback items since the given datetime."""
        pass

    async def test_connection(self) -> bool:
        """Test if the integration is configured correctly."""
        try:
            items = await self.fetch_new_items(since=datetime.utcnow())
            return True
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False

    def _extract_text(self, item: dict) -> str:
        """Extract text from API response (override if needed)."""
        pass

    def validate_config(self) -> bool:
        """Validate required config fields."""
        required = self.required_fields()
        return all(field in self.config for field in required)

    @classmethod
    def required_fields(cls) -> list[str]:
        """Return list of required config fields."""
        return []
```

---

## OAuth Flow

For integrations requiring OAuth (Intercom, Salesforce, HubSpot):

```python
# src/oauth/intercom.py
from authlib.integrations.starlette_client import OAuth

oauth = OAuth()

oauth.register(
    name='intercom',
    client_id=INTERCOM_CLIENT_ID,
    client_secret=INTERCOM_CLIENT_SECRET,
    authorize_url='https://app.intercom.com/oauth',
    authorize_params=None,
    access_token_url='https://api.intercom.io/auth/eagle/token',
    access_token_params=None,
    client_kwargs={'scope': 'conversations.read'}
)

# In backend-api route:
@app.get('/api/v1/integrations/intercom/authorize')
async def authorize_intercom(request: Request):
    redirect_uri = request.url_for('intercom_callback')
    return await oauth.intercom.authorize_redirect(request, redirect_uri)

@app.get('/api/v1/integrations/intercom/callback')
async def intercom_callback(request: Request):
    token = await oauth.intercom.authorize_access_token(request)

    # Save token to database
    integration = Integration(
        organization_id=current_org.id,
        type='intercom',
        config={'access_token': token['access_token']}
    )
    db.add(integration)
    db.commit()

    return RedirectResponse('/integrations?success=intercom')
```

---

## Rate Limiting

Many APIs have rate limits. Handle with backoff:

```python
# src/utils/rate_limiter.py
import asyncio
from datetime import datetime, timedelta

class RateLimiter:
    def __init__(self, max_requests: int, period: timedelta):
        self.max_requests = max_requests
        self.period = period
        self.requests = []

    async def acquire(self):
        now = datetime.utcnow()

        # Remove old requests
        self.requests = [r for r in self.requests if r > now - self.period]

        if len(self.requests) >= self.max_requests:
            # Wait until oldest request expires
            sleep_time = (self.requests[0] + self.period - now).total_seconds()
            await asyncio.sleep(sleep_time)

        self.requests.append(now)

# Usage
limiter = RateLimiter(max_requests=100, period=timedelta(minutes=1))

async def fetch_with_limit():
    await limiter.acquire()
    response = await client.get(...)
```

---

## Webhook Receiver

For generic webhook integrations:

```python
# In backend-api
@app.post('/api/v1/webhooks/{org_id}/{secret_token}')
async def receive_webhook(
    org_id: int,
    secret_token: str,
    payload: dict
):
    # Validate token
    org = db.query(Organization).get(org_id)
    if org.webhook_token != secret_token:
        raise HTTPException(status_code=403, detail="Invalid token")

    # Extract feedback from payload
    feedback = FeedbackItem(
        organization_id=org_id,
        text=payload.get("text"),
        source="webhook",
        metadata=payload
    )
    db.add(feedback)
    db.commit()

    # Queue analysis
    analyze_feedback_batch.delay(org_id, [feedback.id])

    return {"status": "received"}
```

---

## Testing

```bash
# Test specific connector
python -m pytest tests/test_connectors.py::test_intercom_connector -v

# Mock API responses
@patch('httpx.AsyncClient.get')
async def test_intercom_fetch(mock_get):
    mock_get.return_value.json.return_value = {
        "conversations": [{"id": "123", "created_at": 1234567890}]
    }

    connector = IntercomConnector(config={"access_token": "test"})
    items = await connector.fetch_new_items(since=datetime(2024, 1, 1))

    assert len(items) == 1
```

---

## Environment Variables

```bash
# OAuth credentials
INTERCOM_CLIENT_ID=...
INTERCOM_CLIENT_SECRET=...
ZENDESK_CLIENT_ID=...
ZENDESK_CLIENT_SECRET=...
SALESFORCE_CLIENT_ID=...
SALESFORCE_CLIENT_SECRET=...

# API keys
APP_STORE_CONNECT_KEY_ID=...
GOOGLE_PLAY_SERVICE_ACCOUNT=...
```

---

## Deployment

**Runs as part of worker-service** or as standalone service

**Docker**:
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ ./src/

# If standalone API
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8002"]

# If background jobs only (called by worker-service)
# No CMD needed
```

---

## Support

- **Intercom API**: https://developers.intercom.com
- **Zendesk API**: https://developer.zendesk.com
- **Slack Webhooks**: https://api.slack.com/messaging/webhooks
- **Development Guide**: [/.claude/skills/feature-implementation.md](/.claude/skills/feature-implementation.md)

---

**Status**: In Development (Month 2)
**Version**: 0.1.0
**Maintained**: Yes
