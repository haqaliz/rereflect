"""shadow_repaired_automation_triggers

Revision ID: 12a1003fbfe0
Revises: b2262e51eeb5
Create Date: 2026-07-29 02:01:49.626081

Phase 4 of the worker-trigger-mirror aspect (automations-delivery-integrity,
see docs/planning/automations-delivery-integrity/prd.md R3 and Risk 1).

`services/worker-service/src/tasks/analysis.py` has always swallowed the
`ImportError` for `feedback_category_match` and `sentiment_pattern` trigger
evaluation, so any pre-existing rule on those two trigger types has never
actually fired, no matter what `mode` it was left in. A concurrent change
repairs that dead import. Repairing it, on its own, would suddenly ACTIVATE
rules that users configured months ago and that have never once run — a real
behaviour change on a notification path, sprung on operators with no warning.

This migration moves that blast radius into `mode="shadow"`: every rule that
is currently `mode="active"` AND on one of the two repaired trigger types is
set to `mode="shadow"` so it evaluates (and logs an `AutomationExecution`
row) but runs no actions on first deploy. Operators review the shadow log
and opt each rule back into `active` deliberately.

Explicitly untouched:
- Rules on any other trigger type (`health_score_threshold`,
  `churn_risk_level_change`, `churn_probability_threshold`, `usage_trend`)
  have been firing correctly via the backend/worker all along and must not
  be disturbed.
- Rules already `mode="off"` or `mode="shadow"` are left exactly as they are.
- Template defaults are untouched — rules created *after* this migration
  still start `mode="active"` as normal; this is a one-time data repair, not
  a change to `src/config/automation_templates.py` or the model default.

downgrade() is a deliberate no-op (see below) rather than reversing the
UPDATE.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12a1003fbfe0'
down_revision: Union[str, None] = 'b2262e51eeb5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE automation_rules SET mode = 'shadow' "
        "WHERE mode = 'active' "
        "AND trigger_type IN ('feedback_category_match', 'sentiment_pattern')"
    )


def downgrade() -> None:
    # Deliberate no-op. Reversing this would flip every rule this migration
    # moved to 'shadow' back to 'active' indiscriminately — including rules
    # an operator has since reviewed and consciously left in shadow (or
    # tuned) after this deploy. Silently re-arming a notification-sending
    # automation on a downgrade is worse than an irreversible data
    # migration: there is no way to distinguish "still exactly as this
    # migration left it" from "operator deliberately kept it in shadow" at
    # downgrade time, so we refuse to guess and leave `mode` untouched.
    pass
