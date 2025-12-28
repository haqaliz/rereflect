# Worker Service

**Background job processing for Customer Feedback Analyzer**

---

## Purpose

Handles asynchronous tasks:
- **Batch analysis**: Analyze large feedback uploads in background
- **Alert service**: Check for urgent feedback every 5 minutes
- **Integration sync**: Pull data from Intercom, Zendesk daily
- **Scheduled reports**: Generate and email weekly/monthly reports
- **Data cleanup**: Delete old data based on retention policies

---

## Tech Stack

- **Task Queue**: Celery 5.3+
- **Broker**: Redis 7.0+
- **Backend**: Redis (result storage)
- **Language**: Python 3.9+
- **Dependencies**: Same as analysis-engine

---

## Quick Start

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start Redis (required)
redis-server

# Run worker
celery -A src.celery_app worker --loglevel=info

# Run scheduler (for periodic tasks)
celery -A src.celery_app beat --loglevel=info

# Run both (worker + scheduler)
celery -A src.celery_app worker --beat --loglevel=info
```

---

## Tasks

### 1. Analyze Feedback Batch

**Task**: `analyze_feedback_batch(org_id, feedback_ids)`

**Purpose**: Analyze uploaded feedback files in background

**Trigger**: Backend API after file upload

**Example**:
```python
from src.tasks.analysis import analyze_feedback_batch

# Queue the task
result = analyze_feedback_batch.delay(org_id=123, feedback_ids=[1, 2, 3, 4, 5])

# Check status
result.ready()  # True if complete
result.get()    # Get result (blocks until complete)
```

**Implementation**:
```python
# src/tasks/analysis.py
from celery import shared_task
from src.analyzer import FeedbackAnalyzer

@shared_task
def analyze_feedback_batch(org_id: int, feedback_ids: list[int]):
    # Get feedback from database
    feedback_items = db.query(FeedbackItem).filter(
        FeedbackItem.organization_id == org_id,
        FeedbackItem.id.in_(feedback_ids)
    ).all()

    # Analyze
    analyzer = FeedbackAnalyzer()
    result = analyzer.analyze(feedback_items)

    # Save results to database
    save_analysis_results(org_id, result)

    return {"status": "success", "analyzed": len(feedback_ids)}
```

---

### 2. Check Urgent Alerts

**Task**: `check_urgent_alerts()`

**Purpose**: Send Slack alerts for urgent feedback

**Schedule**: Every 5 minutes

**Example**:
```python
# src/tasks/alerts.py
from celery import shared_task
import httpx

@shared_task
def check_urgent_alerts():
    # Get all active Slack integrations
    integrations = db.query(Integration).filter(
        Integration.type == "slack",
        Integration.is_active == True
    ).all()

    for integration in integrations:
        # Get urgent feedback (not yet alerted)
        urgent = db.query(FeedbackItem).filter(
            FeedbackItem.organization_id == integration.organization_id,
            FeedbackItem.is_urgent == True,
            FeedbackItem.alerted_at == None
        ).all()

        if urgent:
            send_slack_message(integration.config["webhook_url"], urgent)

            # Mark as alerted
            for item in urgent:
                item.alerted_at = datetime.utcnow()
            db.commit()

    return {"integrations_checked": len(integrations)}
```

---

### 3. Sync Integrations

**Task**: `sync_integration(integration_id)`

**Purpose**: Pull new data from 3rd party APIs

**Schedule**: Daily (configurable per integration)

**Example**:
```python
# src/tasks/integrations.py
from celery import shared_task
from src.connectors import IntercomConnector, ZendeskConnector

@shared_task
def sync_integration(integration_id: int):
    integration = db.query(Integration).get(integration_id)

    # Get connector
    if integration.type == "intercom":
        connector = IntercomConnector(integration.config)
    elif integration.type == "zendesk":
        connector = ZendeskConnector(integration.config)
    else:
        raise ValueError(f"Unknown integration type: {integration.type}")

    # Pull new conversations/tickets
    new_items = connector.fetch_new_items(since=integration.last_synced_at)

    # Save to database
    for item in new_items:
        feedback = FeedbackItem(
            organization_id=integration.organization_id,
            text=item.text,
            source=integration.type,
            created_at=item.created_at
        )
        db.add(feedback)

    # Update last synced
    integration.last_synced_at = datetime.utcnow()
    db.commit()

    # Queue analysis
    feedback_ids = [f.id for f in new_items]
    analyze_feedback_batch.delay(integration.organization_id, feedback_ids)

    return {"synced": len(new_items)}
