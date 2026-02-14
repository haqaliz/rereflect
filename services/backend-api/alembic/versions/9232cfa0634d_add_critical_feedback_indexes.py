"""add_critical_feedback_indexes

Revision ID: 9232cfa0634d
Revises: 093c65b07d95
Create Date: 2026-02-15 01:36:27.356609

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9232cfa0634d'
down_revision: Union[str, None] = '093c65b07d95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_feedback_org_sentiment',
        'feedback_items',
        ['organization_id', 'sentiment_label'],
        unique=False,
    )
    op.create_index(
        'ix_feedback_org_urgent',
        'feedback_items',
        ['organization_id', 'is_urgent'],
        unique=False,
    )
    op.create_index(
        'ix_feedback_org_pain_cat',
        'feedback_items',
        ['organization_id', 'pain_point_category'],
        unique=False,
    )
    op.create_index(
        'ix_feedback_org_feature_cat',
        'feedback_items',
        ['organization_id', 'feature_request_category'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_feedback_org_feature_cat', table_name='feedback_items')
    op.drop_index('ix_feedback_org_pain_cat', table_name='feedback_items')
    op.drop_index('ix_feedback_org_urgent', table_name='feedback_items')
    op.drop_index('ix_feedback_org_sentiment', table_name='feedback_items')
