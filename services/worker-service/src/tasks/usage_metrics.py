"""
Celery tasks for product-usage rollup and scoring (aspect 3), plus the
usage-history-snapshot aspect's daily storage and pruning.

Tasks:
  process_usage_event      — triggered per event from ingestion-receiver;
                              upserts the customer_usage rollup and
                              recomputes usage_score.
  recompute_usage_scores   — scheduled daily to apply recency decay even when
                              no new events arrive; also writes a daily
                              customer_usage_history snapshot row per
                              scanned customer (usage-history-snapshot
                              aspect).
  purge_old_usage_history  — scheduled weekly to delete snapshot rows older
                              than USAGE_HISTORY_RETENTION_DAYS.

Beat registration: see celery_app.py (``recompute-usage-scores-daily``,
``purge-old-usage-history``).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from celery import shared_task

from src.database import get_db_session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Score change threshold that warrants a health-score recompute during the
# scheduled decay pass (avoids spamming unnecessary health refreshes).
_HEALTH_RECOMPUTE_DELTA: int = 2

# Retention window for customer_usage_history rows (usage-history-snapshot
# aspect). 180 days comfortably exceeds the 12-16 day lookback band the
# trend-detection-and-health aspect will use. Single edit point if an
# operator ever wants a shorter window; no per-org configurability.
USAGE_HISTORY_RETENTION_DAYS: int = 180

# Batch size for the daily snapshot write's bulk insert (AC 7 — not N+1: a
# large first-run population is chunked rather than issued as one
# unboundedly large INSERT).
_SNAPSHOT_CHUNK_SIZE: int = 1000


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _compute_rollup_from_events(
    events: list,
    now: datetime,
) -> dict:
    """
    Derive all rollup fields from a list of UsageEvent rows.

    Parameters
    ----------
    events : list of UsageEvent ORM objects for (org_id, customer_email).
    now    : reference timestamp for rolling-window calculations.

    Returns
    -------
    dict with keys matching CustomerUsage columns.
    """
    cutoff_7d = now - timedelta(days=7)
    cutoff_14d = now - timedelta(days=14)
    cutoff_30d = now - timedelta(days=30)

    events_7d = [e for e in events if e.occurred_at and e.occurred_at >= cutoff_7d]
    events_14d = [e for e in events if e.occurred_at and e.occurred_at >= cutoff_14d]
    events_30d = [e for e in events if e.occurred_at and e.occurred_at >= cutoff_30d]

    # Distinct calendar days with at least one event
    active_days_7d = len(set(e.occurred_at.date() for e in events_7d if e.occurred_at))
    active_days_14d = len(set(e.occurred_at.date() for e in events_14d if e.occurred_at))
    active_days_30d = len(set(e.occurred_at.date() for e in events_30d if e.occurred_at))

    # Login/activity counts: any track or identify event counts as activity
    login_count_7d = sum(1 for e in events_7d if e.event_type in ("track", "identify"))
    login_count_30d = sum(1 for e in events_30d if e.event_type in ("track", "identify"))

    # Distinct feature names from ALL history (not window-limited)
    distinct_features: List[str] = sorted(set(
        e.event_name for e in events if e.event_name is not None
    ))
    distinct_feature_count = len(distinct_features)

    all_occurred = [e.occurred_at for e in events if e.occurred_at]
    last_active_at = max(all_occurred) if all_occurred else None
    first_seen_at = min(all_occurred) if all_occurred else None

    return {
        "events_total": len(events),
        "last_active_at": last_active_at,
        "first_seen_at": first_seen_at,
        "active_days_7d": active_days_7d,
        "active_days_14d": active_days_14d,
        "active_days_30d": active_days_30d,
        "login_count_7d": login_count_7d,
        "login_count_30d": login_count_30d,
        "distinct_features": distinct_features,
        "distinct_feature_count": distinct_feature_count,
    }


def _rederive_windows(db, org_id: int, customer_email: str, now: datetime) -> dict:
    """
    Re-derive ONLY the rolling-window fields for a customer against ``now``,
    from a bounded (30-day) ``usage_event`` read.

    This deliberately does NOT read the customer's full event history — the
    daily recompute does not need lifetime aggregates, and feeding a bounded
    event list through ``_compute_rollup_from_events`` would silently
    truncate ``events_total``, ``first_seen_at``, and ``distinct_features``
    if the full returned dict were written back (see plan §6.1). Callers
    must assign only the keys returned here.

    Returns
    -------
    dict with exactly: active_days_7d, active_days_14d, active_days_30d,
    login_count_7d, login_count_30d.
    """
    from src.models import UsageEvent

    cutoff_30d = now - timedelta(days=30)
    events_30d = (
        db.query(UsageEvent)
        .filter(
            UsageEvent.organization_id == org_id,
            UsageEvent.customer_email == customer_email,
            UsageEvent.occurred_at != None,  # noqa: E711 — preserve NULL guard
            UsageEvent.occurred_at >= cutoff_30d,
        )
        .all()
    )

    fields = _compute_rollup_from_events(events_30d, now)
    return {
        "active_days_7d": fields["active_days_7d"],
        "active_days_14d": fields["active_days_14d"],
        "active_days_30d": fields["active_days_30d"],
        "login_count_7d": fields["login_count_7d"],
        "login_count_30d": fields["login_count_30d"],
    }


def _upsert_rollup(db, org_id: int, customer_email: str, fields: dict, usage_score: int):
    """
    Insert or update a customer_usage row.

    The upsert is done in Python rather than via ON CONFLICT so that SQLite
    (used in tests) and PostgreSQL (production) both work.
    """
    from src.models import CustomerUsage

    rollup = (
        db.query(CustomerUsage)
        .filter_by(organization_id=org_id, customer_email=customer_email)
        .first()
    )
    if rollup is None:
        rollup = CustomerUsage(
            organization_id=org_id,
            customer_email=customer_email,
            first_seen_at=fields.get("first_seen_at"),
        )
        db.add(rollup)

    rollup.events_total = fields["events_total"]
    rollup.last_active_at = fields["last_active_at"]
    rollup.active_days_7d = fields["active_days_7d"]
    rollup.active_days_14d = fields["active_days_14d"]
    rollup.active_days_30d = fields["active_days_30d"]
    rollup.login_count_7d = fields["login_count_7d"]
    rollup.login_count_30d = fields["login_count_30d"]
    rollup.distinct_features = fields["distinct_features"]
    rollup.distinct_feature_count = fields["distinct_feature_count"]
    rollup.usage_score = usage_score
    rollup.updated_at = datetime.utcnow()

    # Preserve earliest first_seen_at across re-processes
    fsa = fields.get("first_seen_at")
    if fsa is not None:
        if rollup.first_seen_at is None or fsa < rollup.first_seen_at:
            rollup.first_seen_at = fsa

    db.flush()
    return rollup


def _call_update_health(org_id: int, customer_email: str, db) -> None:
    """
    Trigger a health-score recompute for the customer.

    ImportError is silently tolerated: during a partial-deploy the
    health_score_service module may not yet be present in the worker image.
    All other errors (e.g. sqlalchemy.exc.SQLAlchemyError for transient DB
    issues) are intentionally NOT caught here so that they propagate to the
    Celery task and trigger the configured retry policy.
    """
    try:
        from src.services.health_score_service import update_customer_health
        update_customer_health(org_id, customer_email, db)
    except ImportError:
        logger.warning(
            "health_score_service not available; skipping health recompute "
            "for org=%s email=%s", org_id, customer_email,
        )


def _write_usage_history_snapshots(
    db, snapshot_rows: List[Dict[str, Any]], today: "date",
) -> int:
    """
    Batched, idempotent daily write of ``customer_usage_history`` rows
    (usage-history-snapshot aspect).

    ``snapshot_rows`` is a list of pre-built plain dicts (organization_id,
    customer_email, and the payload fields) captured from the caller's
    already-recomputed CustomerUsage rows — NOT ORM instances — so this
    function has no dependency on those instances staying unexpired across
    the caller's own commit boundary.

    Not N+1 (AC 7): exactly one query to resolve which (org, email) pairs
    already have a snapshot for ``today`` (scoped to the orgs present in
    ``snapshot_rows``), then one ``bulk_insert_mappings`` call per chunk of
    ``_SNAPSHOT_CHUNK_SIZE`` rows — independent of the total row count for
    ordinary daily volumes.

    Same-day idempotency (AC 3): rows whose (org, email) key already has a
    snapshot for ``today`` are skipped, so re-running on the same UTC date
    leaves exactly one row per (org, email, today) and raises no
    IntegrityError. No ON CONFLICT — no precedent in this codebase and
    SQLite-backed tests could not exercise a Postgres-dialect upsert.

    Returns the number of rows actually inserted.
    """
    from src.models import CustomerUsageHistory

    if not snapshot_rows:
        return 0

    org_ids = {row["organization_id"] for row in snapshot_rows}
    existing_keys = {
        (org_id, email)
        for org_id, email in db.query(
            CustomerUsageHistory.organization_id, CustomerUsageHistory.customer_email
        ).filter(
            CustomerUsageHistory.snapshot_date == today,
            CustomerUsageHistory.organization_id.in_(org_ids),
        )
    }

    mappings = [
        {**row, "snapshot_date": today}
        for row in snapshot_rows
        if (row["organization_id"], row["customer_email"]) not in existing_keys
    ]

    written = 0
    for i in range(0, len(mappings), _SNAPSHOT_CHUNK_SIZE):
        chunk = mappings[i : i + _SNAPSHOT_CHUNK_SIZE]
        db.bulk_insert_mappings(CustomerUsageHistory, chunk)
        written += len(chunk)

    return written


def _do_process_usage_event(
    org_id: int,
    customer_email: Optional[str],
    event_type: str,
    event_name: Optional[str],
    occurred_at_iso: Optional[str],
    external_event_id: str,
    properties: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Core implementation of process_usage_event (Celery-free, directly testable).

    Upserts the customer_usage rollup for a single processed usage event.
    This function is designed to be fully idempotent: re-processing the same
    ``external_event_id`` produces the same rollup because the raw-event table
    already dedups on (organization_id, external_event_id).

    Note: ``occurred_at_iso`` is accepted for the enqueue contract (callers
    pass the timestamp at enqueue time) but the authoritative timestamp is
    read from the persisted UsageEvent row, not from this argument.
    """
    from src.models import UsageEvent

    if customer_email is None:
        logger.info(
            "process_usage_event: no customer_email, skipping rollup "
            "for org=%s ext_id=%s", org_id, external_event_id,
        )
        return {"status": "skipped", "reason": "no_customer_email"}

    with get_db_session() as db:
        # Verify the raw event exists (created by ingestion receiver).
        event = (
            db.query(UsageEvent)
            .filter_by(organization_id=org_id, external_event_id=external_event_id)
            .first()
        )
        if event is None:
            logger.warning(
                "process_usage_event: raw event not found org=%s ext_id=%s — skipping",
                org_id, external_event_id,
            )
            return {"status": "skipped", "reason": "event_not_found"}

        now = datetime.utcnow()

        # Fetch ALL events for this customer (full re-aggregation = idempotent)
        all_events = (
            db.query(UsageEvent)
            .filter_by(organization_id=org_id, customer_email=customer_email)
            .all()
        )

        fields = _compute_rollup_from_events(all_events, now)

        # Compute usage score (pure function, no I/O)
        from src.services.usage_score_service import compute_usage_score

        # Build a namespace-like object for compute_usage_score
        class _Proxy:
            pass

        proxy = _Proxy()
        proxy.last_active_at = fields["last_active_at"]
        proxy.active_days_30d = fields["active_days_30d"]
        proxy.distinct_feature_count = fields["distinct_feature_count"]

        score = compute_usage_score(proxy, now=now)

        _upsert_rollup(db, org_id, customer_email, fields, score)

        # Health score recompute (within same DB session)
        _call_update_health(org_id, customer_email, db)

        return {
            "status": "ok",
            "org_id": org_id,
            "customer_email": customer_email,
            "events_total": fields["events_total"],
            "usage_score": score,
        }


