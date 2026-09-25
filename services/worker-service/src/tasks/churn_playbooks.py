"""
Celery tasks for churn playbook execution — Phase 5.2 (M4.1).

Tasks:
    run_playbook(execution_id)     — Execute a ChurnPlaybookExecution.
    purge_old_executions()         — Delete execution rows older than 90 days.
    reap_stale_executions()        — Re-publish / fail executions stranded at queued/running.

Beat schedule entries (registered in celery_app.py):
    purge-playbook-executions: Sundays 03:00 UTC
    reap-stale-playbook-executions: every 10 minutes
"""

import logging
from datetime import datetime, timedelta

from celery import shared_task

from src.database import get_db_session
from src.services import playbook_engine
from src.services.playbook_engine import EXECUTION_RETENTION_DAYS

logger = logging.getLogger(__name__)

# Reaper thresholds (playbook-execution-reaper R2)
QUEUED_STALE_MINUTES = 15          # queued longer than this → dispatch presumed lost
QUEUED_MAX_REDISPATCH_HOURS = 24   # older than this → fail instead of re-running stale plays
RUNNING_STALE_HOURS = 1            # running longer than this → worker presumed dead
REAP_BATCH_LIMIT = 500             # max rows per class per run, oldest first

EXPIRED_QUEUED_MESSAGE = (
    "never picked up by a worker (dispatch lost); not re-run automatically because "
    "it is over 24h old — run the playbook again if it still applies"
)
STALE_RUNNING_MESSAGE = (
    "worker stopped mid-run; actions may be partially applied — check the action "
    "log before re-running"
)


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


@shared_task(name="src.tasks.churn_playbooks.purge_old_executions")
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


@shared_task(name="src.tasks.churn_playbooks.reap_stale_executions")
def reap_stale_executions() -> dict:
    """
    Recover ChurnPlaybookExecution rows stranded by a lost publish or a dead worker.

    - queued, 15 min .. 24 h old  → re-publish run_playbook(id); row untouched.
      Duplicate deliveries are safe: execute() claims with a conditional UPDATE.
    - queued, over 24 h old       → failed (re-running a days-old play acts on stale state).
    - running, started over 1 h   → failed (actions are not idempotent; never re-run).

    Failed-marking is committed before any re-publish. Each class is bounded by
    REAP_BATCH_LIMIT, oldest first. Runs every 10 minutes (celery_app.py).

    Returns:
        dict — {"status": "complete", "redispatched": N,
                "expired_queued": N, "failed_running": N}
    """
    from src.models import ChurnPlaybookExecution as Exe

    now = datetime.utcnow()
    queued_stale_cutoff = now - timedelta(minutes=QUEUED_STALE_MINUTES)
    queued_expiry_cutoff = now - timedelta(hours=QUEUED_MAX_REDISPATCH_HOURS)
    running_cutoff = now - timedelta(hours=RUNNING_STALE_HOURS)

    with get_db_session() as db:
        # Terminal transitions are conditional UPDATEs on the status we selected,
        # so a row a worker claims or finishes in between is never overwritten.
        expired_queued = _fail_where(
            db,
            (Exe.status == "queued", Exe.created_at < queued_expiry_cutoff),
            Exe.created_at,
            "queued",
            EXPIRED_QUEUED_MESSAGE,
            now,
        )
        stale_running = _fail_where(
            db,
            (Exe.status == "running", Exe.started_at < running_cutoff),
            Exe.started_at,
            "running",
            STALE_RUNNING_MESSAGE,
            now,
        )

        # Commit the terminal transitions before publishing anything.
        db.commit()

        redispatch_ids = [
            exe_id for (exe_id,) in (
                db.query(Exe.id)
                .filter(
                    Exe.status == "queued",
                    Exe.created_at < queued_stale_cutoff,
                    Exe.created_at >= queued_expiry_cutoff,
                )
                .order_by(Exe.created_at, Exe.id)
                .limit(REAP_BATCH_LIMIT)
                .all()
            )
        ]

    redispatched = 0
    for exe_id in redispatch_ids:
        try:
            run_playbook.delay(exe_id)
            redispatched += 1
        except Exception as exc:
            logger.warning(
                "reap_stale_executions: re-publish failed for execution_id=%s: %s",
                exe_id, exc,
            )

    result = {
        "status": "complete",
        "redispatched": redispatched,
        "expired_queued": expired_queued,
        "failed_running": stale_running,
    }
    logger.info("reap_stale_executions: %s", result)
    return result


def _fail_where(db, criteria, order_col, from_status, message, now) -> int:
    """Mark up to REAP_BATCH_LIMIT matching rows failed, oldest first; return count."""
    from src.models import ChurnPlaybookExecution as Exe

    ids = [
        exe_id for (exe_id,) in (
            db.query(Exe.id)
            .filter(*criteria)
            .order_by(order_col, Exe.id)
            .limit(REAP_BATCH_LIMIT)
            .all()
        )
    ]
    if not ids:
        return 0
    return (
        db.query(Exe)
        .filter(Exe.id.in_(ids), Exe.status == from_status)
        .update(
            {"status": "failed", "error_message": message, "completed_at": now},
            synchronize_session=False,
        )
    )
