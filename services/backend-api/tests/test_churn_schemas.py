"""
TDD tests for Advanced Churn Prediction Pydantic schemas (M4.1 Phase 1.3).

RED phase: all tests fail until schemas are implemented.
"""

import pytest
from datetime import datetime, date, timezone
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# ChurnEvent schema tests (20–27)
# ---------------------------------------------------------------------------

class TestChurnEventCreateSchema:

    def test_churn_event_create_schema_requires_reason_code(self):
        """ChurnEventCreate schema raises if reason_code is missing."""
        from src.schemas.churn_event import ChurnEventCreate

        with pytest.raises(ValidationError):
            ChurnEventCreate(
                customer_email="user@example.com",
                churned_at=datetime(2026, 1, 15),
                source="manual",
                # reason_code omitted
            )

    def test_churn_event_create_schema_rejects_invalid_reason_code(self):
        """ChurnEventCreate raises ValidationError for unknown reason_code."""
        from src.schemas.churn_event import ChurnEventCreate

        with pytest.raises(ValidationError):
            ChurnEventCreate(
                customer_email="user@example.com",
                churned_at=datetime(2026, 1, 15),
                reason_code="not_a_valid_code",
                source="manual",
            )

    def test_churn_event_create_schema_accepts_optional_reason_text(self):
        """reason_text is optional; model is valid with or without it."""
        from src.schemas.churn_event import ChurnEventCreate

        # Without reason_text
        schema1 = ChurnEventCreate(
            customer_email="user@example.com",
            churned_at=datetime(2026, 1, 15),
            reason_code="price",
            source="manual",
        )
        assert schema1.reason_text is None

        # With reason_text
        schema2 = ChurnEventCreate(
            customer_email="user@example.com",
            churned_at=datetime(2026, 1, 15),
            reason_code="price",
            source="manual",
            reason_text="Too expensive for our budget.",
        )
        assert schema2.reason_text == "Too expensive for our budget."

    def test_churn_event_create_schema_normalizes_email_lowercase(self):
        """customer_email is normalized to lowercase by the schema."""
        from src.schemas.churn_event import ChurnEventCreate

        schema = ChurnEventCreate(
            customer_email="User@Example.COM",
            churned_at=datetime(2026, 1, 15),
            reason_code="competitor",
            source="manual",
        )
        assert schema.customer_email == "user@example.com"


class TestChurnEventResponseSchema:

    def test_churn_event_response_schema_serializes_datetime_as_iso(self):
        """ChurnEventResponse serializes datetime fields as ISO strings."""
        from src.schemas.churn_event import ChurnEventResponse

        now = datetime(2026, 5, 20, 10, 30, 0)
        response = ChurnEventResponse(
            id=1,
            organization_id=1,
            customer_email="user@example.com",
            churned_at=now,
            reason_code="price",
            source="manual",
            created_at=now,
            updated_at=now,
        )
        dumped = response.model_dump(mode="json")
        assert isinstance(dumped["churned_at"], str)
        assert "2026" in dumped["churned_at"]


class TestChurnEventBulkSchema:

    def test_churn_event_bulk_schema_requires_non_empty_email_list(self):
        """ChurnEventBulkCreate requires at least one email."""
        from src.schemas.churn_event import ChurnEventBulkCreate

        with pytest.raises(ValidationError):
            ChurnEventBulkCreate(
                emails=[],  # empty list
                churned_at=datetime(2026, 1, 15),
                reason_code="price",
            )

        # Valid case
        schema = ChurnEventBulkCreate(
            emails=["a@example.com", "b@example.com"],
            churned_at=datetime(2026, 1, 15),
            reason_code="price",
        )
        assert len(schema.emails) == 2


class TestChurnEventCsvRowSchema:

    def test_churn_event_csv_row_schema_validates_iso_date(self):
        """ChurnEventCsvRow rejects non-ISO date strings."""
        from src.schemas.churn_event import ChurnEventCsvRow

        with pytest.raises(ValidationError):
            ChurnEventCsvRow(
                email="user@example.com",
                churned_at="15/01/2026",  # not ISO format
                reason_code="price",
            )

        # Valid ISO date
        row = ChurnEventCsvRow(
            email="user@example.com",
            churned_at="2026-01-15",
            reason_code="price",
        )
        assert row.email == "user@example.com"

    def test_churn_event_csv_row_schema_validates_email_format(self):
        """ChurnEventCsvRow rejects malformed emails."""
        from src.schemas.churn_event import ChurnEventCsvRow

        with pytest.raises(ValidationError):
            ChurnEventCsvRow(
                email="not-an-email",
                churned_at="2026-01-15",
                reason_code="price",
            )

        # Valid email
        row = ChurnEventCsvRow(
            email="Valid@Example.COM",
            churned_at="2026-01-15",
            reason_code="price",
        )
        assert row.email == "valid@example.com"  # normalized


# ---------------------------------------------------------------------------
# ChurnPlaybook schema tests (28–29)
# ---------------------------------------------------------------------------

class TestChurnPlaybookCreateSchema:

    def test_playbook_create_schema_rejects_inverted_probability_range(self):
        """PlaybookCreate raises ValidationError when probability_min >= probability_max."""
        from src.schemas.churn_playbook import PlaybookCreate

        with pytest.raises(ValidationError):
            PlaybookCreate(
                name="Bad Playbook",
                probability_min=0.70,
                probability_max=0.50,  # inverted
                action_sequence=[{"type": "notify"}],
            )

        # Equal values also invalid
        with pytest.raises(ValidationError):
            PlaybookCreate(
                name="Equal Playbook",
                probability_min=0.60,
                probability_max=0.60,
                action_sequence=[{"type": "notify"}],
            )

    def test_playbook_create_schema_requires_action_sequence_non_empty(self):
        """PlaybookCreate requires at least one action in action_sequence."""
        from src.schemas.churn_playbook import PlaybookCreate

        with pytest.raises(ValidationError):
            PlaybookCreate(
                name="Empty Actions",
                probability_min=0.50,
                probability_max=0.80,
                action_sequence=[],  # empty
            )

        # Valid case
        schema = PlaybookCreate(
            name="Real Playbook",
            probability_min=0.50,
            probability_max=0.85,
            action_sequence=[{"type": "send_slack_alert", "channel": "#cs-leads"}],
        )
        assert len(schema.action_sequence) == 1
