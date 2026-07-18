"""add_automation_rule_mode

Revision ID: u4v5w6x7y8z9
Revises: t3u4v5w6x7y8
Create Date: 2026-07-18 00:00:00.000000

Adds `automation_rules.mode` (off | shadow | active) — the execution-state
field used to auto-run churn playbooks via the AutomationEngine. `mode`
becomes the single source of truth for evaluation going forward; `is_active`
is kept as a derived, write-through alias for backward compatibility.

Backfills `mode` from the existing `is_active` column so no rule silently
changes behavior after migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'u4v5w6x7y8z9'
down_revision: Union[str, None] = 't3u4v5w6x7y8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "automation_rules",
        sa.Column("mode", sa.String(length=10), nullable=False, server_default="active"),
    )
    op.execute(
        "UPDATE automation_rules SET mode = CASE WHEN is_active THEN 'active' ELSE 'off' END"
    )


def downgrade() -> None:
    op.drop_column("automation_rules", "mode")
