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
        "src.tasks.billing",
        "src.tasks.anomaly",
        "src.tasks.insights",
        "src.tasks.workflow",
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
    # Billing: Check for expired trials daily at 3 AM
    "check-trial-expirations": {
        "task": "billing.check_trial_expirations",
        "schedule": crontab(hour=3, minute=0),
    },
    # Billing: Send trial ending reminders daily at 9 AM
    "send-trial-ending-reminders": {
        "task": "billing.send_trial_ending_reminder",
        "schedule": crontab(hour=9, minute=0),
    },
    # Billing: Report overages to Stripe hourly
    "report-overages-to-stripe": {
        "task": "billing.report_overages_to_stripe",
        "schedule": crontab(minute=15),  # At 15 minutes past every hour
    },
    # Billing: Check usage warnings daily at 10 AM
    "check-usage-warnings": {
        "task": "billing.check_usage_warnings",
        "schedule": crontab(hour=10, minute=0),
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
}


if __name__ == "__main__":
    celery_app.start()
