"""
Pydantic schemas for CustomerChurnEvent (M4.1).

Separate from src/api/schemas.py to keep churn schemas self-contained.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from src.models.churn_event import CHURN_REASON_CODES, CHURN_EVENT_SOURCES


class ChurnEventCreate(BaseModel):
    """Schema for creating a single churn event (manual mark)."""

    customer_email: str = Field(..., description="Customer email — normalized to lowercase")
    churned_at: datetime = Field(default_factory=datetime.utcnow)
    reason_code: str = Field(..., description=f"One of: {', '.join(CHURN_REASON_CODES)}")
    reason_text: Optional[str] = Field(None, max_length=2000)
    source: str = Field(default="manual", description=f"One of: {', '.join(CHURN_EVENT_SOURCES)}")

    @field_validator("customer_email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("reason_code")
    @classmethod
    def validate_reason_code(cls, v: str) -> str:
        if v not in CHURN_REASON_CODES:
            raise ValueError(
                f"reason_code must be one of: {', '.join(CHURN_REASON_CODES)}"
            )
        return v

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        if v not in CHURN_EVENT_SOURCES:
            raise ValueError(
                f"source must be one of: {', '.join(CHURN_EVENT_SOURCES)}"
            )
        return v


class ChurnEventResponse(BaseModel):
    """Schema for serializing a CustomerChurnEvent row."""

    id: int
    organization_id: int
    customer_email: str
    churned_at: datetime
    reason_code: str
    reason_text: Optional[str] = None
    recovered_at: Optional[datetime] = None
    marked_by_user_id: Optional[int] = None
    source: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChurnEventBulkCreate(BaseModel):
    """Schema for bulk-marking multiple customers as churned."""

    emails: List[str] = Field(..., min_length=1, description="Must contain at least one email")
    churned_at: datetime = Field(default_factory=datetime.utcnow)
    reason_code: str
    reason_text: Optional[str] = None

    @field_validator("emails")
    @classmethod
    def validate_emails_non_empty(cls, v: List[str]) -> List[str]:
        if len(v) == 0:
            raise ValueError("emails list must contain at least one email address")
        return [email.strip().lower() for email in v]

    @field_validator("reason_code")
    @classmethod
    def validate_reason_code(cls, v: str) -> str:
        if v not in CHURN_REASON_CODES:
            raise ValueError(
                f"reason_code must be one of: {', '.join(CHURN_REASON_CODES)}"
            )
        return v


class ChurnEventCsvRow(BaseModel):
    """Schema for a single row from a CSV churn import file.

    Columns: email, churned_at (ISO date), reason_code (optional), reason_text (optional).
    """

    email: str
    churned_at: str = Field(..., description="ISO 8601 date string, e.g. 2026-01-15")
    reason_code: Optional[str] = Field(default="other")
    reason_text: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_and_normalize_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError(f"Invalid email format: {v!r}")
        return v

    @field_validator("churned_at")
    @classmethod
    def validate_iso_date(cls, v: str) -> str:
        """Accept ISO date (YYYY-MM-DD) or ISO datetime strings."""
        v = v.strip()
        # Try parsing as date first, then datetime
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                datetime.strptime(v, fmt)
                return v
            except ValueError:
                continue
        raise ValueError(
            f"churned_at must be an ISO date (YYYY-MM-DD) or datetime, got: {v!r}"
        )

    @field_validator("reason_code")
    @classmethod
    def validate_reason_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return "other"
        if v not in CHURN_REASON_CODES:
            raise ValueError(
                f"reason_code must be one of: {', '.join(CHURN_REASON_CODES)}"
            )
        return v
