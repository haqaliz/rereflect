"""
Celery tasks for scheduled AI report generation (worker-scheduled-generation).

Beat schedule (registered in celery_app.py):
- generate_scheduled_reports → hourly at :15 UTC; filters due schedules by
  cadence + hour_utc, then atomically claims each window via
  `UPDATE report_schedules SET last_run_at=:now WHERE id=:id AND enabled=TRUE
  AND (last_run_at IS NULL OR last_run_at < :cutoff)` (rowcount == 1).

- generate_schedule_once(schedule_id) → manual "sync now" (dispatched by the
  backend's POST /api/v1/report-schedules/{id}/run). Same pipeline; a manual
  run also claims the window, so it is exactly-once per cadence window.

Cutoffs (UTC): daily → start of today; weekly → most recent occurrence of
day_of_week before now; monthly → most recent occurrence of day_of_month
before now. A month without that day (e.g. day 31 in February) is skipped —
the window never existed, so it is neither claimed nor backfilled.

Window semantics: a crashed window is skipped, not backfilled (PRD §6.3).

Per-schedule try/except with db.rollback(): one failure never aborts the
batch (classifier_training.py retrain_all_orgs pattern), and a failed claim
is rolled back so the schedule stays claimable.

Never a bare except around imports (worker CLAUDE.md — treated as a defect).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from celery import shared_task
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.database import get_db_session
from src.email import send_scheduled_report_email
from src.models import Organization, Report, ReportSchedule, User
from src.services.report_generator import ReportGenerator
from src.services.scheduled_report_email import (
    DATE_RANGE_LABELS,
    REPORT_TYPE_LABELS,
    render_scheduled_report_email,
)
from src.services.scheduled_report_narrative import (
    generate_report_narrative,
    resolve_narrative_model,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cutoff / due computation (UTC)
# ---------------------------------------------------------------------------


def _cutoff(schedule: ReportSchedule, now: datetime) -> Optional[datetime]:
    """Start of the cadence window that `now` falls into, or None to skip.

    daily   → start of today (00:00 UTC)
    weekly  → most recent occurrence of day_of_week before now (00:00 UTC)
    monthly → most recent occurrence of day_of_month before now (00:00 UTC);
              None when the current or previous month has no such day.
    """
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if schedule.cadence == "daily":
        return midnight

    if schedule.cadence == "weekly":
        days_since = (now.weekday() - schedule.day_of_week) % 7
        return (now - timedelta(days=days_since)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    if schedule.cadence == "monthly":
        if now.day >= schedule.day_of_month:
            return now.replace(
                day=schedule.day_of_month, hour=0, minute=0, second=0, microsecond=0
            )
        prev_month_last = now.replace(day=1) - timedelta(days=1)
        if schedule.day_of_month > prev_month_last.day:
            return None
        return prev_month_last.replace(
            day=schedule.day_of_month, hour=0, minute=0, second=0, microsecond=0
        )

    raise ValueError(f"unknown cadence: {schedule.cadence}")


def _is_due(schedule: ReportSchedule, now: datetime) -> bool:
    """True when the schedule's cadence window + hour_utc matches `now`."""
    if schedule.hour_utc != now.hour:
        return False

    if schedule.cadence == "daily":
        return True
    if schedule.cadence == "weekly":
        return now.weekday() == schedule.day_of_week
    if schedule.cadence == "monthly":
        return now.day == schedule.day_of_month

    raise ValueError(f"unknown cadence: {schedule.cadence}")


# ---------------------------------------------------------------------------
# Atomic claim
# ---------------------------------------------------------------------------


def _claim_schedule(db: Session, schedule_id: int, now: datetime, cutoff: datetime) -> bool:
    """Atomically claim the current window; True only when this caller won.

    The UPDATE both marks last_run_at and acts as the dedup guard: the row is
    updated only while enabled and last_run_at < cutoff, so two overlapping
    beats (or a manual run) can never both win the same window.
    """
    result = db.execute(
        text(
            "UPDATE report_schedules SET last_run_at = :now "
            "WHERE id = :id AND enabled = TRUE "
            "AND (last_run_at IS NULL OR last_run_at < :cutoff)"
        ),
        {"now": now, "id": schedule_id, "cutoff": cutoff},
    )
    return result.rowcount == 1


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _report_title(report_type: str, date_range_days: int) -> str:
    type_label = REPORT_TYPE_LABELS.get(
        report_type, report_type.replace("_", " ").title()
    )
    range_label = DATE_RANGE_LABELS.get(
        date_range_days, f"Last {date_range_days} days"
    )
    return f"{type_label} report — {range_label}"


