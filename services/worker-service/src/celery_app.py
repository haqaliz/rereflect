"""
Celery application configuration.
Uses Redis Streams as the message broker.
"""

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
}


if __name__ == "__main__":
    celery_app.start()
