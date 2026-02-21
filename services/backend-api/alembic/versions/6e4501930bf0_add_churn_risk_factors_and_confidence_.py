"""add_churn_risk_factors_and_confidence_score

Revision ID: 6e4501930bf0
Revises: g0h1i2j3k4l5
Create Date: 2026-02-21 02:07:21.189405

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e4501930bf0'
down_revision: Union[str, None] = 'g0h1i2j3k4l5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('customer_health_scores', sa.Column('confidence_score', sa.Integer(), nullable=True))
    op.add_column('feedback_items', sa.Column('churn_risk_factors', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('feedback_items', 'churn_risk_factors')
    op.drop_column('customer_health_scores', 'confidence_score')
