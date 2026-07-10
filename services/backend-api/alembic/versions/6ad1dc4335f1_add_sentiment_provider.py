"""add_sentiment_provider

Revision ID: 6ad1dc4335f1
Revises: a6b703d7a303
Create Date: 2026-07-10 13:51:52.679933

Adds the per-org sentiment engine opt-in (local-analyzer-sentiment-model,
per-org-resolution aspect):
  - org_ai_config.sentiment_provider  VARCHAR(20)  NULL  DEFAULT 'vader'

Values: 'vader' | 'transformer'. NULL and any value outside this set are
treated as 'vader' by resolve_sentiment_provider (defense in depth — the
server_default covers new/backfilled rows; the resolver covers rows written
by an older or newer, incompatible app version). No existing analysis
output changes because the resolver only returns non-None for an explicit,
valid 'transformer' value.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6ad1dc4335f1'
down_revision: Union[str, None] = 'a6b703d7a303'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'org_ai_config',
        sa.Column('sentiment_provider', sa.String(20), nullable=True, server_default='vader'),
    )


def downgrade() -> None:
    op.drop_column('org_ai_config', 'sentiment_provider')
