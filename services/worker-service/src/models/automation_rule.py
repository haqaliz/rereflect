"""
AutomationRule — lightweight SQLAlchemy mirror for worker-service.

The full model + engine live in backend-api
(`services/backend-api/src/models/automation_rule.py`). This mirror is used
ONLY by `src.services.automation_churn_trigger` to evaluate the
`churn_probability_threshold` trigger from the worker's probability-update
seam (`src.services.probability_updater.update()`). It intentionally does
NOT activate the other trigger types (`health_score_threshold`,
`sentiment_pattern`, `churn_risk_level_change`, `feedback_category_match`) —
those remain backend-only / dead in the worker (see
`src.tasks.analysis` for the pre-existing dead `AutomationEngine` import).

No ForeignKeys are declared here (same pattern as all other worker mirrors,
e.g. `src.models.automation_execution.AutomationExecution`) — the worker
shares the same physical DB as backend-api but does not own migrations for
this table.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, Integer, JSON, String, Text
from sqlalchemy.orm import validates

from src.models import Base


# Execution-state modes: "off" (disabled), "shadow" (evaluate + log, no
# actions run), "active" (evaluate + run actions). Mirrors backend-api's
# RULE_MODES exactly (Task-1).
RULE_MODES = ("off", "shadow", "active")


class AutomationRule(Base):
    """An IF/THEN automation rule for an organization (worker-service mirror)."""

    __tablename__ = "automation_rules"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, nullable=False)

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)

    # `mode` is the single source of truth for evaluation; `is_active` is a
    # derived, write-through alias kept for backward compatibility with
    # existing callers. See the `@validates` methods below for the
    # reconciliation logic that keeps `is_active == (mode != "off")`.
    mode = Column(
        String(10),
        nullable=False,
        default="active",
        server_default="active",
    )

    # Trigger
    trigger_type = Column(String(50), nullable=False)  # health_score_threshold | sentiment_pattern | churn_risk_level_change | feedback_category_match | churn_probability_threshold
    trigger_config = Column(JSON, nullable=False, default=dict)

    # Actions — array of {type, config}
    actions = Column(JSON, nullable=False, default=list)

    cooldown_hours = Column(Integer, default=24, nullable=False)

    # Execution tracking
    execution_count = Column(Integer, default=0, nullable=False)
    last_executed_at = Column(DateTime, nullable=True)

    # Template metadata
    is_template = Column(Boolean, default=False, nullable=False)
    template_id = Column(String(50), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        Index("ix_automation_rules_org_active", "organization_id", "is_active"),
        Index("ix_automation_rules_org_trigger", "organization_id", "trigger_type"),
    )

    @validates("mode")
    def _validate_mode(self, key: str, value: str) -> str:
        """Reject unknown modes and keep `is_active` in sync.

        `mode` is the source of truth; `is_active` is derived as
        `mode != "off"`. A reentrancy guard (`_syncing_mode_is_active`)
        prevents infinite recursion with `_validate_is_active` below, since
        each validator writes to the other's attribute exactly once per
        external assignment. (Mirrors backend-api Task-1 logic verbatim.)
        """
        if value not in RULE_MODES:
            raise ValueError(
                f"Invalid AutomationRule mode: {value!r}. Must be one of {RULE_MODES}."
            )
        if not getattr(self, "_syncing_mode_is_active", False):
            self._syncing_mode_is_active = True
            try:
                self.is_active = value != "off"
            finally:
                self._syncing_mode_is_active = False
        return value

    @validates("is_active")
    def _validate_is_active(self, key: str, value: bool) -> bool:
        """Keep `mode` in sync with `is_active` (see `_validate_mode`).

        Setting `is_active=False` forces `mode="off"`. Setting
        `is_active=True` promotes `mode` to `"active"` only when the current
        mode is `"off"` (or unset) — an explicit `"shadow"` mode is never
        clobbered by a plain `is_active=True` assignment.
        """
        if not getattr(self, "_syncing_mode_is_active", False):
            self._syncing_mode_is_active = True
            try:
                if value:
                    if getattr(self, "mode", None) in (None, "off"):
                        self.mode = "active"
                else:
                    self.mode = "off"
            finally:
                self._syncing_mode_is_active = False
        return value

    def __repr__(self) -> str:
        return f"<AutomationRule(id={self.id}, name='{self.name}', org={self.organization_id})>"
