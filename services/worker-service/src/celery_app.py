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
        "src.tasks.classifier_training",
        "src.tasks.usage_metrics",
        "src.tasks.segments",
        "src.tasks.hubspot_sync",
        "src.tasks.hubspot_writeback",
        "src.tasks.salesforce_sync",
        "src.tasks.salesforce_writeback",
        "src.tasks.zendesk_sync",
        "src.tasks.jira_sync",
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
    # Retrain per-org sentiment corrections classifier — Mondays 06:30 UTC
    # (uncrowded slot: before generate-churn-insights at 07:00. Folds in
    # purge_old_classifier_models after the loop — no separate beat slot.)
    "retrain-classifier-weekly": {
        "task": "src.tasks.classifier_training.retrain_all_orgs",
        "schedule": crontab(hour=6, minute=30, day_of_week=1),
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
    # Recompute usage scores daily so recency decays without new events — 04:00 UTC
    "recompute-usage-scores-daily": {
        "task": "src.tasks.usage_metrics.recompute_usage_scores",
        "schedule": crontab(hour=4, minute=0),
    },
    # Recompute customer segments daily so time-based segments (dormant,
    # silent_churner, new) flip without new activity — 04:15 UTC, after
    # usage scores (04:00 UTC).
    "recompute-segments-daily": {
        "task": "src.tasks.segments.recompute_segments",
        "schedule": crontab(hour=4, minute=15),
    },
    # Sync HubSpot CRM data daily at 03:15 UTC — between integrations (02:00) and usage (04:00)
    # (03:00 is occupied by refit-global-calibration-daily)
    "sync-hubspot-daily": {
        "task": "src.tasks.hubspot_sync.sync_all_hubspot",
        "schedule": crontab(hour=3, minute=15),
    },
    # Sync Salesforce CRM data daily at 03:45 UTC — avoids 03:00 (global
    # calibration) and 03:15 (hubspot sync).
    "sync-salesforce-daily": {
        "task": "src.tasks.salesforce_sync.sync_all_salesforce",
        "schedule": crontab(hour=3, minute=45),
    },
    # Poll Zendesk incremental tickets every 15 minutes (ingestion-pull
    # aspect — see docs/planning/zendesk-integration/ingestion-pull/plan_20260705.md
    # Phase 5). Fixed-interval cadence (not a specific wall-clock crontab
    # time), same style as process-unanalyzed-feedback's 30.0.
    "sync-zendesk-every-15-min": {
        "task": "src.tasks.zendesk_sync.sync_all_zendesk",
        "schedule": 900.0,  # every 15 minutes
    },
    # Poll Jira issue status every 15 minutes (jira-status-sync/inbound-status-sync
    # aspect — see docs/planning/jira-status-sync/inbound-status-sync/plan_20260711.md
    # Phase 4). Fixed-interval cadence, same style as sync-zendesk-every-15-min.
    "sync-jira-status-every-15-min": {
        "task": "src.tasks.jira_sync.sync_all_jira",
        "schedule": 900.0,  # every 15 minutes
    },
}


if __name__ == "__main__":
    celery_app.start()
