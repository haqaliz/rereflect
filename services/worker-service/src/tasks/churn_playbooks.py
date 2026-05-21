"""
Celery tasks for churn playbook execution — Phase 5.2 (M4.1).

Tasks:
    run_playbook(execution_id)     — Execute a ChurnPlaybookExecution.
    purge_old_executions()         — Delete execution rows older than 90 days.

Beat schedule entries (registered in celery_app.py):
    purge-playbook-executions: Sundays 03:00 UTC
"""

import logging
from datetime import datetime, timedelta

from celery import shared_task

from src.database import get_db_session
from src.services import playbook_engine
from src.services.playbook_engine import EXECUTION_RETENTION_DAYS

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="tasks.churn_playbooks.run_playbook")
def run_playbook(self, execution_id: int) -> dict:
    """
    Execute a ChurnPlaybookExecution by id.

    Delegates to playbook_engine.execute().  If the engine raises unexpectedly,
    the exception is caught, the execution is marked failed within the same DB
    session, and a structured error dict is returned (no re-raise).

    Returns:
        dict — {"status": ..., "action_log": [...]}
                or {"status": "error", "error": "..."} on unexpected failure.
    """
    from src.models import ChurnPlaybookExecution

    with get_db_session() as db:
        try:
            result = playbook_engine.execute(execution_id, db)
            return result
        except Exception as exc:
            logger.exception(
                "run_playbook: unhandled exception for execution_id=%s: %s",
                execution_id, exc,
            )
            # Best-effort: mark execution failed using the same open session
            try:
                execution = db.query(ChurnPlaybookExecution).filter_by(id=execution_id).first()
                if execution and execution.status in ("queued", "running"):
                    execution.status = "failed"
                    execution.error_message = f"task error: {exc}"
                    execution.completed_at = datetime.utcnow()
                    db.commit()
            except Exception as inner_exc:
                logger.error(
                    "run_playbook: failed to mark execution %s as failed: %s",
                    execution_id, inner_exc,
                )

            return {"status": "error", "error": str(exc)}


@shared_task(name="tasks.churn_playbooks.purge_old_executions")
def purge_old_executions() -> dict:
    """
    Delete ChurnPlaybookExecution rows older than 90 days.

    Runs weekly on Sundays at 03:00 UTC (registered in celery_app.py beat_schedule).
    Safe to run multiple times — idempotent DELETE with cutoff timestamp.

    Returns:
        dict — {"status": "complete", "deleted": N}
    """
    from src.models import ChurnPlaybookExecution

    cutoff = datetime.utcnow() - timedelta(days=EXECUTION_RETENTION_DAYS)

    with get_db_session() as db:
        deleted = (
            db.query(ChurnPlaybookExecution)
            .filter(ChurnPlaybookExecution.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()

    logger.info(
        "purge_old_executions: deleted %d ChurnPlaybookExecution rows older than %s",
        deleted, cutoff.date(),
    )

    return {"status": "complete", "deleted": deleted}
