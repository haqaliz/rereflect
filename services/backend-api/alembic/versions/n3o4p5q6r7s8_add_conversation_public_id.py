"""add_conversation_public_id

Revision ID: n3o4p5q6r7s8
Revises: i2j3k4l5m6n7
Create Date: 2026-02-25 02:30:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'n3o4p5q6r7s8'
down_revision: Union[str, None] = 'i2j3k4l5m6n7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Add public_id column as nullable
    op.add_column('conversations', sa.Column('public_id', sa.String(36), nullable=True))

    # Step 2: Backfill existing rows with unique UUIDs
    conn = op.get_bind()
    rows = conn.execute(sa.text('SELECT id FROM conversations WHERE public_id IS NULL')).fetchall()
    for row in rows:
        conn.execute(
            sa.text('UPDATE conversations SET public_id = :pid WHERE id = :id'),
            {'pid': str(uuid.uuid4()), 'id': row[0]},
        )

    # Step 3: Set column to non-nullable
    op.alter_column('conversations', 'public_id', nullable=False)

    # Step 4: Add unique index
    op.create_index('ix_conversations_public_id', 'conversations', ['public_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_conversations_public_id', table_name='conversations')
    op.drop_column('conversations', 'public_id')
