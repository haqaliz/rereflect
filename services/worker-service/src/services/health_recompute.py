"""
Single seam for worker-side customer-health recomputation.

WHAT IS BROKEN (GitHub #3)
--------------------------
``health_score_service`` lives only in ``services/backend-api``. The worker image
copies ``worker-service/src`` and ``analysis-engine/src/analyzer`` and nothing
else, so ``from src.services.health_score_service import update_customer_health``
raises ImportError inside the worker **every time, in every deployment**.

Three call sites did that import inline and swallowed the ImportError:

    tasks/analysis.py      after feedback analysis
    tasks/usage_metrics.py after a usage event
    tasks/hubspot_sync.py  after a CRM enrichment upsert

so all three have always been no-ops. The scope in #3 ("crm_component does not
refresh") is narrower than reality: the worker never recomputes customer health
at all. ``CustomerHealth`` rows are only ever written by the backend, from
``crm_integration_common``.

It stayed hidden because the worker tests inject a mock module into
``sys.modules`` for ``src.services.health_score_service`` before importing the
task. That makes the import succeed under test, so the suite asserts the call is
made while production cannot make it. ``test_health_recompute_seam.py`` pins the
real behaviour instead.

WHY IT IS NOT FIXED HERE
------------------------
``update_customer_health`` transitively needs ``automation_engine`` and
``notification_dispatch_helpers`` on top of the eight models the worker already
mirrors. Mirroring the scoring core but degrading those two would give
worker-triggered recomputes different side effects from backend-triggered ones —
a silent behavioural divergence in the health score, which is worse than the
current honest no-op. The options are laid out in #3; picking one is a design
decision, not a cleanup.

WHAT THIS MODULE DOES
---------------------
Centralises the seam so there is exactly one place to implement the fix, and
makes the failure observable instead of silent. Callers get a boolean and can
carry on: a missed recompute must never fail the task that triggered it.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Log the unavailability once per process rather than once per customer per
# sync — at ERROR, because a silently skipped recompute is what hid #3.
_warned = False


def request_health_recompute(org_id: int, customer_email: str, db: Any) -> bool:
    """Recompute a customer's health score. Returns True if it actually ran.

    Never raises for the "service unavailable" case: callers are Celery tasks
    whose primary work (analysis, usage ingest, CRM sync) has already succeeded
    and must not be rolled back because a derived score could not be refreshed.
    Errors raised by the recompute itself DO propagate, so a genuine failure is
    still visible to the task's retry policy.
    """
    global _warned
    try:
        from src.services.health_score_service import update_customer_health
    except ImportError:
        if not _warned:
            _warned = True
            logger.error(
                "customer-health recompute is UNAVAILABLE in the worker: "
                "src.services.health_score_service is not part of the worker "
                "image, so health scores will not refresh from worker-driven "
                "events (feedback analysis, usage events, CRM sync). "
                "See GitHub issue #3. This message is logged once per process."
            )
        return False

    update_customer_health(org_id, customer_email, db)
    return True
