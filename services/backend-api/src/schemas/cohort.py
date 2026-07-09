"""
Shared cohort contract — segment-actions / bulk-actions-api.

`Cohort` is how an operator selects a set of customers to act on, either by
an explicit email list or by the same filter vocabulary as
`GET /api/v1/customers/`. Consumed by:

  - this aspect's `POST /customers/bulk/tags` and
    `POST /customers/bulk/assign-owner`
  - the (later) `playbook-cohort-run` aspect, which imports `Cohort` and
    `resolve_cohort` from here to avoid a second implementation.
"""
from typing import List, Optional

from pydantic import BaseModel, model_validator


class CohortFilter(BaseModel):
    """Same filter vocabulary as `list_customers` (GET /api/v1/customers/)."""

    segment: Optional[str] = None
    risk_level: Optional[str] = None
    search: Optional[str] = None
    include_archived: bool = False


class Cohort(BaseModel):
    """A customer selection: exactly one of `emails` or `filter` must be set."""

    emails: Optional[List[str]] = None
    filter: Optional[CohortFilter] = None

    @model_validator(mode="after")
    def _exactly_one_of_emails_or_filter(self) -> "Cohort":
        has_emails = self.emails is not None
        has_filter = self.filter is not None
        if has_emails == has_filter:
            raise ValueError(
                "Exactly one of 'emails' or 'filter' must be provided (not both, not neither)"
            )
        return self


class BulkActionSummary(BaseModel):
    """Summary returned by every bulk-action endpoint (tags, assign-owner, ...)."""

    matched: int
    updated: int
    skipped: int
    errors: List[str] = []
