"""
Pydantic schemas for ChurnPlaybook and ChurnPlaybookExecution (M4.1).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from src.models.churn_playbook import PLAYBOOK_EXECUTION_STATUSES, PLAYBOOK_TRIGGER_SOURCES


class PlaybookCreate(BaseModel):
    """Schema for creating a new churn playbook."""

    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None
    probability_min: float = Field(..., ge=0.0, le=1.0)
    probability_max: float = Field(..., ge=0.0, le=1.0)
    action_sequence: List[Dict[str, Any]] = Field(
        ..., description="Must contain at least one action"
    )
    source_template_id: Optional[int] = None

    @model_validator(mode="after")
    def validate_probability_range(self) -> "PlaybookCreate":
        if self.probability_min >= self.probability_max:
            raise ValueError(
                "probability_min must be strictly less than probability_max"
            )
        return self

    @field_validator("action_sequence")
    @classmethod
    def validate_action_sequence_non_empty(
        cls, v: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        if len(v) == 0:
            raise ValueError("action_sequence must contain at least one action")
        return v


class PlaybookUpdate(BaseModel):
    """Schema for updating an existing org playbook."""

    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = None
    probability_min: Optional[float] = Field(None, ge=0.0, le=1.0)
    probability_max: Optional[float] = Field(None, ge=0.0, le=1.0)
    action_sequence: Optional[List[Dict[str, Any]]] = None
    is_active: Optional[bool] = None

    @model_validator(mode="after")
    def validate_probability_range(self) -> "PlaybookUpdate":
        if self.probability_min is not None and self.probability_max is not None:
            if self.probability_min >= self.probability_max:
                raise ValueError(
                    "probability_min must be strictly less than probability_max"
                )
        return self


class PlaybookResponse(BaseModel):
    """Schema for serializing a ChurnPlaybook row."""

    id: int
    organization_id: Optional[int] = None
    name: str
    description: Optional[str] = None
    probability_min: float
    probability_max: float
    action_sequence: List[Dict[str, Any]]
    is_template: bool
    is_active: bool
    source_template_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PlaybookRunRequest(BaseModel):
    """Schema for triggering a playbook run on a single customer."""

    customer_email: str

    @field_validator("customer_email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class PlaybookExecutionResponse(BaseModel):
    """Schema for serializing a ChurnPlaybookExecution row."""

    id: int
    playbook_id: int
    organization_id: int
    customer_email: str
    triggered_by: str
    triggered_by_user_id: Optional[int] = None
    status: str
    action_log: List[Dict[str, Any]]
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True
