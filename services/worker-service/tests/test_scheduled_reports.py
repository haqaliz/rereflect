"""
TDD tests for scheduled AI report generation (worker-scheduled-generation).

Phase 1: mirrored ReportGenerator characterization (pins against drift).
Later phases append: narrative writer, beat task dedup, Report row content,
email dispatch, per-schedule exception isolation, generate_schedule_once.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.models import (
    CustomerHealth,
    FeedbackItem,
    Organization,
    Report,
    ReportSchedule,
    User,
)
from src.services.report_generator import ReportGenerator
from src.services.scheduled_report_narrative import generate_report_narrative


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_org(db, name: str = "Org") -> Organization:
    org = Organization(name=name, plan="business")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _seed_report_data(db, org_id: int) -> None:
    """Deterministic dataset for the generator characterization test."""
    now = datetime.utcnow()
    feedbacks = [
        FeedbackItem(
            organization_id=org_id,
            text="Great product!",
            source="email",
            sentiment_label="positive",
            sentiment_score=0.9,
            is_urgent=False,
            created_at=now - timedelta(days=1),
        ),
        FeedbackItem(
            organization_id=org_id,
            text="App crashes on login",
            source="support",
            sentiment_label="negative",
            sentiment_score=-0.8,
            pain_point_category="bugs",
            pain_point_severity="critical",
            is_urgent=True,
            created_at=now - timedelta(days=2),
        ),
        FeedbackItem(
            organization_id=org_id,
            text="Would like dark mode",
            source="email",
            sentiment_label="neutral",
            sentiment_score=0.1,
            feature_request_category="ui",
            feature_request_priority="medium",
            is_urgent=False,
            created_at=now - timedelta(days=3),
        ),
        FeedbackItem(
            organization_id=org_id,
            text="Old feedback",
            source="email",
            sentiment_label="positive",
            sentiment_score=0.9,
            is_urgent=False,
            created_at=now - timedelta(days=40),
        ),
    ]
    health = [
        CustomerHealth(
            organization_id=org_id,
            customer_email="at-risk@test.com",
            health_score=30,
            risk_level="at_risk",
        ),
        CustomerHealth(
            organization_id=org_id,
            customer_email="critical@test.com",
            health_score=15,
            risk_level="critical",
        ),
        CustomerHealth(
            organization_id=org_id,
            customer_email="healthy@test.com",
            health_score=85,
            risk_level="healthy",
        ),
    ]
    for f in feedbacks:
        db.add(f)
    for h in health:
        db.add(h)
    db.commit()


# ---------------------------------------------------------------------------
# Phase 1 — ReportGenerator mirror characterization
# ---------------------------------------------------------------------------


class TestReportGeneratorMirror:
    def test_generate_executive_summary_section_shape(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)

        result = ReportGenerator().generate(db, org.id, "executive_summary", 30)

        assert result["title"].startswith("Executive Summary")
        headings = [s["heading"] for s in result["sections"]]
        assert headings == [
            "Overview",
            "Sentiment Analysis",
            "Top Pain Points",
            "Feature Requests",
        ]
        overview_rows = {
            row[0]: row[1] for row in result["sections"][0]["data"]["rows"]
        }
        assert overview_rows["Total Feedback"] == 3  # 40-day-old row excluded
        assert overview_rows["Urgent Items"] == 1
        assert overview_rows["At-Risk Customers"] == 2

        sentiment_rows = {
            row[0]: row[1] for row in result["sections"][1]["data"]["rows"]
        }
        assert sentiment_rows == {"positive": 1, "negative": 1, "neutral": 1}

        pain_rows = result["sections"][2]["data"]["rows"]
        assert pain_rows == [["bugs", 1]]

        feature_rows = result["sections"][3]["data"]["rows"]
        assert feature_rows == [["ui", 1]]

    def test_generate_customer_health_section_shape(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)

        result = ReportGenerator().generate(db, org.id, "customer_health", 30)

        headings = [s["heading"] for s in result["sections"]]
        assert headings == [
            "Health Distribution",
            "At-Risk Customers",
            "Health Score Trends",
        ]
        dist_rows = {
            row[0]: row[1] for row in result["sections"][0]["data"]["rows"]
        }
        assert dist_rows["at_risk"] == 1
        assert dist_rows["critical"] == 1
        assert dist_rows["healthy"] == 1

        at_risk = result["sections"][1]["data"]["rows"]
        assert [r[0] for r in at_risk] == ["critical@test.com", "at-risk@test.com"]

    def test_generate_feature_prioritization_section_shape(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)

        result = ReportGenerator().generate(
            db, org.id, "feature_prioritization", 30
        )

        headings = [s["heading"] for s in result["sections"]]
        assert headings == [
            "Request Volume",
            "Top Requests by Frequency",
            "Requests by Source",
            "Priority Matrix",
        ]
        volume_rows = {
            row[0]: row[1] for row in result["sections"][0]["data"]["rows"]
        }
        assert volume_rows["Total Feature Requests"] == 1
        assert result["sections"][1]["data"]["rows"][0][:2] == ["ui", 1]

    def test_generate_churn_risk_section_shape(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)

        result = ReportGenerator().generate(db, org.id, "churn_risk", 30)

        headings = [s["heading"] for s in result["sections"]]
        assert headings == [
            "Risk Overview",
            "High-Risk Customer Details",
            "Churn Trends",
            "Category Correlation",
        ]
        risk_rows = {
            row[0]: row[1] for row in result["sections"][0]["data"]["rows"]
        }
        assert risk_rows["at_risk"] == 1
        assert risk_rows["critical"] == 1

# ---------------------------------------------------------------------------
# Phase 2 — Narrative writer
# ---------------------------------------------------------------------------


class TestReportNarrative:
    def _report_data(self):
        return {
            "title": "Executive Summary — Jul 26 to Aug 25, 2026",
            "sections": [
                {
                    "heading": "Overview",
                    "data": {
                        "type": "table",
                        "columns": ["Metric", "Value"],
                        "rows": [
                            ["Total Feedback", 3],
                            ["Urgent Items", 1],
                            ["At-Risk Customers", 2],
                        ],
                    },
                },
                {
                    "heading": "Sentiment Analysis",
                    "data": {
                        "type": "table",
                        "columns": ["Sentiment", "Count"],
                        "rows": [
                            ["positive", 1],
                            ["negative", 1],
                            ["neutral", 1],
                        ],
                    },
                },
            ],
        }

    def test_returns_text_when_llm_configured(self, db):
        org = _make_org(db)

        class _FakeResponse:
            content = "A concise data-led narrative."

        with patch(
            "src.services.scheduled_report_narrative.call_llm_for_org",
            return_value=_FakeResponse(),
        ) as mock_call:
            narrative = generate_report_narrative(self._report_data(), org.id, db)

        assert narrative == "A concise data-led narrative."
        assert mock_call.call_count == 1
        kwargs = mock_call.call_args.kwargs
        assert kwargs["org_id"] == org.id
        assert kwargs["task_type"] == "report_narrative"
        prompt = kwargs["request"].messages[0]["content"]
        assert "Overview" in prompt
        assert "Total Feedback" in prompt

    def test_returns_none_when_resolver_returns_none(self, db):
        org = _make_org(db)

        with patch(
            "src.services.scheduled_report_narrative.call_llm_for_org",
            return_value=None,
        ):
            narrative = generate_report_narrative(self._report_data(), org.id, db)

        assert narrative is None

    def test_returns_none_when_completion_raises(self, db):
        org = _make_org(db)

        with patch(
            "src.services.scheduled_report_narrative.call_llm_for_org",
            side_effect=RuntimeError("provider down"),
        ):
            narrative = generate_report_narrative(self._report_data(), org.id, db)

        assert narrative is None

    def test_returns_none_when_org_id_missing(self, db):
        assert generate_report_narrative(self._report_data(), None, db) is None
        assert generate_report_narrative(self._report_data(), 1, None) is None


# ---------------------------------------------------------------------------
# Phase 3 — Helpers for task tests
# ---------------------------------------------------------------------------


def _make_schedule(
    db,
    org_id: int,
    *,
    report_type: str = "executive_summary",
    date_range_days: int = 30,
    cadence: str = "daily",
    hour_utc: int = 9,
    day_of_week=None,
    day_of_month=None,
    recipients=None,
    enabled: bool = True,
    last_run_at=None,
    created_by_user_id=None,
) -> ReportSchedule:
    schedule = ReportSchedule(
        organization_id=org_id,
        created_by_user_id=created_by_user_id,
        report_type=report_type,
        date_range_days=date_range_days,
        cadence=cadence,
        hour_utc=hour_utc,
        day_of_week=day_of_week,
        day_of_month=day_of_month,
        recipients=recipients if recipients is not None else ["ops@test.com"],
        enabled=enabled,
        last_run_at=last_run_at,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


class _FakeDatetime:
    """Stand-in for datetime with a fixed utcnow (task tests control 'now')."""

    _now = None

    @classmethod
    def utcnow(cls):
        return cls._now


def _freeze_now(dt):
    _FakeDatetime._now = dt
    return patch("src.tasks.scheduled_reports.datetime", _FakeDatetime)


def _run_task(db, task_name: str, *args):
    """Run a scheduled_reports task against the db fixture session."""
    import src.tasks.scheduled_reports as tasks

    with patch("src.tasks.scheduled_reports.get_db_session") as mock_db_ctx:
        mock_db_ctx.return_value.__enter__ = MagicMock(return_value=db)
        mock_db_ctx.return_value.__exit__ = MagicMock(return_value=False)
        return getattr(tasks, task_name)(*args)


# ---------------------------------------------------------------------------
# Phase 3 — Beat task: due filtering
# ---------------------------------------------------------------------------


class TestDueFiltering:
    def test_daily_due_only_when_hour_matches(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        _make_schedule(db, org.id, cadence="daily", hour_utc=9)

        with _freeze_now(datetime(2026, 8, 25, 10, 15)):
            result = _run_task(db, "generate_scheduled_reports")
            assert result["generated"] == 0
            assert result["skipped"] == 1

        with _freeze_now(datetime(2026, 8, 25, 9, 15)):
            result = _run_task(db, "generate_scheduled_reports")
            assert result["generated"] == 1
            assert result["errors"] == 0

    def test_weekly_due_only_on_matching_weekday(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        # 2026-08-25 is a Tuesday (weekday() == 1); schedule wants Mondays (0).
        _make_schedule(db, org.id, cadence="weekly", hour_utc=9, day_of_week=0)

        with _freeze_now(datetime(2026, 8, 25, 9, 15)):  # Tuesday
            result = _run_task(db, "generate_scheduled_reports")
            assert result["generated"] == 0
            assert result["skipped"] == 1

        with _freeze_now(datetime(2026, 8, 24, 9, 15)):  # Monday
            result = _run_task(db, "generate_scheduled_reports")
            assert result["generated"] == 1

    def test_monthly_due_only_on_matching_day_of_month(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        _make_schedule(db, org.id, cadence="monthly", hour_utc=9, day_of_month=15)

        with _freeze_now(datetime(2026, 8, 14, 9, 15)):
            result = _run_task(db, "generate_scheduled_reports")
            assert result["generated"] == 0
            assert result["skipped"] == 1

        with _freeze_now(datetime(2026, 8, 15, 9, 15)):
            result = _run_task(db, "generate_scheduled_reports")
            assert result["generated"] == 1

    def test_monthly_day_31_skipped_in_shorter_month(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        _make_schedule(db, org.id, cadence="monthly", hour_utc=9, day_of_month=31)

        # February 2026 has 28 days — never due, and no occurrence before now.
        with _freeze_now(datetime(2026, 2, 20, 9, 15)):
            result = _run_task(db, "generate_scheduled_reports")
            assert result["generated"] == 0
            assert result["skipped"] == 1

    def test_disabled_schedule_skipped(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        _make_schedule(db, org.id, cadence="daily", hour_utc=9, enabled=False)

        with _freeze_now(datetime(2026, 8, 25, 9, 15)):
            result = _run_task(db, "generate_scheduled_reports")
            assert result["generated"] == 0
            assert result["errors"] == 0
            assert db.query(Report).count() == 0


# ---------------------------------------------------------------------------
# Phase 3 — Atomic claim / exactly-once per window
# ---------------------------------------------------------------------------


class TestExactlyOnce:
    def test_second_invocation_same_window_skips(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        _make_schedule(db, org.id, cadence="daily", hour_utc=9)

        with _freeze_now(datetime(2026, 8, 25, 9, 15)):
            first = _run_task(db, "generate_scheduled_reports")
            second = _run_task(db, "generate_scheduled_reports")

        assert first["generated"] == 1
        assert second["generated"] == 0
        assert second["skipped"] == 1
        assert db.query(Report).count() == 1

    def test_concurrently_claimed_schedule_skipped(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        # last_run_at inside the current window -> claim-by-rowcount fails.
        _make_schedule(
            db, org.id, cadence="daily", hour_utc=9,
            last_run_at=datetime(2026, 8, 25, 8, 0),
        )

        with _freeze_now(datetime(2026, 8, 25, 9, 15)):
            result = _run_task(db, "generate_scheduled_reports")

        assert result["generated"] == 0
        assert result["skipped"] == 1
        assert db.query(Report).count() == 0

    def test_last_run_at_updated_on_generation(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        schedule = _make_schedule(db, org.id, cadence="daily", hour_utc=9)

        with _freeze_now(datetime(2026, 8, 25, 9, 15)):
            _run_task(db, "generate_scheduled_reports")

        db.refresh(schedule)
        assert schedule.last_run_at == datetime(2026, 8, 25, 9, 15)


# ---------------------------------------------------------------------------
# Phase 3 — Report row content
# ---------------------------------------------------------------------------


class TestReportRow:
    def test_report_row_content_and_metadata(self, db):
        org = _make_org(db)
        user = User(
            email="creator@test.com",
            organization_id=org.id,
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        _seed_report_data(db, org.id)
        schedule = _make_schedule(
            db, org.id,
            report_type="customer_health",
            date_range_days=30,
            cadence="daily",
            hour_utc=9,
            created_by_user_id=user.id,
        )

        with _freeze_now(datetime(2026, 8, 25, 9, 15)):
            result = _run_task(db, "generate_scheduled_reports")

        assert result["generated"] == 1
        report = db.query(Report).one()
        assert report.organization_id == org.id
        assert report.created_by_user_id == user.id
        assert report.conversation_id is None
        assert report.report_type == "customer_health"
        assert report.date_range_days == 30
        assert report.title == "Customer Health report — Last 30 days"
        assert report.pdf_generated is False
        assert isinstance(report.sections, list)
        assert report.sections[0]["heading"] == "Health Distribution"

        meta = report.report_metadata
        assert meta["schedule_id"] == schedule.id
        assert meta["source"] == "scheduled"
        assert meta["generated_at"] == "2026-08-25T09:15:00"
        assert meta["date_start"] == "2026-07-26T09:15:00"
        assert meta["date_end"] == "2026-08-25T09:15:00"

    def test_created_by_user_id_null_when_creator_gone(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        _make_schedule(
            db, org.id, cadence="daily", hour_utc=9, created_by_user_id=99999
        )

        with _freeze_now(datetime(2026, 8, 25, 9, 15)):
            result = _run_task(db, "generate_scheduled_reports")

        assert result["generated"] == 1
        report = db.query(Report).one()
        assert report.created_by_user_id is None

    def test_narrative_present_when_llm_mocked(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        _make_schedule(db, org.id, cadence="daily", hour_utc=9)

        with _freeze_now(datetime(2026, 8, 25, 9, 15)), patch(
            "src.tasks.scheduled_reports.generate_report_narrative",
            return_value="Narrative summary from the mocked LLM.",
        ):
            _run_task(db, "generate_scheduled_reports")

        report = db.query(Report).one()
        assert report.report_metadata["model_used"] == "gpt-4o-mini"

    def test_data_only_when_llm_absent(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        _make_schedule(db, org.id, cadence="daily", hour_utc=9)

        with _freeze_now(datetime(2026, 8, 25, 9, 15)), patch(
            "src.tasks.scheduled_reports.generate_report_narrative",
            return_value=None,
        ):
            result = _run_task(db, "generate_scheduled_reports")

        assert result["generated"] == 1
        report = db.query(Report).one()
        assert "model_used" not in report.report_metadata
        assert all(s["narrative"] == "" for s in report.sections)


# ---------------------------------------------------------------------------
# Phase 3 — Email dispatch
# ---------------------------------------------------------------------------


class TestEmailDispatch:
    def test_no_email_call_when_recipients_empty(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        _make_schedule(db, org.id, cadence="daily", hour_utc=9, recipients=[])

        with _freeze_now(datetime(2026, 8, 25, 9, 15)), patch(
            "src.tasks.scheduled_reports.send_scheduled_report_email"
        ) as mock_send:
            result = _run_task(db, "generate_scheduled_reports")

        assert result["generated"] == 1
        mock_send.assert_not_called()

    def test_email_sent_to_each_recipient_after_commit(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        _make_schedule(
            db, org.id, cadence="daily", hour_utc=9,
            recipients=["ops@test.com", "cs@test.com"],
        )

        with _freeze_now(datetime(2026, 8, 25, 9, 15)), patch(
            "src.tasks.scheduled_reports.send_scheduled_report_email"
        ) as mock_send:
            result = _run_task(db, "generate_scheduled_reports")

        assert result["generated"] == 1
        assert mock_send.call_count == 2
        emails = {c.kwargs["to_email"] for c in mock_send.call_args_list}
        assert emails == {"ops@test.com", "cs@test.com"}
        # Report row is committed even though emailing happens after.
        assert db.query(Report).count() == 1

    def test_email_failure_does_not_fail_run(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        _make_schedule(db, org.id, cadence="daily", hour_utc=9)

        with _freeze_now(datetime(2026, 8, 25, 9, 15)), patch(
            "src.tasks.scheduled_reports.send_scheduled_report_email",
            side_effect=RuntimeError("resend down"),
        ):
            result = _run_task(db, "generate_scheduled_reports")

        assert result["generated"] == 1
        assert result["errors"] == 0
        assert db.query(Report).count() == 1


# ---------------------------------------------------------------------------
# Phase 3 — Per-schedule exception isolation
# ---------------------------------------------------------------------------


class TestExceptionIsolation:
    def test_one_bad_schedule_does_not_abort_batch(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        # Broken schedule: unknown cadence -> cutoff computation raises.
        _make_schedule(db, org.id, cadence="hourly", hour_utc=9)
        _make_schedule(db, org.id, cadence="daily", hour_utc=9)

        with _freeze_now(datetime(2026, 8, 25, 9, 15)):
            result = _run_task(db, "generate_scheduled_reports")

        assert result["generated"] == 1
        assert result["errors"] == 1
        assert db.query(Report).count() == 1

    def test_failed_schedule_rolls_back_claim(self, db):
        """A failed schedule must not leave last_run_at set (rollback)."""
        org = _make_org(db)
        _seed_report_data(db, org.id)
        bad = _make_schedule(db, org.id, cadence="hourly", hour_utc=9)

        with _freeze_now(datetime(2026, 8, 25, 9, 15)):
            result = _run_task(db, "generate_scheduled_reports")

        assert result["errors"] == 1
        db.refresh(bad)
        assert bad.last_run_at is None


# ---------------------------------------------------------------------------
# Phase 3 — generate_schedule_once (manual sync)
# ---------------------------------------------------------------------------


class TestGenerateScheduleOnce:
    def test_unknown_schedule_id_returns_not_found(self, db):
        result = _run_task(db, "generate_schedule_once", 12345)
        assert result["status"] == "not_found"

    def test_generates_and_is_exactly_once_per_window(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        schedule = _make_schedule(db, org.id, cadence="daily", hour_utc=9)

        with _freeze_now(datetime(2026, 8, 25, 9, 15)):
            first = _run_task(db, "generate_schedule_once", schedule.id)
            second = _run_task(db, "generate_schedule_once", schedule.id)

        assert first["status"] == "generated"
        assert second["status"] == "skipped"
        assert db.query(Report).count() == 1

    def test_disabled_schedule_skipped(self, db):
        org = _make_org(db)
        _seed_report_data(db, org.id)
        schedule = _make_schedule(
            db, org.id, cadence="daily", hour_utc=9, enabled=False
        )

        with _freeze_now(datetime(2026, 8, 25, 9, 15)):
            result = _run_task(db, "generate_schedule_once", schedule.id)

        assert result["status"] == "skipped"
        assert db.query(Report).count() == 0
