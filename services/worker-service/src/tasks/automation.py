"""
Celery tasks for AI Workflow Automation (M4.4).

Currently contains:
- purge_old_automation_executions: weekly retention purge (90-day window)
"""

import logging
from datetime import datetime, timedelta

from celery import shared_task

from src.database import get_db_session

logger = logging.getLogger(__name__)

EXECUTION_RETENTION_DAYS = 90


@shared_task
def purge_old_automation_executions() -> dict:
    """
    Celery Beat task: delete AutomationExecution records older than 90 days.

    Runs weekly on Sunday at 02:30 UTC (registered in celery_app.py).
    Safe to run multiple times — idempotent DELETE with a cutoff timestamp.

    Returns:
        dict with {"status": "complete", "deleted": N}
    """
    from src.models.automation_execution import AutomationExecution

    cutoff = datetime.utcnow() - timedelta(days=EXECUTION_RETENTION_DAYS)

    with get_db_session() as db:
        deleted = (
            db.query(AutomationExecution)
            .filter(AutomationExecution.executed_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()

    logger.info(
        "purge_old_automation_executions: deleted %d records older than %s",
        deleted, cutoff.date(),
    )

    return {"status": "complete", "deleted": deleted}
