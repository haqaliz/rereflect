"""add_model_embeddings_to_org_ai_config

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-01 00:00:00.000000

Adds the per-org embedding-model override (template-matching-local S1):
  - org_ai_config.model_embeddings  VARCHAR(100) NULL

Null = derive the default model from default_provider (see
src/services/embeddings/resolver.py + EmbeddingProviderFactory). No backfill
needed; existing orgs simply fall back to the provider default.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'org_ai_config',
        sa.Column('model_embeddings', sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('org_ai_config', 'model_embeddings')
