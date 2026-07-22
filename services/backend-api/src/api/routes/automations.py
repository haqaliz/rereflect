"""
AI Workflow Automation API (M4.4 — Phase 1).

Endpoints:
  GET    /api/v1/automations                              List org rules
  POST   /api/v1/automations                              Create rule (Admin+)
  GET    /api/v1/automations/templates                    List pre-built templates
  POST   /api/v1/automations/templates/{template_id}/enable  Enable template (Admin+)
  GET    /api/v1/automations/{id}                         Get rule
  PUT    /api/v1/automations/{id}                         Update rule (Admin+)
  DELETE /api/v1/automations/{id}                         Delete rule (Admin+)
  PATCH  /api/v1/automations/{id}/toggle                  Pause / resume rule (Admin+)
  GET    /api/v1/automations/{id}/executions              Execution log (last 50)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from src.api.dependencies import (
    get_current_org,
    get_current_user,
    require_admin_or_owner,
)
from src.config.automation_templates import AUTOMATION_TEMPLATES, TEMPLATES_BY_ID
from src.config.plans import get_automation_rule_limit, has_feature
from src.database.session import get_db
from src.models.automation_execution import AutomationExecution
from src.models.automation_rule import RULE_MODES, AutomationRule
from src.services.automation_engine import seed_churn_cooldowns
from src.models.churn_playbook import ChurnPlaybook
from src.models.organization import Organization
from src.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/automations", tags=["automations"])

# ---------------------------------------------------------------------------
# Valid values
# ---------------------------------------------------------------------------

VALID_TRIGGER_TYPES = frozenset({
    "health_score_threshold",
    "sentiment_pattern",
    "churn_risk_level_change",
    "feedback_category_match",
    "churn_probability_threshold",
    "usage_trend",
})

VALID_ACTION_TYPES = frozenset({
    "auto_assign",
    "change_status",
    "send_notification",
    "draft_response",
    "run_playbook",
})

VALID_WORKFLOW_STATUSES = frozenset({"new", "in_review", "resolved", "closed"})
VALID_CHURN_LEVELS = frozenset({"at_risk", "critical"})
VALID_DRAFT_TONES = frozenset({"professional", "empathetic", "friendly", "concise"})


# ---------------------------------------------------------------------------
# Pydantic — trigger config schemas
# ---------------------------------------------------------------------------

class HealthScoreConfig(BaseModel):
    threshold: int = Field(..., ge=1, le=99)
    direction: str

    @field_validator("direction")
    @classmethod
    def direction_must_be_below(cls, v: str) -> str:
        if v != "below":
            raise ValueError("direction must be 'below'")
        return v


class SentimentPatternConfig(BaseModel):
    count: int = Field(..., ge=1, le=20)
    days: int = Field(..., ge=1, le=30)
    sentiment: str = "negative"


class ChurnRiskConfig(BaseModel):
    target_level: str
    from_levels: Optional[List[str]] = None

    @field_validator("target_level")
    @classmethod
    def validate_target_level(cls, v: str) -> str:
        if v not in VALID_CHURN_LEVELS:
            raise ValueError(f"target_level must be one of {sorted(VALID_CHURN_LEVELS)}")
        return v


class ChurnProbabilityConfig(BaseModel):
    threshold: float = Field(..., ge=0.0, le=1.0)
    direction: str = "above"

    @field_validator("direction")
    @classmethod
    def direction_must_be_above(cls, v: str) -> str:
        if v != "above":
            raise ValueError("direction must be 'above'")
        return v


VALID_USAGE_TREND_STATES = frozenset({"declining", "sharp_decline"})


class UsageTrendConfig(BaseModel):
    model_config = {"extra": "forbid"}

    states: List[str] = Field(..., min_length=1)

    @field_validator("states")
    @classmethod
    def validate_states(cls, v: List[str]) -> List[str]:
        invalid = [s for s in v if s not in VALID_USAGE_TREND_STATES]
        if invalid:
            raise ValueError(
                f"states must each be one of {sorted(VALID_USAGE_TREND_STATES)}; "
                f"got {invalid}. 'stable' and 'insufficient_history' cannot be "
                f"entered as a worsening transition, so a rule targeting them "
                f"could never fire."
            )
        return v


class FeedbackCategoryConfig(BaseModel):
    categories: List[str] = Field(..., min_length=1)
    is_urgent: Optional[bool] = None
    severity: Optional[str] = None

    @field_validator("categories")
    @classmethod
    def categories_must_not_be_empty(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("categories must be a non-empty array")
        return v


# ---------------------------------------------------------------------------
# Pydantic — action config schemas
# ---------------------------------------------------------------------------

class AutoAssignConfig(BaseModel):
    assign_to: str  # user:{id} | role:owner | role:admin | round_robin


class ChangeStatusConfig(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in VALID_WORKFLOW_STATUSES:
            raise ValueError(f"status must be one of {sorted(VALID_WORKFLOW_STATUSES)}")
        return v


class SendNotificationConfig(BaseModel):
    recipients: str  # assignee | admins | owner | user:{id}
    channels: List[str]
    message_template: Optional[str] = None


class DraftResponseConfig(BaseModel):
    tone: str = "professional"
    template_id: Optional[int] = None

    @field_validator("tone")
    @classmethod
    def validate_tone(cls, v: str) -> str:
        if v not in VALID_DRAFT_TONES:
            raise ValueError(f"tone must be one of {sorted(VALID_DRAFT_TONES)}")
        return v


class RunPlaybookConfig(BaseModel):
    playbook_id: int = Field(..., ge=1)
    # Ownership (org-scoped, active) is checked in the handler — a schema
    # can't hit the DB.


# ---------------------------------------------------------------------------
# Pydantic — trigger / action wrappers
# ---------------------------------------------------------------------------

class TriggerSchema(BaseModel):
    type: str
    config: dict[str, Any]

    @model_validator(mode="after")
    def validate_trigger(self) -> "TriggerSchema":
        t = self.type
        cfg = self.config

        if t not in VALID_TRIGGER_TYPES:
            raise ValueError(
                f"trigger.type must be one of {sorted(VALID_TRIGGER_TYPES)}"
            )

        if t == "health_score_threshold":
            HealthScoreConfig(**cfg)
        elif t == "sentiment_pattern":
            SentimentPatternConfig(**cfg)
        elif t == "churn_risk_level_change":
            ChurnRiskConfig(**cfg)
        elif t == "feedback_category_match":
            FeedbackCategoryConfig(**cfg)
        elif t == "churn_probability_threshold":
            ChurnProbabilityConfig(**cfg)
        elif t == "usage_trend":
            UsageTrendConfig(**cfg)

        return self


class ActionSchema(BaseModel):
    type: str
    config: dict[str, Any]

    @model_validator(mode="after")
    def validate_action(self) -> "ActionSchema":
        t = self.type
        cfg = self.config

        if t not in VALID_ACTION_TYPES:
            raise ValueError(
                f"action.type must be one of {sorted(VALID_ACTION_TYPES)}"
            )

        if t == "auto_assign":
            AutoAssignConfig(**cfg)
        elif t == "change_status":
            ChangeStatusConfig(**cfg)
        elif t == "send_notification":
            SendNotificationConfig(**cfg)
        elif t == "draft_response":
            DraftResponseConfig(**cfg)
        elif t == "run_playbook":
            RunPlaybookConfig(**cfg)

        return self


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class RuleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    trigger: TriggerSchema
    actions: List[ActionSchema] = Field(..., min_length=1)
    cooldown_hours: int = Field(default=24, ge=1, le=168)
    mode: str = Field(default="active")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        if v not in RULE_MODES:
            raise ValueError(f"mode must be one of {sorted(RULE_MODES)}")
        return v


class RuleUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    trigger: Optional[TriggerSchema] = None
    actions: Optional[List[ActionSchema]] = None
    cooldown_hours: Optional[int] = Field(None, ge=1, le=168)
    mode: Optional[str] = None

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in RULE_MODES:
            raise ValueError(f"mode must be one of {sorted(RULE_MODES)}")
        return v


class RuleResponse(BaseModel):
    id: int
    organization_id: int
    name: str
    description: Optional[str]
    is_active: bool
    mode: str
    trigger: dict[str, Any]
    actions: list[dict[str, Any]]
    cooldown_hours: int
    execution_count: int
    last_executed_at: Optional[datetime]
    is_template: bool
    template_id: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RuleListResponse(BaseModel):
    rules: List[RuleResponse]
    total: int
    limit: Optional[int]


class ExecutionResponse(BaseModel):
    id: int
    rule_id: int
    organization_id: int
    feedback_id: Optional[int]
    customer_email: Optional[str]
    trigger_snapshot: Optional[dict]
    actions_executed: Optional[list]
    status: str
    executed_at: datetime

    model_config = {"from_attributes": True}


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    trigger: dict[str, Any]
    actions: list[dict[str, Any]]
    cooldown_hours: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rule_to_response(rule: AutomationRule) -> RuleResponse:
    return RuleResponse(
        id=rule.id,
        organization_id=rule.organization_id,
        name=rule.name,
        description=rule.description,
        is_active=rule.is_active,
        mode=rule.mode,
        trigger={"type": rule.trigger_type, "config": rule.trigger_config},
        actions=rule.actions,
        cooldown_hours=rule.cooldown_hours,
        execution_count=rule.execution_count,
        last_executed_at=rule.last_executed_at,
        is_template=rule.is_template,
        template_id=rule.template_id,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


def _check_automation_access(org: Organization) -> None:
    """Raise 402/403 if the org's plan doesn't include workflow_automation."""
    plan = org.plan or "free"
    if not has_feature(plan, "workflow_automation"):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "feature_not_available",
                "feature": "workflow_automation",
                "current_plan": plan,
                "required_plan": "pro",
                "message": "Workflow automation requires the Pro plan or higher.",
                "upgrade_url": "/settings/billing",
            },
        )


def _check_rule_limit(org: Organization, db: Session) -> None:
    """Raise 402 if the org has reached its automation rule limit."""
    plan = org.plan or "free"
    limit = get_automation_rule_limit(plan)

    if limit == 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "feature_not_available",
                "feature": "workflow_automation",
                "current_plan": plan,
                "required_plan": "pro",
                "message": "Workflow automation requires the Pro plan or higher.",
                "upgrade_url": "/settings/billing",
            },
        )

    if limit is not None:
        current_count = (
            db.query(AutomationRule)
            .filter(AutomationRule.organization_id == org.id)
            .count()
        )
        if current_count >= limit:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "automation_rule_limit_exceeded",
                    "limit": limit,
                    "used": current_count,
                    "message": (
                        f"You've reached your limit of {limit} automation rules. "
                        "Upgrade to add more."
                    ),
                    "upgrade_url": "/settings/billing",
                },
            )


def _validate_run_playbook_actions(
    actions: List[ActionSchema], org_id: int, db: Session
) -> None:
    """Raise 422 if any `run_playbook` action references a playbook that is
    missing, inactive, or owned by a different organization.

    A playbook is a valid reference when it is `is_active == True` AND
    (`organization_id == org_id` OR `organization_id IS NULL` — system
    template). Called from both `create_rule` and `update_rule`, AFTER
    request-schema validation and BEFORE persisting.
    """
    for action in actions:
        if action.type != "run_playbook":
            continue
        playbook_id = action.config.get("playbook_id")
        playbook = (
            db.query(ChurnPlaybook)
            .filter(
                ChurnPlaybook.id == playbook_id,
                ChurnPlaybook.is_active == True,  # noqa: E712
                (ChurnPlaybook.organization_id == org_id)
                | (ChurnPlaybook.organization_id.is_(None)),
            )
            .first()
        )
        if not playbook:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "run_playbook action references an unknown or inactive "
                    f"playbook: {playbook_id}"
                ),
            )


def _get_rule_or_404(rule_id: int, org_id: int, db: Session) -> AutomationRule:
    rule = (
        db.query(AutomationRule)
        .filter(
            AutomationRule.id == rule_id,
            AutomationRule.organization_id == org_id,
        )
        .first()
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    return rule


# ---------------------------------------------------------------------------
# Routes — NOTE: static sub-paths (/templates) MUST come before /{id}
# ---------------------------------------------------------------------------

@router.get("/templates", response_model=List[TemplateResponse])
def list_templates(
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
):
    """List all pre-built automation templates."""
    return [
        TemplateResponse(
            id=t["id"],
            name=t["name"],
            description=t["description"],
            trigger=t["trigger"],
            actions=t["actions"],
            cooldown_hours=t["cooldown_hours"],
        )
        for t in AUTOMATION_TEMPLATES
    ]


@router.post(
    "/templates/{template_id}/enable",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_owner)],
)
def enable_template(
    template_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Create a new automation rule from a pre-built template."""
    _check_automation_access(current_org)
    _check_rule_limit(current_org, db)

    tmpl = TEMPLATES_BY_ID.get(template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")

    now = datetime.utcnow()
    # `mode` is optional per-template (defaults to "active" — today's
    # behavior, unchanged for the 5 pre-existing templates). Setting `mode`
    # directly (rather than `is_active=True`) lets AutomationRule's own
    # `@validates("mode")` derive `is_active` for us, since is_active is a
    # write-through alias of mode (`models/automation_rule.py`). Passing
    # `is_active=True` here as before would *promote* mode to "active"
    # unconditionally and silently discard an explicit "shadow" template
    # default (M7's shadow-by-default guarantee).
    rule = AutomationRule(
        organization_id=current_org.id,
        name=tmpl["name"],
        description=tmpl["description"],
        mode=tmpl.get("mode", "active"),
        trigger_type=tmpl["trigger"]["type"],
        trigger_config=tmpl["trigger"]["config"],
        actions=tmpl["actions"],
        cooldown_hours=tmpl["cooldown_hours"],
        is_template=True,
        template_id=template_id,
        execution_count=0,
        created_at=now,
        updated_at=now,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _rule_to_response(rule)


@router.get("", response_model=RuleListResponse)
def list_rules(
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """List all automation rules for the current organization."""
    rules = (
        db.query(AutomationRule)
        .filter(AutomationRule.organization_id == current_org.id)
        .order_by(AutomationRule.created_at.desc())
        .all()
    )
    plan = current_org.plan or "free"
    limit = get_automation_rule_limit(plan)
    return RuleListResponse(
        rules=[_rule_to_response(r) for r in rules],
        total=len(rules),
        limit=limit,
    )


@router.post(
    "",
    response_model=RuleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin_or_owner)],
)
def create_rule(
    payload: RuleCreateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Create a new automation rule. Requires Admin or Owner role."""
    _check_automation_access(current_org)
    _check_rule_limit(current_org, db)
    _validate_run_playbook_actions(payload.actions, current_org.id, db)

    now = datetime.utcnow()
    rule = AutomationRule(
        organization_id=current_org.id,
        name=payload.name,
        description=payload.description,
        mode=payload.mode,
        trigger_type=payload.trigger.type,
        trigger_config=payload.trigger.config,
        actions=[a.model_dump() for a in payload.actions],
        cooldown_hours=payload.cooldown_hours,
        is_template=False,
        template_id=None,
        execution_count=0,
        created_at=now,
        updated_at=now,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)

    if rule.mode == "active":
        # Rule created directly in active mode with a churn_probability_threshold
        # trigger — seed cooldowns so it doesn't stampede-fire for every
        # customer already above threshold (seed_churn_cooldowns no-ops for
        # any other trigger_type). Never let seeding failure fail the request.
        try:
            seeded = seed_churn_cooldowns(db, rule)
            if seeded:
                logger.info(
                    "create_rule: seeded %d cooldowns for rule %s on creation (active)",
                    seeded, rule.id,
                )
        except Exception as exc:
            logger.warning(
                "create_rule: cooldown seeding failed for rule %s: %s", rule.id, exc
            )

    return _rule_to_response(rule)


@router.get("/{rule_id}", response_model=RuleResponse)
def get_rule(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get a specific automation rule by ID."""
    rule = _get_rule_or_404(rule_id, current_org.id, db)
    return _rule_to_response(rule)


@router.put(
    "/{rule_id}",
    response_model=RuleResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def update_rule(
    rule_id: int,
    payload: RuleUpdateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Update an existing automation rule. Requires Admin or Owner role."""
    rule = _get_rule_or_404(rule_id, current_org.id, db)
    old_mode = rule.mode  # captured BEFORE the update is applied

    if payload.actions is not None:
        _validate_run_playbook_actions(payload.actions, current_org.id, db)

    if payload.name is not None:
        rule.name = payload.name
    if payload.description is not None:
        rule.description = payload.description
    if payload.trigger is not None:
        rule.trigger_type = payload.trigger.type
        rule.trigger_config = payload.trigger.config
    if payload.actions is not None:
        rule.actions = [a.model_dump() for a in payload.actions]
    if payload.cooldown_hours is not None:
        rule.cooldown_hours = payload.cooldown_hours
    if payload.mode is not None:
        rule.mode = payload.mode

    rule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule)

    if rule.mode == "active" and old_mode != "active":
        # Transition INTO active — seed against the FINAL (post-update)
        # threshold/config now that the rule is persisted. Seeding failure
        # must never fail the request.
        try:
            seeded = seed_churn_cooldowns(db, rule)
            if seeded:
                logger.info(
                    "update_rule: seeded %d cooldowns for rule %s activation (%s -> active)",
                    seeded, rule.id, old_mode,
                )
        except Exception as exc:
            logger.warning(
                "update_rule: cooldown seeding failed for rule %s: %s", rule.id, exc
            )

    return _rule_to_response(rule)


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin_or_owner)],
)
def delete_rule(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Delete an automation rule. Requires Admin or Owner role."""
    rule = _get_rule_or_404(rule_id, current_org.id, db)
    db.delete(rule)
    db.commit()


@router.patch(
    "/{rule_id}/toggle",
    response_model=RuleResponse,
    dependencies=[Depends(require_admin_or_owner)],
)
def toggle_rule(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Toggle a rule between active and paused. Requires Admin or Owner role."""
    rule = _get_rule_or_404(rule_id, current_org.id, db)
    old_mode = rule.mode  # captured BEFORE the flip
    rule.is_active = not rule.is_active
    rule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule)

    if rule.mode == "active" and old_mode != "active":
        # Transition INTO active via toggle — mirror update_rule's guard so
        # the activation stampede doesn't reopen through this endpoint.
        try:
            seeded = seed_churn_cooldowns(db, rule)
            if seeded:
                logger.info(
                    "toggle_rule: seeded %d cooldowns for rule %s activation (%s -> active)",
                    seeded, rule.id, old_mode,
                )
        except Exception as exc:
            logger.warning(
                "toggle_rule: cooldown seeding failed for rule %s: %s", rule.id, exc
            )

    return _rule_to_response(rule)


@router.get("/{rule_id}/executions", response_model=List[ExecutionResponse])
def get_executions(
    rule_id: int,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: Session = Depends(get_db),
):
    """Get the last 50 execution log entries for a rule."""
    # Verify the rule belongs to this org
    _get_rule_or_404(rule_id, current_org.id, db)

    executions = (
        db.query(AutomationExecution)
        .filter(AutomationExecution.rule_id == rule_id)
        .order_by(AutomationExecution.executed_at.desc())
        .limit(50)
        .all()
    )
    return executions
