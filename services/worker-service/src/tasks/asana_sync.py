"""
Inbound Asana status-sync poller (asana-status-sync/worker-sync-task).
See docs/planning/asana-status-sync/worker-sync-task/plan_20260712.md.
Mirrors src/tasks/jira_sync.py — see that module's docstring for the full
architectural rationale. This docstring only calls out the deltas.

Tasks:
  sync_all_asana  — fan-out over orgs with active AND status_sync_enabled
                     Asana integrations
  sync_asana_org  — per-org retryable sync (max_retries=3), thin wrapper
                     around `_sync_asana_org_body`

Core (Celery-free, tested directly):
  _sync_asana_org_body(integration_id, db, client=None) — loads the
  integration + this org's FeedbackAsanaTask links. Unlike Jira, Asana has
  no batch-fetch endpoint, so the poller calls `client.get_task(gid)` once
  per linked task (N-GET fan-out — accepted PRD risk for slice 1). Each
  fetched `completed` bool is mapped to a status_sync_core category via
  `asana_category` and reconciled through the pure
  `status_sync_core.decide_link_update`:
    - 'seed'    -> set link.asana_completed/asana_status_category/
                   last_status_synced_at only. NO status change/event
                   (safety: first observation must never move a
                   feedback item's workflow_status).
    - 'noop'    -> nothing.
    - 'changed' -> set link fields; the owning feedback is a candidate
                   for a status change.
  For every feedback with >=1 changed link, the target status is
  resolved from the MOST ADVANCED category across that feedback's live
  links (status_sync_core.most_advanced) — a multi-task feedback never
  regresses because one linked task reopened while another stayed done.
  `apply_status_change_worker` (lifted to src.services.status_writer so
  Jira and Asana share one implementation) applies the change (no-op on
  same value) and writes exactly ONE FeedbackWorkflowEvent per changed
  feedback.

  `client` is injectable (a plain object exposing `get_task`) so tests
  never need real HTTP or Celery machinery. When `client` is None (the
  real `sync_asana_org` task path), a real `AsanaClient` is constructed
  from the decrypted PAT (Bearer auth, fixed host — no site_url/email,
  contrast Jira).

The worker cannot import backend-api — it duplicates the pure reconcile
core (see src/services/status_sync_core.py, reused UNCHANGED) and the
Asana client (src/clients/asana.py), and mirrors the model columns it
needs (src/models/__init__.py AsanaIntegration / FeedbackAsanaTask).

R3: the api_token is never logged. Log messages use integration_id/org_id only.
R6: missing LLM_ENCRYPTION_KEY returns {"status": "error", "reason": "missing_encryption_key"}
    and does NOT retry (non-transient config error) — mirrors jira_sync.py/zendesk_sync.py.
D7 (mirrors jira_sync.py/zendesk_sync.py): an AsanaAuthError is operator-recoverable —
    last_sync_status/last_error are recorded WITHOUT disconnecting (is_active untouched)
    and without raising/retrying.

A 404 on a single task (AsanaNotFoundError) is swallowed per-link — that
link is left unchanged and the loop continues; the org sync still reports
"success" overall.

Outbound webhook dispatch on an Asana-driven status change is explicitly
DEFERRED (v2, PRD Out-of-Scope) — this task writes the timeline event +
status change only (see status_writer.py's docstring).

Beat schedule: every 15 minutes (interval, matching sync-jira-status-every-15-min).
Registration: see src/celery_app.py include list.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from celery import shared_task

from src.clients.asana import AsanaAuthError, AsanaClient, AsanaNotFoundError, AsanaTransientError
from src.database import get_db_session
from src.services.asana_adapter import asana_category
from src.services.status_sync_core import decide_link_update, most_advanced, resolve_target_status
from src.services.status_writer import apply_status_change_worker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Local token decryption (mirrors jira_sync.py / zendesk_sync.py _decrypt)
# R6: Worker cannot import from backend-api; uses its own Fernet helper.
# ---------------------------------------------------------------------------


def _decrypt(token: str) -> str:
    """Decrypt a Fernet-encrypted string using LLM_ENCRYPTION_KEY."""
    from cryptography.fernet import Fernet
    key = os.environ.get("LLM_ENCRYPTION_KEY")
    if not key:
        raise ValueError("LLM_ENCRYPTION_KEY is not set")
    return Fernet(key.encode()).decrypt(token.encode()).decode()


def _persist_terminal_status(integration_id: int, status: str, error: str) -> None:
    """
    Persist last_sync_status/last_error in a FRESH session that commits
    independently of the caller's session (mirrors jira_sync.py's
    identically-named helper — see its docstring for the full rollback
    rationale: the caller's `with get_db_session() as db:` block rolls
    back on any exception that propagates out of it, so a terminal
    failure status written just before `raise self.retry(...)` would
    otherwise be silently discarded).
    """
    from src.models import AsanaIntegration

    try:
        with get_db_session() as fresh_db:
            row = (
                fresh_db.query(AsanaIntegration)
                .filter(AsanaIntegration.id == integration_id)
                .first()
            )
            if row is not None:
                row.last_sync_status = status
                row.last_error = error
    except Exception:
        logger.error(
            "asana_sync: failed to persist terminal status=%s for integration_id=%s",
            status,
            integration_id,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Core sync logic (Celery-free — tested directly)
# ---------------------------------------------------------------------------


def _sync_asana_org_body(integration_id: int, db, client=None) -> Dict[str, Any]:
    """
    Inner logic of sync_asana_org. Extracted as a plain function taking `db`
    and an injectable `client` so tests never need real HTTP or Celery
    machinery.

    Raises:
        AsanaTransientError: propagated to the caller (sync_asana_org) so
            Celery can retry — never caught here.

    AsanaAuthError is caught HERE (not propagated) — recorded on the
    integration row and returned as a result dict, matching D7 (operator-
    recoverable, no retry, no disconnect).
    """
    from src.models import AsanaIntegration, FeedbackAsanaTask, FeedbackItem

    integ = (
        db.query(AsanaIntegration)
        .filter(AsanaIntegration.id == integration_id)
        .first()
    )
    if not integ:
        return {"status": "not_found", "integration_id": integration_id}
    if not integ.is_active:
        return {"status": "inactive", "integration_id": integration_id}
    if not integ.status_sync_enabled:
        return {"status": "disabled", "integration_id": integration_id}

    owns_client = client is None
    if owns_client:
        # R6: missing LLM_ENCRYPTION_KEY -> non-transient config error; do not retry.
        try:
            token = _decrypt(integ.api_token)
        except ValueError:
            logger.error(
                "asana_sync: LLM_ENCRYPTION_KEY unset for org=%s "
                "— cannot decrypt api_token; skipping (integration_id=%s)",
                integ.organization_id,
                integration_id,
            )
            integ.last_sync_status = "error"
            integ.last_error = "missing_encryption_key"
            db.flush()
            return {"status": "error", "reason": "missing_encryption_key"}

        client = AsanaClient(token)

    try:
        links = (
            db.query(FeedbackAsanaTask)
            .filter(FeedbackAsanaTask.organization_id == integ.organization_id)
            .all()
        )

        seeded = 0
        changed_links = 0
        changed_feedback_ids: set = set()

        # No batch endpoint — one get_task call per linked task gid.
        for link in links:
            try:
                task = client.get_task(link.asana_task_gid)
            except AsanaNotFoundError:
                # 404 / deleted / moved task — this link is simply left
                # unchanged (fine per plan); continue the loop.
                continue
            if task is None:
                continue

            completed = bool(task.get("completed"))
            category = asana_category(completed)
            # Synthetic label — used only for logging/metadata via
            # decide_link_update's return signature; not persisted (no
            # name column on FeedbackAsanaTask, contrast Jira).
            label = "Completed" if completed else "Open"

            action, _name, category = decide_link_update(
                category, label, link.asana_status_category
            )
            if action == "noop":
                continue

            link.asana_completed = completed
            link.asana_status_category = category
            link.last_status_synced_at = datetime.utcnow()

            if action == "seed":
                seeded += 1
            elif action == "changed":
                changed_links += 1
                changed_feedback_ids.add(link.feedback_id)

        status_changes = 0
        for feedback_id in changed_feedback_ids:
            feedback = (
                db.query(FeedbackItem).filter(FeedbackItem.id == feedback_id).first()
            )
            if feedback is None:
                continue

            live_links = [l for l in links if l.feedback_id == feedback_id]
            categories = [l.asana_status_category for l in live_links if l.asana_status_category]
            top_category = most_advanced(categories)
            if top_category is None:
                continue

            target = resolve_target_status(top_category, integ.status_mapping)
            observed_old_status = feedback.workflow_status
            if target is None or target == observed_old_status:
                continue

            # The link that drove the most-advanced category — used for the
            # timeline event's metadata (which Asana task caused this).
            driving_link = next(
                (l for l in live_links if l.asana_status_category == top_category),
                live_links[0],
            )

            applied = apply_status_change_worker(
                db,
                feedback,
                target,
                old_status=observed_old_status,
                organization_id=integ.organization_id,
                actor_label="asana-sync",
                metadata={
                    "source": "asana",
                    "asana_task_gid": driving_link.asana_task_gid,
                    "asana_completed": driving_link.asana_completed,
                },
            )
            if applied:
                status_changes += 1

        integ.last_synced_at = datetime.utcnow()
        integ.last_sync_status = "success"
        integ.last_error = None
        db.flush()

        return {
            "status": "success",
            "links_seen": len(links),
            "seeded": seeded,
            "changed_links": changed_links,
            "status_changes": status_changes,
        }

    except AsanaAuthError as exc:
        # D7: operator-recoverable auth failure — record without disconnecting
        # (is_active untouched) and without raising/retrying.
        logger.error(
            "asana_sync: auth error for org=%s (integration_id=%s): %s",
            integ.organization_id,
            integration_id,
            exc,
        )
        integ.last_sync_status = "error"
        integ.last_error = str(exc)[:500]
        db.flush()
        return {"status": "error", "reason": "auth_error"}

    finally:
        if owns_client:
            client.close()


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------


@shared_task(name="src.tasks.asana_sync.sync_all_asana")
def sync_all_asana() -> Dict[str, Any]:
    """
    Fan-out: scan all active + status_sync_enabled Asana integrations and
    enqueue per-org sync.

    Per-org try/except ensures one failure never aborts the batch.
    """
    from src.models import AsanaIntegration

    with get_db_session() as db:
        integrations = (
            db.query(AsanaIntegration)
            .filter(
                AsanaIntegration.is_active.is_(True),
                AsanaIntegration.status_sync_enabled.is_(True),
            )
            .all()
        )
        if not integrations:
            return {"status": "no_integrations", "queued": 0}

        queued = 0
        for integ in integrations:
            try:
                sync_asana_org.delay(integ.id)
                queued += 1
            except Exception as exc:
                logger.error(
                    "sync_all_asana: failed to enqueue org=%s (integration_id=%s): %s",
                    integ.organization_id,
                    integ.id,
                    exc,
                )

        return {"status": "queued", "queued": queued}


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="src.tasks.asana_sync.sync_asana_org",
)
def sync_asana_org(self, integration_id: int) -> Dict[str, Any]:
    """
    Per-org Asana status-sync poll. Retries on AsanaTransientError (max 3x).
    AsanaAuthError / missing-encryption-key are handled inside
    `_sync_asana_org_body` (recorded without raising/retrying).
    """
    with get_db_session() as db:
        try:
            return _sync_asana_org_body(integration_id, db)
        except AsanaTransientError as exc:
            logger.warning(
                "asana_sync: transient error for integration_id=%s: %s",
                integration_id,
                exc,
            )
            # NOTE: deliberately NOT db.flush()'d — this session's transaction
            # rolls back on the `raise` below regardless (see get_db_session),
            # and flushing here would additionally take a row lock that could
            # self-deadlock against the fresh session _persist_terminal_status
            # opens next (same row, same process). _persist_terminal_status is
            # the sole durable write for this branch — mirrors jira_sync.py.
            _persist_terminal_status(integration_id, "retrying", str(exc))
            raise self.retry(exc=exc)
