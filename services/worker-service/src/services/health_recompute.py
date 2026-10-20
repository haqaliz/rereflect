"""
Single seam for worker-side customer-health recomputation.

The scoring implementation (``health_score_service.update_customer_health``)
lives only in ``services/backend-api``. The worker image does not contain it, so
this module calls a backend internal endpoint instead — one implementation of
the scoring logic, identical side effects to backend-triggered recomputes.

Configuration (both required):

    INTERNAL_API_URL     backend base URL, e.g. http://backend:8000
    INTERNAL_API_SECRET  shared secret; the backend fails closed when unset

When the caller's Session has an open transaction, the POST is registered as an
``after_commit`` listener rather than sent immediately: the backend must be able
to read the feedback/usage/CRM rows this task just wrote. If the transaction
rolls back, nothing is posted. With no open transaction the POST is sent
immediately.

Unconfigured deployments keep the honest no-op: one ERROR per process naming the
consequence, and ``False`` returned. A failed POST is logged with the org/email
and never raises into the task that triggered it — a missed derived score must
not fail analysis, usage ingest, or a CRM sync.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from sqlalchemy import event

logger = logging.getLogger(__name__)

_RECOMPUTE_PATH = "/api/v1/internal/health/recompute"

# Log the missing-configuration case once per process rather than once per
# customer per sync — at ERROR, because a silently skipped recompute is what
# hid GitHub #3.
_warned = False


def _configured_endpoint() -> tuple[str, str] | None:
    base = os.getenv("INTERNAL_API_URL", "").strip()
    secret = os.getenv("INTERNAL_API_SECRET", "").strip()
    if not base or not secret:
        return None
    return base.rstrip("/") + _RECOMPUTE_PATH, secret


def _post(url: str, secret: str, org_id: int, customer_email: str) -> None:
    try:
        response = httpx.post(
            url,
            json={"org_id": org_id, "customer_email": customer_email},
            headers={"X-Internal-Secret": secret},
            timeout=5.0,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.error(
            "customer-health recompute POST failed for org=%s email=%s: %s",
            org_id,
            customer_email,
            exc,
        )


def request_health_recompute(org_id: int, customer_email: str, db: Any) -> bool:
    """Schedule a backend health recompute. Returns True when it was scheduled.

    Never raises for missing configuration or a failed POST: callers are Celery
    tasks whose primary work has already succeeded and must not be rolled back
    because a derived score could not be refreshed.
    """
    global _warned

    endpoint = _configured_endpoint()
    if endpoint is None:
        if not _warned:
            _warned = True
            logger.error(
                "customer-health recompute is UNAVAILABLE in the worker: "
                "INTERNAL_API_URL and/or INTERNAL_API_SECRET is not set, so "
                "health scores will not refresh from worker-driven events "
                "(feedback analysis, usage events, CRM sync). Set both to "
                "enable the backend recompute endpoint. This message is "
                "logged once per process."
            )
        return False

    url, secret = endpoint

    if db is not None and db.in_transaction():
        # Wait for the caller's commit so the backend reads committed rows.
        def _after_commit(session: Any) -> None:
            _post(url, secret, org_id, customer_email)

        event.listen(db, "after_commit", _after_commit, once=True)
        return True

    _post(url, secret, org_id, customer_email)
    return True