# ---------------------------------------------------------------------------
# Celery tasks
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="src.tasks.usage_metrics.process_usage_event",
)
def process_usage_event(
    self,
    org_id: int,
    customer_email: Optional[str],
    event_type: str,
    event_name: Optional[str],
    occurred_at_iso: Optional[str],
    external_event_id: str,
    properties: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Upsert the customer_usage rollup for a single processed usage event.

    This task is enqueued by the ingestion receiver (aspect 2) AFTER the raw
    event row has been written to ``usage_events``.  Delegates to
    ``_do_process_usage_event`` for testability.

    Args:
        org_id             : Organization ID (from JWT, not the event body).
        customer_email     : Resolved customer email (may be None).
        event_type         : ``"track"`` or ``"identify"``.
        event_name         : The track event name / identify action.
        occurred_at_iso    : ISO-8601 string of the event timestamp.
        external_event_id  : Segment messageId (dedup key).
        properties         : Event properties payload (may be None).

    Returns:
        dict with status, org_id, customer_email, events_total, usage_score.
    """
    try:
        return _do_process_usage_event(
            org_id=org_id,
            customer_email=customer_email,
            event_type=event_type,
            event_name=event_name,
            occurred_at_iso=occurred_at_iso,
            external_event_id=external_event_id,
            properties=properties,
        )
    except Exception as exc:
        logger.error(
            "process_usage_event failed for org=%s ext_id=%s: %s",
            org_id, external_event_id, exc, exc_info=True,
        )
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Scheduled recompute (daily)
# ---------------------------------------------------------------------------


# Same @shared_task pattern as process_usage_event above.
# NOTE: churn_calibration.py beat tasks (refit_all_orgs, refit_global_calibration,
# purge_old_calibration_models) appear to be plain functions without @shared_task
# decorators — they are likely silently unregistered.  See TRACKING.md follow-up.
# Do NOT edit churn_calibration.py here; address in a separate audit pass.
@shared_task(name="src.tasks.usage_metrics.recompute_usage_scores")
def recompute_usage_scores() -> Dict[str, int]:
    """
    Re-derive usage_score for every customer_usage row across all orgs.

    This task applies recency decay: even if no new events arrive, a
    customer who was last active 35 days ago will see their score fall from
    the ``aging`` band to the ``stale`` band over time.

    When the recomputed score changes by >= ``_HEALTH_RECOMPUTE_DELTA`` points,
    ``update_customer_health`` is also called so the health score reflects the
    new usage component.

    After the per-row recompute loop, also writes one customer_usage_history
    snapshot row per scanned customer for today's UTC date (usage-history-
    snapshot aspect) — see ``_write_usage_history_snapshots``.

    Beat schedule: daily — see celery_app.py ``recompute-usage-scores-daily``.

    Returns:
        dict with ``updated`` (rows whose score changed), ``total`` (rows
        scanned), and ``snapshot_written`` (rows newly inserted into
        customer_usage_history — 0 on a same-day re-run, AC 3).
    """
    from src.models import CustomerUsage
    from src.services.usage_score_service import compute_usage_score

    updated = 0
    total = 0
    snapshot_written = 0
    snapshot_rows: List[Dict[str, Any]] = []

    with get_db_session() as db:
        rows = db.query(CustomerUsage).all()
        now = datetime.utcnow()
        today = now.date()

        for row in rows:
            total += 1

            windows = _rederive_windows(db, row.organization_id, row.customer_email, now)
            windows_changed = any(
                getattr(row, field) != value for field, value in windows.items()
            )
            for field, value in windows.items():
                setattr(row, field, value)

            new_score = compute_usage_score(row, now=now)
            old_score = row.usage_score if row.usage_score is not None else 50

            # usage-history-snapshot aspect: capture the RE-DERIVED
            # (post-window-update) values for today's snapshot before any
            # early `continue` below — every scanned row is snapshotted
            # regardless of whether its score/windows actually changed
            # (AC 1, 2). Plain dicts, not the ORM row itself, so this
            # survives the score-update commit below without needing the
            # row to stay unexpired.
            snapshot_rows.append({
                "organization_id": row.organization_id,
                "customer_email": row.customer_email,
                "active_days_7d": row.active_days_7d,
                "active_days_14d": row.active_days_14d,
                "active_days_30d": row.active_days_30d,
                "login_count_30d": row.login_count_30d,
                "distinct_feature_count": row.distinct_feature_count,
                "usage_score": new_score,
                "last_active_at": row.last_active_at,
            })

            if new_score == old_score and not windows_changed:
                continue

            row.usage_score = new_score
            row.updated_at = now
            updated += 1

            if abs(new_score - old_score) >= _HEALTH_RECOMPUTE_DELTA:
                _call_update_health(row.organization_id, row.customer_email, db)

        if updated:
            db.commit()

        # Daily snapshot write — a SEPARATE transaction from the score-update
        # commit above, and run UNCONDITIONALLY (not gated on `updated`): a
        # steady population with no score changes must still get a daily
        # snapshot, or the trend detector's history never warms up. A
        # failure here is caught, logged, and does NOT roll back the score
        # updates already committed above — this task's long-shipped
        # behaviour (recency decay) must not regress because the newer
        # snapshot feature had a bad day (see D3 in the aspect spec: a
        # silently swallowed failure is the thing to avoid, not the fact of
        # catching it).
        try:
            snapshot_written = _write_usage_history_snapshots(db, snapshot_rows, today)
            db.commit()
        except Exception as exc:
            db.rollback()
            snapshot_written = 0
            logger.error(
                "recompute_usage_scores: snapshot write failed for %d scanned rows: %s",
                total, exc, exc_info=True,
            )

    logger.info(
        "recompute_usage_scores: scanned=%s updated=%s snapshot_written=%s",
        total, updated, snapshot_written,
    )
    return {"updated": updated, "total": total, "snapshot_written": snapshot_written}


# ---------------------------------------------------------------------------
# usage-history-snapshot aspect — prune task
# ---------------------------------------------------------------------------


@shared_task(name="src.tasks.usage_metrics.purge_old_usage_history")
def purge_old_usage_history() -> Dict[str, Any]:
    """
    Delete customer_usage_history rows with snapshot_date strictly older
    than USAGE_HISTORY_RETENTION_DAYS (180) days before now.

    Runs weekly (see celery_app.py ``purge-old-usage-history``). Safe to run
    multiple times — idempotent DELETE with a cutoff date; a second
    immediate run deletes 0.

    Returns:
        dict — {"status": "complete", "deleted": N}
    """
    from src.models import CustomerUsageHistory

    cutoff = datetime.utcnow().date() - timedelta(days=USAGE_HISTORY_RETENTION_DAYS)

    with get_db_session() as db:
        deleted = (
            db.query(CustomerUsageHistory)
            .filter(CustomerUsageHistory.snapshot_date < cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()

    logger.info(
        "purge_old_usage_history: deleted %d CustomerUsageHistory rows older than %s",
        deleted, cutoff,
    )

    return {"status": "complete", "deleted": deleted}