def _generate_for_schedule(schedule: ReportSchedule, db: Session, now: datetime) -> None:
    """Build + commit the Report row, then email recipients (best-effort).

    Narrative is generated BEFORE the Report commit: on any LLM absence or
    failure the run degrades to data-only and never fails (the writer itself
    returns None, but the guard also protects against a future writer
    regression). Email failures are logged, never fail the run.
    """
    report_data = ReportGenerator().generate(
        db,
        schedule.organization_id,
        schedule.report_type,
        schedule.date_range_days,
    )

    narrative = None
    try:
        narrative = generate_report_narrative(
            report_data, schedule.organization_id, db
        )
    except Exception:
        logger.error(
            "scheduled report: schedule=%s narrative FAILED — data-only",
            schedule.id,
            exc_info=True,
        )
        narrative = None

    created_by = None
    if schedule.created_by_user_id is not None:
        creator = db.query(User).filter_by(id=schedule.created_by_user_id).first()
        if creator is not None:
            created_by = creator.id

    date_start = now - timedelta(days=schedule.date_range_days)
    report_metadata = {
        "schedule_id": schedule.id,
        "source": "scheduled",
        "generated_at": now.isoformat(),
        "date_start": date_start.isoformat(),
        "date_end": now.isoformat(),
    }
    if narrative:
        report_metadata["model_used"] = resolve_narrative_model(
            schedule.organization_id, db
        )
        report_metadata["narrative"] = narrative

    report = Report(
        organization_id=schedule.organization_id,
        created_by_user_id=created_by,
        conversation_id=None,
        report_type=schedule.report_type,
        date_range_days=schedule.date_range_days,
        title=_report_title(schedule.report_type, schedule.date_range_days),
        sections=report_data["sections"],
        report_metadata=report_metadata,
        pdf_generated=False,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    if schedule.recipients:
        org = db.query(Organization).filter_by(id=schedule.organization_id).first()
        org_name = org.name if org else ""
        rendered = render_scheduled_report_email(
            {
                "organization_name": org_name,
                "report_type": schedule.report_type,
                "date_range_days": schedule.date_range_days,
                "title": report.title,
                "narrative": narrative,
                "sections": report_data["sections"],
            }
        )
        for email in schedule.recipients:
            try:
                send_scheduled_report_email(
                    to_email=email,
                    organization_name=org_name,
                    subject=rendered["subject"],
                    html=rendered["html"],
                )
            except Exception:
                logger.error(
                    "scheduled report: schedule=%s email to %s FAILED",
                    schedule.id,
                    email,
                    exc_info=True,
                )


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


@shared_task(name="src.tasks.scheduled_reports.generate_scheduled_reports")
def generate_scheduled_reports() -> dict:
    """Beat: hourly at :15 UTC — materialize every due schedule into a Report.

    Returns {"status": "ok", "generated": N, "skipped": M, "errors": K}.
    One failing schedule never aborts the batch; its claim is rolled back so
    the window stays claimable.
    """
    tally = {"status": "ok", "generated": 0, "skipped": 0, "errors": 0}

    with get_db_session() as db:
        now = datetime.utcnow()
        schedules = (
            db.query(ReportSchedule)
            .filter(ReportSchedule.enabled == True)  # noqa: E712
            .all()
        )
        for schedule in schedules:
            try:
                if not _is_due(schedule, now):
                    tally["skipped"] += 1
                    continue
                cutoff = _cutoff(schedule, now)
                if cutoff is None:
                    # Month without this day (e.g. day 31 in February) —
                    # the window never existed; skipped, not backfilled.
                    tally["skipped"] += 1
                    continue
                if not _claim_schedule(db, schedule.id, now, cutoff):
                    tally["skipped"] += 1
                    continue
                _generate_for_schedule(schedule, db, now)
                tally["generated"] += 1
            except Exception:
                logger.error(
                    "generate_scheduled_reports: schedule=%s FAILED",
                    schedule.id,
                    exc_info=True,
                )
                # Shared session: a failed flush/commit leaves the session
                # needing a rollback, else the next schedule hits
                # PendingRollbackError and the whole batch cascades. The
                # rollback also undoes an uncommitted claim.
                db.rollback()
                tally["errors"] += 1

    logger.info("generate_scheduled_reports: done %s", tally)
    return tally


@shared_task(name="src.tasks.scheduled_reports.generate_schedule_once")
def generate_schedule_once(schedule_id: int) -> dict:
    """Manual "sync now" for one schedule (admin/owner endpoint dispatches this).

    Same pipeline as the beat task. A manual run claims the current cadence
    window the same way, so it is also exactly-once per window: if the window
    was already claimed (by the beat or a previous manual run), it is skipped.
    The hour/cadence due-check does NOT apply — the operator asked for it now.
    """
    with get_db_session() as db:
        now = datetime.utcnow()
        schedule = db.query(ReportSchedule).filter_by(id=schedule_id).first()
        if schedule is None:
            logger.warning(
                "generate_schedule_once: schedule %s not found", schedule_id
            )
            return {"status": "not_found", "schedule_id": schedule_id}

        try:
            cutoff = _cutoff(schedule, now)
            if cutoff is None:
                return {"status": "skipped", "schedule_id": schedule_id}
            if not _claim_schedule(db, schedule.id, now, cutoff):
                return {"status": "skipped", "schedule_id": schedule_id}
            _generate_for_schedule(schedule, db, now)
        except Exception:
            logger.error(
                "generate_schedule_once: schedule=%s FAILED",
                schedule_id,
                exc_info=True,
            )
            db.rollback()
            return {"status": "error", "schedule_id": schedule_id}

        logger.info("generate_schedule_once: schedule=%s generated", schedule_id)
        return {"status": "generated", "schedule_id": schedule_id}