"""add structured llm_analysis_data JSON, llm_raw_response JSON, customer_analysis_actions table

Revision ID: g0h1i2j3k4l5
Revises: f9g0h1i2j3k4
Create Date: 2026-02-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON


# revision identifiers, used by Alembic.
revision: str = 'g0h1i2j3k4l5'
down_revision: Union[str, None] = 'f9g0h1i2j3k4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _parse_pipe_separated(raw: str) -> dict:
    """Parse legacy pipe-separated llm_analysis text into structured JSON."""
    parts = raw.split(' | ')
    analysis = parts[0] or ''
    actions = []
    urgency = ''

    for part in parts[1:]:
        if part.startswith('Actions: '):
            actions = [a.strip() for a in part.replace('Actions: ', '').split(';') if a.strip()]
        elif part.startswith('Urgency: '):
            urgency = part.replace('Urgency: ', '').strip()

    return {
        'analysis': analysis,
        'recommended_actions': actions,
        'risk_drivers': [],
        'estimated_urgency': urgency or 'this_month',
        'analysis_type': 'churn_risk',
    }


def upgrade() -> None:
    # 1. Add llm_analysis_data JSON column
    op.add_column(
        'customer_health_scores',
        sa.Column('llm_analysis_data', JSON, nullable=True),
    )

    # 2. Add llm_raw_response JSON column
    op.add_column(
        'customer_health_scores',
        sa.Column('llm_raw_response', JSON, nullable=True),
    )

    # 3. Create customer_analysis_actions table
    op.create_table(
        'customer_analysis_actions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'customer_health_id',
            sa.Integer(),
            sa.ForeignKey('customer_health_scores.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'organization_id',
            sa.Integer(),
            sa.ForeignKey('organizations.id'),
            nullable=False,
        ),
        sa.Column('action_text', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column(
            'completed_by',
            sa.Integer(),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # 4. Create indexes on customer_analysis_actions
    op.create_index(
        'ix_analysis_action_health_status',
        'customer_analysis_actions',
        ['customer_health_id', 'status'],
    )
    op.create_index(
        'ix_analysis_action_org',
        'customer_analysis_actions',
        ['organization_id'],
    )

    # 5. Data migration: parse existing pipe-separated llm_analysis into llm_analysis_data JSON
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, llm_analysis FROM customer_health_scores WHERE llm_analysis IS NOT NULL")
    ).fetchall()

    for row in rows:
        record_id = row[0]
        raw_text = row[1]
        try:
            structured = _parse_pipe_separated(raw_text)
            import json
            conn.execute(
                sa.text(
                    "UPDATE customer_health_scores SET llm_analysis_data = :data WHERE id = :id"
                ),
                {"data": json.dumps(structured), "id": record_id},
            )
        except Exception:
            pass  # Skip malformed records


def downgrade() -> None:
    op.drop_index('ix_analysis_action_org', table_name='customer_analysis_actions')
    op.drop_index('ix_analysis_action_health_status', table_name='customer_analysis_actions')
    op.drop_table('customer_analysis_actions')
    op.drop_column('customer_health_scores', 'llm_raw_response')
    op.drop_column('customer_health_scores', 'llm_analysis_data')
