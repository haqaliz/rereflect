"""
Pydantic schemas for ChurnLabelSuggestion — review-queue aspect.

Confirm is the ONLY path that turns a CRM-sourced suggestion into a
trainable CustomerChurnEvent(source='manual'). See
docs/planning/crm-churn-labels/review-queue/spec.md.
"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.models.churn_event import CHURN_REASON_CODES


class ChurnSuggestionResponse(BaseModel):
    """Whole-row serialization of a ChurnLabelSuggestion."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int
    customer_email: str
    provider: str
    external_opportunity_id: str
    suggested_churned_at: datetime
    evidence: Optional[dict] = None
    status: str
    reviewed_by_user_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    churn_event_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


class ChurnSuggestionListResponse(BaseModel):
    """Paginated list of churn suggestions."""

    items: List[ChurnSuggestionResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Cohort — this aspect's own filter vocabulary (NOT schemas/cohort.py's
# customer filter — see plan §7 delta 2).
# ---------------------------------------------------------------------------


class SuggestionCohortFilter(BaseModel):
    """Filter vocabulary for a bulk-review cohort — suggestion-shaped, not
    customer-shaped (segment/risk_level would be meaningless here)."""

    status: Optional[str] = None
    provider: Optional[str] = None
    search: Optional[str] = None


class SuggestionCohort(BaseModel):
    """A suggestion selection: exactly one of `emails` or `filter` must be set.

    Validator shape copied verbatim from `schemas/cohort.py:33-41` — the
    *contract shape* is reused, the *filter vocabulary* is this aspect's own.
    """

    emails: Optional[List[str]] = None
    filter: Optional[SuggestionCohortFilter] = None

    @model_validator(mode="after")
    def _exactly_one_of_emails_or_filter(self) -> "SuggestionCohort":
        has_emails = self.emails is not None
        has_filter = self.filter is not None
        if has_emails == has_filter:
            raise ValueError(
                "Exactly one of 'emails' or 'filter' must be provided (not both, not neither)"
            )
        return self


# ---------------------------------------------------------------------------
# Confirm / reject / bulk request-response schemas
# ---------------------------------------------------------------------------


class ConfirmRequest(BaseModel):
    """Body for POST .../{id}/confirm. reason_code is REQUIRED (Finding 6 —
    no new enum value; reuse CHURN_REASON_CODES)."""

    reason_code: str = Field(..., description=f"One of: {', '.join(CHURN_REASON_CODES)}")
    reason_text: Optional[str] = Field(None, max_length=2000)

    @field_validator("reason_code")
    @classmethod
    def validate_reason_code(cls, v: str) -> str:
        if v not in CHURN_REASON_CODES:
            raise ValueError(f"reason_code must be one of: {', '.join(CHURN_REASON_CODES)}")
        return v


class SuggestionActionResponse(BaseModel):
    """Response for the single confirm/reject routes — the ACTION outcome
    on the wire (spec §2: `{id, status: confirmed|skipped, churn_event_id,
    reason?}`), not the raw persisted row. This matters because a collided
    confirm always persists `suggestion.status == 'confirmed'` in the DB
    (R-B — it resolves out of the queue) while the wire must say
    `'skipped'` so the operator knows an event wasn't created by their
    action. Reject's wire status is 'rejected' on success, 'skipped' when
    the target wasn't pending.
    """

    id: int
    status: Literal["confirmed", "rejected", "skipped"]
    churn_event_id: Optional[int] = None
    reason: Optional[str] = None


class RejectRequest(BaseModel):
    """Body for POST .../{id}/reject.

    NOTE: `note` is accepted but persisted nowhere today — the model has no
    note column. This is a documented gap (not a silent discard like
    RecoverRequest.note): a `review_note` column is the named follow-up.
    """

    note: Optional[str] = Field(None, max_length=2000)


class BulkReviewRequest(BaseModel):
    """Body for POST .../bulk. `reason_code` is required when
    action == 'confirm' (validated below); ignored for 'reject'."""

    action: Literal["confirm", "reject"]
    cohort: SuggestionCohort
    reason_code: Optional[str] = None
    reason_text: Optional[str] = Field(None, max_length=2000)

    @model_validator(mode="after")
    def _reason_code_required_for_confirm(self) -> "BulkReviewRequest":
        if self.action == "confirm":
            if not self.reason_code:
                raise ValueError("reason_code is required when action='confirm'")
            if self.reason_code not in CHURN_REASON_CODES:
                raise ValueError(
                    f"reason_code must be one of: {', '.join(CHURN_REASON_CODES)}"
                )
        return self


class BulkReviewResultItem(BaseModel):
    """Per-id result entry in the bulk response, deduped input order."""

    id: int
    status: Literal["confirmed", "skipped", "error"]
    reason: Optional[str] = None


class BulkReviewResponse(BaseModel):
    """Bulk result contract — reuses the shipped public-bulk shape
    (public_api.py:378-382), with `confirmed` in place of upstream's
    `updated` (spec §6), plus additive `capped`/`cap` (plan §7 delta 3):
    the invariant `confirmed + skipped + errors == len(results) == matched`
    holds exactly when `capped is False`.
    """

    matched: int
    confirmed: int
    skipped: int
    results: List[BulkReviewResultItem]
    capped: bool = False
    cap: Optional[int] = None
