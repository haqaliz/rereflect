"""
Shared, provider-agnostic status writer for inbound status-sync pollers
(jira_sync.py, asana_sync.py — asana-status-sync/worker-sync-task aspect).

Lifted verbatim (behavior byte-identical) from jira_sync.py's
`apply_status_change_worker`, which was already provider-neutral: it takes
an `actor_label` and a free-form `metadata` dict and hardcodes nothing
Jira-specific. Both pollers import this single function so the "one event,
no-op-on-equal, actor_id=None, no outbound webhook" invariants can never
diverge between providers.

Characterization lock: tests/test_jira_sync_task.py must stay green,
same count, before and after this lift (proves byte-identical behavior).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def apply_status_change_worker(
    db,
    feedback,
    new_status: str,
    *,
    organization_id: int,
    actor_label: str,
    metadata: Optional[dict] = None,
) -> bool:
    """
    Apply a workflow_status change driven by an automated source (no acting
    user — actor_id is always None here) and write exactly ONE
    FeedbackWorkflowEvent timeline row.

    No-ops (returns False, writes nothing) when `new_status` already equals
    the feedback's current workflow_status.

    NOTE: this deliberately does NOT dispatch outbound `feedback.status_changed`
    webhooks — see the calling task modules' docstrings ("Outbound webhook
    dispatch ... DEFERRED"). If worker-side webhook dispatch is ever added,
    do it once here so both providers stay aligned.
    """
    from src.models import FeedbackWorkflowEvent

    if feedback.workflow_status == new_status:
        return False

    old_status = feedback.workflow_status
    feedback.workflow_status = new_status

    logger.info(
        "status_writer: %s changed feedback_id=%s org=%s %s -> %s",
        actor_label,
        feedback.id,
        organization_id,
        old_status,
        new_status,
    )

    event = FeedbackWorkflowEvent(
        feedback_id=feedback.id,
        organization_id=organization_id,
        actor_id=None,
        event_type="status_changed",
        old_value=old_status,
        new_value=new_status,
        metadata_=metadata,
        created_at=datetime.utcnow(),
    )
    db.add(event)
    return True
