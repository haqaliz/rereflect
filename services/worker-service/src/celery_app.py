"""
Celery application configuration.
Uses Redis Streams as the message broker.
"""

import sys
import os

# Add analysis-engine/src to Python path
analysis_engine_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../analysis-engine/src"))
if analysis_engine_path not in sys.path:
    sys.path.insert(0, analysis_engine_path)

# ---------------------------------------------------------------------------
# Sentry error tracking (free tier)
# ---------------------------------------------------------------------------
import sentry_sdk

sentry_sdk.init(
    dsn="https://2b2ca3ad26940c13fbf60d94b877505a@o4511048843788288.ingest.us.sentry.io/4511050724737024",
    send_default_pii=True,
    traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
    environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
)

from celery import Celery
from celery.schedules import crontab

from src.config import CELERY_BROKER_URL, CELERY_BACKEND_URL, settings

# Create Celery app
celery_app = Celery(
    "customer_feedback_worker",
    broker=CELERY_BROKER_URL,
    backend=CELERY_BACKEND_URL,
    include=[
        "src.tasks.analysis",
        "src.tasks.alerts",
        "src.tasks.integrations",
        "src.tasks.source_events",
        "src.tasks.anomaly",
        "src.tasks.insights",
        "src.tasks.workflow",
        "src.tasks.webhook_delivery",
        "src.tasks.automation",
        "src.tasks.churn_playbooks",
        "src.tasks.churn_calibration",
    ],
)

# Celery configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_acks_late=True,  # Acknowledge after task completes (reliability)
    task_reject_on_worker_lost=True,  # Requeue if worker dies
    task_time_limit=settings.analysis_timeout,

    # Worker configuration
    worker_prefetch_multiplier=4,  # Fetch 4 tasks at a time
    worker_concurrency=4,  # 4 concurrent workers per process

    # Result backend
    result_expires=3600,  # Results expire after 1 hour

    # Retry configuration
    task_default_retry_delay=settings.retry_delay,
    task_max_retries=settings.max_retries,

    # Redis-specific optimizations
    broker_transport_options={
        "visibility_timeout": 3600,  # 1 hour visibility timeout
        "fanout_prefix": True,
        "fanout_patterns": True,
    },
)

# Periodic task schedule (Celery Beat)
celery_app.conf.beat_schedule = {
    # Process unanalyzed feedback every 30 seconds
    "process-unanalyzed-feedback": {
        "task": "src.tasks.analysis.process_unanalyzed_feedback",
        "schedule": 30.0,
    },
    # Check for urgent alerts every 5 minutes
    "check-urgent-alerts": {
        "task": "src.tasks.alerts.check_urgent_alerts",
        "schedule": 300.0,
    },
    # Sync integrations daily at 2 AM
    "sync-integrations-daily": {
        "task": "src.tasks.integrations.sync_all_integrations",
        "schedule": crontab(hour=2, minute=0),
    },
    # Weekly digest: Every hour at :05, task filters by user's preferred day+hour
    "send-weekly-digests": {
        "task": "src.tasks.alerts.send_weekly_digests",
        "schedule": crontab(minute=5),
    },
    # Retry LLM analysis for items that fell back to keyword analysis
    "retry-llm-analysis": {
        "task": "src.tasks.analysis.retry_llm_analysis",
        "schedule": 300.0,  # Every 5 minutes
    },
    # Detect sentiment anomalies every hour
    "detect-sentiment-anomalies": {
        "task": "src.tasks.anomaly.detect_sentiment_anomalies",
        "schedule": crontab(minute=0),  # Top of every hour
    },
    # Generate churn insights for at-risk customers: Every Monday at 7 AM UTC
    "generate-churn-insights": {
        "task": "src.tasks.insights.generate_churn_insights",
        "schedule": crontab(hour=7, minute=0, day_of_week=1),
    },
    # Generate retention insights for moderate customers: Every Monday at 7:15 AM (bi-weekly)
    "generate-retention-insights": {
        "task": "src.tasks.insights.generate_retention_insights",
        "schedule": crontab(hour=7, minute=15, day_of_week=1),
    },
    # Generate growth insights for healthy customers: Every Monday at 7:30 AM (monthly)
    "generate-growth-insights": {
        "task": "src.tasks.insights.generate_growth_insights",
        "schedule": crontab(hour=7, minute=30, day_of_week=1),
    },
    # Generate weekly AI insights: Every Monday at 8:30 AM UTC (before digest at 9 AM)
    "generate-weekly-insights": {
        "task": "src.tasks.insights.generate_weekly_insights",
        "schedule": crontab(hour=8, minute=30, day_of_week=1),
    },
    # Check for feedback volume spikes every hour
    "check-volume-spikes": {
        "task": "src.tasks.alerts.check_volume_spikes",
        "schedule": crontab(minute=30),  # At 30 minutes past every hour
    },
    # Daily alert digest: Every hour at :00, task filters by user's preferred hour
    "send-daily-alert-digests": {
        "task": "src.tasks.alerts.send_daily_alert_digests",
        "schedule": crontab(minute=0),
    },
    # Cleanup expired notifications daily at 3:30 AM UTC
    "cleanup-expired-notifications": {
        "task": "src.tasks.alerts.cleanup_expired_notifications",
        "schedule": crontab(hour=3, minute=30),
    },
    # Auto-assign unassigned feedback every 60 seconds
    "auto-assign-unassigned-feedback": {
        "task": "src.tasks.workflow.auto_assign_unassigned_feedback",
        "schedule": 60.0,
    },
    # Purge webhook delivery logs older than 30 days — weekly on Sunday at 2:15 AM
    "purge-old-webhook-deliveries": {
        "task": "src.tasks.webhook_delivery.purge_old_webhook_deliveries",
        "schedule": crontab(hour=2, minute=15, day_of_week=0),
    },
    # Purge automation execution logs older than 90 days — weekly on Sunday at 2:30 AM
    "purge-old-automation-executions": {
        "task": "src.tasks.automation.purge_old_automation_executions",
        "schedule": crontab(hour=2, minute=30, day_of_week=0),
    },
    # Purge churn playbook execution logs older than 90 days — Sundays 03:00 UTC
    "purge-playbook-executions": {
        "task": "tasks.churn_playbooks.purge_old_executions",
        "schedule": crontab(hour=3, minute=0, day_of_week=0),
    },
    # Refit per-org churn calibration models — Mondays 07:45 UTC
    "refit-churn-calibration-weekly": {
        "task": "src.tasks.churn_calibration.refit_all_orgs",
        "schedule": crontab(hour=7, minute=45, day_of_week=1),
    },
    # Refit global churn calibration model — Daily 03:00 UTC
    "refit-global-calibration-daily": {
        "task": "src.tasks.churn_calibration.refit_global_calibration",
        "schedule": crontab(hour=3, minute=0),
    },
    # Purge old (inactive, >90d) calibration models — Sundays 03:30 UTC
    "purge-old-calibration-models": {
        "task": "src.tasks.churn_calibration.purge_old_calibration_models",
        "schedule": crontab(hour=3, minute=30, day_of_week=0),
    },
}


if __name__ == "__main__":
    celery_app.start()
