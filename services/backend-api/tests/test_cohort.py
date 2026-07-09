"""
TDD tests — bulk-actions-api aspect (segment-actions feature), Phase 2.

Coverage:
  - `Cohort` validator: exactly one of emails/filter (else ValueError -> 422
    when used as a request body).
  - `resolve_cohort` by emails: normalize (.strip().lower()), org-scope,
    skip-with-count unknown/cross-org emails.
  - `resolve_cohort` by filter: parity with `list_customers` for identical
    params (reuses `_apply_customer_filters`).
  - `count_cohort` cheap-count helper.

See docs/planning/segment-actions/bulk-actions-api/{plan_20260709.md,spec.md}.
"""
import pytest
from datetime import datetime
from pydantic import ValidationError
from sqlalchemy.orm import Session

from src.models.customer_health import CustomerHealth
from src.models.organization import Organization
from src.schemas.cohort import Cohort, CohortFilter, BulkActionSummary


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(name="Cohort Co", plan="business")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


@pytest.fixture
def other_org(db: Session) -> Organization:
    o = Organization(name="Other Cohort Co", plan="business")
    db.add(o)
    db.commit()
    db.refresh(o)
    return o


def make_ch(db, org, email, *, risk_level="moderate", segment=None, is_archived=False) -> CustomerHealth:
    record = CustomerHealth(
        organization_id=org.id,
        customer_email=email,
        health_score=60,
        risk_level=risk_level,
        feedback_count=5,
        confidence_level="medium",
        last_feedback_at=datetime.utcnow(),
        is_archived=is_archived,
        churn_risk_component=50,
        sentiment_component=60,
        resolution_component=70,
        frequency_component=55,
        segment=segment,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


# ---------------------------------------------------------------------------
# Cohort schema validator
# ---------------------------------------------------------------------------

class TestCohortValidator:
    def test_emails_only_is_valid(self):
        c = Cohort(emails=["a@example.com"])
        assert c.emails == ["a@example.com"]
        assert c.filter is None

    def test_filter_only_is_valid(self):
        c = Cohort(filter=CohortFilter(segment="dormant"))
        assert c.filter.segment == "dormant"
        assert c.emails is None

    def test_both_set_raises(self):
        with pytest.raises(ValidationError):
            Cohort(emails=["a@example.com"], filter=CohortFilter(segment="dormant"))

    def test_neither_set_raises(self):
        with pytest.raises(ValidationError):
            Cohort()

    def test_empty_email_list_is_valid_shape(self):
        # Explicit empty list still counts as "emails provided" (resolves to 0 matches).
        c = Cohort(emails=[])
        assert c.emails == []


class TestBulkActionSummarySchema:
    def test_defaults_and_fields(self):
        s = BulkActionSummary(matched=5, updated=3, skipped=2, errors=["x"])
        assert s.matched == 5
        assert s.updated == 3
        assert s.skipped == 2
        assert s.errors == ["x"]

    def test_errors_defaults_to_empty_list(self):
        s = BulkActionSummary(matched=0, updated=0, skipped=0)
        assert s.errors == []


# ---------------------------------------------------------------------------
# resolve_cohort — by emails
# ---------------------------------------------------------------------------

class TestResolveCohortByEmails:
    def test_normalizes_case_and_whitespace(self, db: Session, org: Organization):
        from src.services.cohort_service import resolve_cohort

        make_ch(db, org, "alice@example.com")
        cohort = Cohort(emails=["  ALICE@Example.com  "])
        rows, skipped = resolve_cohort(db, org, cohort)
        assert [r.customer_email for r in rows] == ["alice@example.com"]
        assert skipped == 0

    def test_unknown_email_is_skipped_and_counted(self, db: Session, org: Organization):
        from src.services.cohort_service import resolve_cohort

        make_ch(db, org, "known@example.com")
        cohort = Cohort(emails=["known@example.com", "ghost@example.com"])
        rows, skipped = resolve_cohort(db, org, cohort)
        assert [r.customer_email for r in rows] == ["known@example.com"]
        assert skipped == 1

    def test_cross_org_email_is_skipped_and_counted(
        self, db: Session, org: Organization, other_org: Organization
    ):
        from src.services.cohort_service import resolve_cohort

        make_ch(db, org, "mine@example.com")
        make_ch(db, other_org, "theirs@example.com")
        cohort = Cohort(emails=["mine@example.com", "theirs@example.com"])
        rows, skipped = resolve_cohort(db, org, cohort)
        assert [r.customer_email for r in rows] == ["mine@example.com"]
        assert skipped == 1

    def test_empty_email_list_resolves_to_nothing(self, db: Session, org: Organization):
        from src.services.cohort_service import resolve_cohort

        cohort = Cohort(emails=[])
        rows, skipped = resolve_cohort(db, org, cohort)
        assert rows == []
        assert skipped == 0


# ---------------------------------------------------------------------------
# resolve_cohort — by filter (parity with list_customers)
# ---------------------------------------------------------------------------

class TestResolveCohortByFilter:
    def test_filter_matches_list_customers_output(self, db: Session, org: Organization):
        from src.services.cohort_service import resolve_cohort

        make_ch(db, org, "risky@example.com", risk_level="at_risk", segment="silent_churner")
        make_ch(db, org, "healthy@example.com", risk_level="healthy", segment="happy_advocate")

        cohort = Cohort(filter=CohortFilter(segment="silent_churner"))
        rows, skipped = resolve_cohort(db, org, cohort)
        assert [r.customer_email for r in rows] == ["risky@example.com"]
        assert skipped == 0

    def test_filter_is_org_scoped(self, db: Session, org: Organization, other_org: Organization):
        from src.services.cohort_service import resolve_cohort

        make_ch(db, other_org, "theirs@example.com", segment="dormant")
        cohort = Cohort(filter=CohortFilter(segment="dormant"))
        rows, skipped = resolve_cohort(db, org, cohort)
        assert rows == []

    def test_filter_excludes_archived_by_default(self, db: Session, org: Organization):
        from src.services.cohort_service import resolve_cohort

        make_ch(db, org, "archived@example.com", is_archived=True)
        make_ch(db, org, "active@example.com", is_archived=False)
        cohort = Cohort(filter=CohortFilter())
        rows, _ = resolve_cohort(db, org, cohort)
        assert [r.customer_email for r in rows] == ["active@example.com"]

    def test_filter_include_archived_true(self, db: Session, org: Organization):
        from src.services.cohort_service import resolve_cohort

        make_ch(db, org, "archived@example.com", is_archived=True)
        cohort = Cohort(filter=CohortFilter(include_archived=True))
        rows, _ = resolve_cohort(db, org, cohort)
        emails = {r.customer_email for r in rows}
        assert "archived@example.com" in emails


class TestCountCohort:
    def test_count_matches_resolve_length(self, db: Session, org: Organization):
        from src.services.cohort_service import resolve_cohort, count_cohort

        make_ch(db, org, "a@example.com", segment="dormant")
        make_ch(db, org, "b@example.com", segment="dormant")
        make_ch(db, org, "c@example.com", segment="new")

        cohort = Cohort(filter=CohortFilter(segment="dormant"))
        rows, _ = resolve_cohort(db, org, cohort)
        assert count_cohort(db, org, cohort) == len(rows) == 2
