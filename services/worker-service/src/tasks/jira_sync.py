"""
Inbound Jira status-sync poller (jira-status-sync/inbound-status-sync,
Phase 4). See docs/planning/jira-status-sync/inbound-status-sync/plan_20260711.md.

Tasks:
  sync_all_jira  — fan-out over orgs with active AND status_sync_enabled
                    Jira integrations
  sync_jira_org  — per-org retryable sync (max_retries=3), thin wrapper
                    around `_sync_jira_org_body`

Core (Celery-free, tested directly):
  _sync_jira_org_body(integration_id, db, client=None) — loads the
  integration + this org's FeedbackJiraIssue links, fetches current
  status via `client.search_issues` (chunked <=50 keys), and reconciles
  each link through the pure `status_sync_core.decide_link_update`:
    - 'seed'    -> set link.jira_status/jira_status_category/
                   last_status_synced_at only. NO status change/event
                   (safety: first observation must never move a
                   feedback item's workflow_status).
    - 'noop'    -> nothing.
    - 'changed' -> set link fields; the owning feedback is a candidate
                   for a status change.
  For every feedback with >=1 changed link, the target status is
  resolved from the MOST ADVANCED category across that feedback's live
  links (status_sync_core.most_advanced) — a multi-issue feedback never
  regresses because one linked issue reopened while another stayed done.
  `apply_status_change_worker` applies the change (no-op on same value)
  and writes exactly ONE FeedbackWorkflowEvent per changed feedback.

  `client` is injectable (a plain object exposing `search_issues`) so
  tests never need real HTTP or Celery — this is the extraction point
  the plan calls out ("extracted so tests inject a fake client, no
  Celery"). When `client` is None (the real `sync_jira_org` task path),
  a real `JiraClient` is constructed from the decrypted token.

The worker cannot import backend-api — it duplicates the pure reconcile
core (see src/services/status_sync_core.py, a verbatim copy of
services/backend-api/src/services/status_sync_core.py) and the Jira
client (src/clients/jira.py), and mirrors the model columns it needs
(src/models/__init__.py JiraIntegration / FeedbackJiraIssue).

R3: the api_token is never logged. Log messages use integration_id/org_id only.
R6: missing LLM_ENCRYPTION_KEY returns {"status": "error", "reason": "missing_encryption_key"}
    and does NOT retry (non-transient config error) — mirrors zendesk_sync.py.
D7 (mirrors zendesk_sync.py): a JiraAuthError is operator-recoverable — last_sync_status/
    last_error are recorded WITHOUT disconnecting (is_active untouched) and without
    raising/retrying.

Outbound webhook dispatch on a Jira-driven status change is explicitly
DEFERRED (see plan's Agent Execution Notes) — this task writes the
timeline event + status change only.

Beat schedule: every 15 minutes (interval, matching sync-zendesk-every-15-min).
Registration: see src/celery_app.py include list.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from celery import shared_task

from src.clients.jira import JiraAuthError, JiraClient, JiraTransientError
from src.database import get_db_session
from src.services.status_sync_core import decide_link_update, most_advanced, resolve_target_status
from src.services.status_writer import apply_status_change_worker

logger = logging.getLogger(__name__)

# Cap the number of issue keys sent to a single client.search_issues() call —
# mirrors JiraClient's own internal chunk size (defense in depth; the client
# already chunks internally, but this keeps a single logical "page" of work
# per DB-visible batch here too).
_SEARCH_CHUNK_SIZE = 50


# ---------------------------------------------------------------------------
# Local token decryption (mirrors zendesk_sync.py / hubspot_sync.py _decrypt)
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
    independently of the caller's session (mirrors zendesk_sync.py's
    identically-named helper — see its docstring for the full rollback
    rationale: the caller's `with get_db_session() as db:` block rolls
    back on any exception that propagates out of it, so a terminal
    failure status written just before `raise self.retry(...)` would
    otherwise be silently discarded).
    """
    from src.models import JiraIntegration

    try:
        with get_db_session() as fresh_db:
            row = (
                fresh_db.query(JiraIntegration)
                .filter(JiraIntegration.id == integration_id)
                .first()
            )
            if row is not None:
                row.last_sync_status = status
                row.last_error = error
    except Exception:
        logger.error(
            "jira_sync: failed to persist terminal status=%s for integration_id=%s",
            status,
            integration_id,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Status writer: apply_status_change_worker lifted to
# src.services.status_writer (asana-status-sync/worker-sync-task aspect) so
# both jira_sync.py and asana_sync.py share one provider-agnostic
# implementation. Imported above; see status_writer.py's docstring.
# ---------------------------------------------------------------------------
# Core sync logic (Celery-free — tested directly)
# ---------------------------------------------------------------------------


def _sync_jira_org_body(integration_id: int, db, client=None) -> Dict[str, Any]:
    """
    Inner logic of sync_jira_org. Extracted as a plain function taking `db`
    and an injectable `client` so tests never need real HTTP or Celery
    machinery.

    Raises:
        JiraTransientError: propagated to the caller (sync_jira_org) so
            Celery can retry — never caught here.

    JiraAuthError is caught HERE (not propagated) — recorded on the
    integration row and returned as a result dict, matching D7 (operator-
    recoverable, no retry, no disconnect).
    """
    from src.models import FeedbackItem, FeedbackJiraIssue, JiraIntegration

    integ = (
        db.query(JiraIntegration)
        .filter(JiraIntegration.id == integration_id)
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
                "jira_sync: LLM_ENCRYPTION_KEY unset for org=%s "
                "— cannot decrypt api_token; skipping (integration_id=%s)",
                integ.organization_id,
                integration_id,
            )
            integ.last_sync_status = "error"
            integ.last_error = "missing_encryption_key"
            db.flush()
            return {"status": "error", "reason": "missing_encryption_key"}

        client = JiraClient(integ.site_url, integ.email, token)

    try:
        links = (
            db.query(FeedbackJiraIssue)
            .filter(FeedbackJiraIssue.organization_id == integ.organization_id)
            .all()
        )

        keys = [link.jira_issue_key for link in links]
        fetched: Dict[str, Dict[str, Any]] = {}
        for start in range(0, len(keys), _SEARCH_CHUNK_SIZE):
            chunk = keys[start : start + _SEARCH_CHUNK_SIZE]
            fetched.update(client.search_issues(chunk))

        seeded = 0
        changed_links = 0
        changed_feedback_ids: set = set()

        for link in links:
            info = fetched.get(link.jira_issue_key)
            if info is None:
                # 404 / deleted / moved issue — omitted from the response;
                # this link is simply left unchanged (fine per plan).
                continue

            action, name, category = decide_link_update(
                info.get("category"), info.get("name"), link.jira_status_category
            )
            if action == "noop":
                continue

            link.jira_status = name
            link.jira_status_category = category
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
            categories = [l.jira_status_category for l in live_links if l.jira_status_category]
            top_category = most_advanced(categories)
            if top_category is None:
                continue

            target = resolve_target_status(top_category, integ.status_mapping)
            if target is None or target == feedback.workflow_status:
                continue

            # The link that drove the most-advanced category — used for the
            # timeline event's metadata (which Jira issue caused this).
            driving_link = next(
                (l for l in live_links if l.jira_status_category == top_category),
                live_links[0],
            )

            applied = apply_status_change_worker(
                db,
                feedback,
                target,
                organization_id=integ.organization_id,
                actor_label="jira-sync",
                metadata={
                    "source": "jira",
                    "jira_status": driving_link.jira_status,
                    "jira_status_category": driving_link.jira_status_category,
                    "jira_issue_key": driving_link.jira_issue_key,
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

    except JiraAuthError as exc:
        # D7: operator-recoverable auth failure — record without disconnecting
        # (is_active untouched) and without raising/retrying.
        logger.error(
            "jira_sync: auth error for org=%s (integration_id=%s): %s",
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


@shared_task(name="src.tasks.jira_sync.sync_all_jira")
def sync_all_jira() -> Dict[str, Any]:
    """
    Fan-out: scan all active + status_sync_enabled Jira integrations and
    enqueue per-org sync.

    Per-org try/except ensures one failure never aborts the batch.
    """
    from src.models import JiraIntegration

    with get_db_session() as db:
        integrations = (
            db.query(JiraIntegration)
            .filter(
                JiraIntegration.is_active.is_(True),
                JiraIntegration.status_sync_enabled.is_(True),
            )
            .all()
        )
        if not integrations:
            return {"status": "no_integrations", "queued": 0}

        queued = 0
        for integ in integrations:
            try:
                sync_jira_org.delay(integ.id)
                queued += 1
            except Exception as exc:
                logger.error(
                    "sync_all_jira: failed to enqueue org=%s (integration_id=%s): %s",
                    integ.organization_id,
                    integ.id,
                    exc,
                )

        return {"status": "queued", "queued": queued}


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="src.tasks.jira_sync.sync_jira_org",
)
def sync_jira_org(self, integration_id: int) -> Dict[str, Any]:
    """
    Per-org Jira status-sync poll. Retries on JiraTransientError (max 3x).
    JiraAuthError / missing-encryption-key are handled inside
    `_sync_jira_org_body` (recorded without raising/retrying).
    """
    with get_db_session() as db:
        try:
            return _sync_jira_org_body(integration_id, db)
        except JiraTransientError as exc:
            logger.warning(
                "jira_sync: transient error for integration_id=%s: %s",
                integration_id,
                exc,
            )
            # NOTE: deliberately NOT db.flush()'d — this session's transaction
            # rolls back on the `raise` below regardless (see get_db_session),
            # and flushing here would additionally take a row lock that could
            # self-deadlock against the fresh session _persist_terminal_status
            # opens next (same row, same process). _persist_terminal_status is
            # the sole durable write for this branch — mirrors zendesk_sync.py.
            _persist_terminal_status(integration_id, "retrying", str(exc))
            raise self.retry(exc=exc)
