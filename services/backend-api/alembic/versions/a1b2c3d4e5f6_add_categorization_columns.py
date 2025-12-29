"""add_categorization_columns

Revision ID: a1b2c3d4e5f6
Revises: 9f2a1dfcdb55
Create Date: 2025-12-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9f2a1dfcdb55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Pain point categorization columns
    op.add_column('feedback_items', sa.Column('pain_point_category', sa.String(), nullable=True))
    op.add_column('feedback_items', sa.Column('pain_point_severity', sa.String(), nullable=True))
    op.add_column('feedback_items', sa.Column('pain_point_text', sa.Text(), nullable=True))

    # Feature request categorization columns
    op.add_column('feedback_items', sa.Column('feature_request_category', sa.String(), nullable=True))
    op.add_column('feedback_items', sa.Column('feature_request_priority', sa.String(), nullable=True))
    op.add_column('feedback_items', sa.Column('feature_request_text', sa.Text(), nullable=True))

    # Urgent categorization columns
    op.add_column('feedback_items', sa.Column('urgent_category', sa.String(), nullable=True))
    op.add_column('feedback_items', sa.Column('urgent_response_time', sa.String(), nullable=True))

    # Categorization confidence score
    op.add_column('feedback_items', sa.Column('categorization_confidence', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('feedback_items', 'categorization_confidence')
    op.drop_column('feedback_items', 'urgent_response_time')
    op.drop_column('feedback_items', 'urgent_category')
    op.drop_column('feedback_items', 'feature_request_text')
    op.drop_column('feedback_items', 'feature_request_priority')
    op.drop_column('feedback_items', 'feature_request_category')
    op.drop_column('feedback_items', 'pain_point_text')
    op.drop_column('feedback_items', 'pain_point_severity')
    op.drop_column('feedback_items', 'pain_point_category')
