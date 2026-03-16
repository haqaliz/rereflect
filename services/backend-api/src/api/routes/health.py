"""
Enhanced health check endpoint — system admin only.

GET /health/detailed
Returns: database, redis, worker, memory and uptime diagnostics.
"""

import os
import time
import logging
import redis

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from src.database.session import get_db
from src.api.dependencies import require_system_admin
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

# Module-level start time so uptime is measured from import (server start), not
# from the first request.
_START_TIME: float = time.monotonic()


def _check_database(db: Session) -> dict:
    """Run SELECT 1 against the database and return status + latency."""
    start = time.monotonic()
    try:
        db.execute(text("SELECT 1"))
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {"status": "ok", "latency_ms": latency_ms}
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return {"status": "error", "latency_ms": None}


def _check_redis() -> dict:
    """PING the Redis broker and return status + latency."""
    try:
        client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", 6379)),
            password=os.getenv("REDIS_PASSWORD") or None,
            db=0,
            socket_connect_timeout=1,
        )
        start = time.monotonic()
        client.ping()
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        return {"status": "ok", "latency_ms": latency_ms}
    except Exception as exc:
        logger.warning("Redis health check failed: %s", exc)
        return {"status": "error", "latency_ms": None}


def _check_worker() -> dict:
    """Probe the Celery broker to see if a worker is reachable."""
    try:
        from src.background import get_celery_status
        result = get_celery_status()
        # get_celery_status returns a dict; treat any non-error result as ok
        if isinstance(result, dict) and result.get("status") == "error":
            return {"status": "error"}
        return {"status": "ok"}
    except Exception as exc:
        logger.warning("Worker health check failed: %s", exc)
        return {"status": "unknown"}


def _get_memory_mb() -> float:
    """Return current process RSS memory in megabytes."""
    try:
        import psutil
        process = psutil.Process()
        rss_bytes = process.memory_info().rss
        return round(rss_bytes / (1024 * 1024), 2)
    except Exception:
        # Fallback: resource module (available on Unix without psutil)
        try:
            import resource
            rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # macOS reports bytes, Linux reports kilobytes
            if os.uname().sysname == "Darwin":
                return round(rss_kb / (1024 * 1024), 2)
            return round(rss_kb / 1024, 2)
        except Exception:
            return 0.0


@router.get("/health/detailed")
def detailed_health(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_system_admin),
):
    """
    Comprehensive service health — **system admin only**.

    Checks database connectivity, Redis connectivity, Celery worker,
    process memory, and server uptime.
    """
    from src.api.main import app as fastapi_app

    db_check = _check_database(db)
    redis_check = _check_redis()
    worker_check = _check_worker()
    memory_mb = _get_memory_mb()
    uptime_seconds = round(time.monotonic() - _START_TIME, 2)

    # Derive overall status
    all_statuses = [db_check["status"], redis_check["status"]]
    if "error" in all_statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    return {
        "status": overall,
        "database": db_check,
        "redis": redis_check,
        "worker": worker_check,
        "memory_mb": memory_mb,
        "uptime_seconds": uptime_seconds,
        "version": fastapi_app.version,
    }