```

---

### 4. Generate Scheduled Reports

**Task**: `generate_scheduled_report(org_id, report_type)`

**Purpose**: Generate and email weekly/monthly reports

**Schedule**: Weekly (Monday 9am), Monthly (1st of month)

**Example**:
```python
# src/tasks/reports.py
from celery import shared_task
from src.reports import generate_pdf_report
from src.email import send_email

@shared_task
def generate_scheduled_report(org_id: int, report_type: str):
    # Get organization settings
    org = db.query(Organization).get(org_id)

    # Generate report
    pdf_data = generate_pdf_report(org_id, report_type)

    # Send email
    recipients = org.report_recipients  # Email list from settings
    send_email(
        to=recipients,
        subject=f"{report_type.capitalize()} Feedback Report",
        body="Your scheduled feedback report is attached.",
        attachments=[("report.pdf", pdf_data)]
    )

    return {"status": "sent", "recipients": len(recipients)}
```

---

## Celery Configuration

```python
# src/celery_app.py
from celery import Celery
from celery.schedules import crontab

celery_app = Celery(
    'customer_feedback',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
)

# Periodic task schedule
celery_app.conf.beat_schedule = {
    'check-urgent-alerts-every-5-min': {
        'task': 'src.tasks.alerts.check_urgent_alerts',
        'schedule': 300.0,  # 5 minutes
    },
    'sync-integrations-daily': {
        'task': 'src.tasks.integrations.sync_all_integrations',
        'schedule': crontab(hour=2, minute=0),  # 2 AM daily
    },
    'generate-weekly-reports': {
        'task': 'src.tasks.reports.generate_weekly_reports',
        'schedule': crontab(day_of_week=1, hour=9, minute=0),  # Monday 9 AM
    },
}
```

---

## Monitoring

### Flower (Celery monitoring UI)

```bash
# Install Flower
pip install flower

# Run Flower
celery -A src.celery_app flower --port=5555

# Visit
open http://localhost:5555
```

**Flower Dashboard**:
- Active/completed/failed tasks
- Task runtime statistics
- Worker status
- Task graphs

---

## Error Handling

**Retry Logic**:
```python
@shared_task(bind=True, max_retries=3)
def analyze_feedback_batch(self, org_id, feedback_ids):
    try:
        # Task logic
        pass
    except Exception as exc:
        # Retry in 60 seconds
        raise self.retry(exc=exc, countdown=60)
```

**Dead Letter Queue**:
- Failed tasks after max retries go to DLQ
- Manual review and requeue
- Alert on critical failures

---

## Performance

- **Throughput**: 100 tasks/second (single worker)
- **Concurrency**: 10 workers (configurable)
- **Task timeout**: 10 minutes (analysis tasks)
- **Memory**: ~200MB per worker

**Scaling**:
```bash
# Run multiple workers
celery -A src.celery_app worker --concurrency=20

# Multiple machines
celery -A src.celery_app worker --hostname=worker1@%h
celery -A src.celery_app worker --hostname=worker2@%h
```

---

## Testing

```bash
# Unit tests
pytest tests/ -v

# Integration tests (requires Redis)
pytest tests/test_tasks.py -v

# Test specific task
pytest tests/test_tasks.py::test_analyze_feedback_batch -v
```

**Mock Example**:
```python
import pytest
from unittest.mock import patch

@patch('src.tasks.analysis.FeedbackAnalyzer')
def test_analyze_feedback_batch(mock_analyzer):
    mock_analyzer.return_value.analyze.return_value = {"status": "success"}

    result = analyze_feedback_batch(org_id=1, feedback_ids=[1, 2, 3])

    assert result["status"] == "success"
    mock_analyzer.return_value.analyze.assert_called_once()
```

---

## Deployment

**Docker**:
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ ./src/

CMD ["celery", "-A", "src.celery_app", "worker", "--loglevel=info"]
```

**Kubernetes**: See `/infrastructure/kubernetes/worker-service.yaml`

**Scaling**:
- Horizontal: Add more worker pods
- Vertical: Increase concurrency per worker
- Autoscaling: Based on queue length

---

## Environment Variables

```bash
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql://user:pass@localhost/customer_feedback_saas
ANALYSIS_ENGINE_URL=http://analysis-engine:8001
SLACK_RATE_LIMIT=1  # Max 1 message/second
```

---

## Support

- **Celery Docs**: https://docs.celeryq.dev
- **Development Guide**: [/.claude/skills/saas-development.md](/.claude/skills/saas-development.md)
- **Feature Implementation**: [/.claude/skills/feature-implementation.md](/.claude/skills/feature-implementation.md)

---

**Status**: In Development (Month 2)
**Version**: 0.1.0
**Maintained**: Yes
