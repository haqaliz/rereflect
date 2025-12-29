"""
Celery client for queueing tasks to worker-service.
This module provides a way to queue analysis tasks from the backend-api
to the separate worker-service for distributed processing.

Redis Database Layout:
- DB 0: Celery broker (task queue)
- DB 1: Session storage
- DB 2: Application cache
- DB 3: Rate limiting
"""

import os
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
CELERY_BROKER_DB = int(os.getenv("CELERY_BROKER_DB", "0"))


def get_redis_url(db: int = 0) -> str:
    """Get Redis URL for a specific logical database."""
    if REDIS_PASSWORD:
        return f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{db}"
    return f"redis://{REDIS_HOST}:{REDIS_PORT}/{db}"


# Lazy initialization of Celery app
_celery_app = None


def get_celery_app():
    """Get or create Celery app instance (lazy initialization)."""
    global _celery_app

    if _celery_app is None:
        try:
            from celery import Celery

            _celery_app = Celery(
                "backend_api_client",
                broker=get_redis_url(CELERY_BROKER_DB),
                backend=get_redis_url(CELERY_BROKER_DB),
            )

            _celery_app.conf.update(
                task_serializer="json",
                accept_content=["json"],
                result_serializer="json",
                timezone="UTC",
                enable_utc=True,
            )

            logger.info("Celery client initialized successfully")

        except ImportError:
            logger.error("Celery not installed! Run: pip install celery[redis]")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize Celery: {e}")
            raise

    return _celery_app


def queue_analyze_feedback(feedback_id: int) -> str:
    """
    Queue a single feedback item for analysis.

    Args:
        feedback_id: ID of the feedback item to analyze

    Returns:
        Task ID
    """
    app = get_celery_app()

    try:
        result = app.send_task(
            "src.tasks.analysis.analyze_single_feedback",
            args=[feedback_id],
        )
        logger.info(f"Queued analysis task for feedback {feedback_id}: {result.id}")
        return result.id

    except Exception as e:
        logger.error(f"Failed to queue analysis task: {e}")
        raise


def queue_analyze_batch(org_id: int, feedback_ids: List[int]) -> str:
    """
    Queue a batch of feedback items for analysis.

    Args:
        org_id: Organization ID (for security/isolation)
        feedback_ids: List of feedback item IDs to analyze

    Returns:
        Task ID
    """
    app = get_celery_app()

    try:
        result = app.send_task(
            "src.tasks.analysis.analyze_feedback_batch",
            args=[org_id, feedback_ids],
        )
        logger.info(f"Queued batch analysis for org {org_id}: {len(feedback_ids)} items, task {result.id}")
        return result.id

    except Exception as e:
        logger.error(f"Failed to queue batch analysis task: {e}")
        raise


def get_task_status(task_id: str) -> dict:
    """
    Get the status of a queued task.

    Args:
        task_id: Celery task ID

    Returns:
        dict with task status information
    """
    app = get_celery_app()

    try:
        result = app.AsyncResult(task_id)
        return {
            "task_id": task_id,
            "status": result.status,
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else None,
            "result": result.result if result.ready() else None,
        }

    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        return {"status": "error", "error": str(e)}


def get_celery_status() -> dict:
    """Get Celery connection status."""
    try:
        app = get_celery_app()
        # Try to ping Redis
        import redis
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD or None, db=CELERY_BROKER_DB)
        r.ping()

        return {
            "status": "connected",
            "broker": f"redis://{REDIS_HOST}:{REDIS_PORT}/{CELERY_BROKER_DB}",
        }
    except Exception as e:
        return {
            "status": "disconnected",
            "error": str(e),
        }
