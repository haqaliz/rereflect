"""add_embedding_model_to_mappings

Revision ID: hbsh5o3gbwv4
Revises: 0a3382154c27
Create Date: 2026-07-24 00:00:00.000000

Adds embedding_model (String(100), nullable) to query_template_mappings and
reworks the provider/dimension covering index to also include the model.

Backfill rule (guarded UPDATE, mirrors y4z5a6b7c8d9's try/except-around-bind
shape so a fresh test DB without the table doesn't crash the migration):

  embedding_provider = 'openai' AND embedding_dimension = 1536
      → embedding_model = 'text-embedding-3-small'
  all other rows (including NULL provider/dim)
      → embedding_model stays NULL (stale)

Later tasks (3 & 4) key the template-mapping skip-filter on
(embedding_provider, embedding_dimension, embedding_model) so a model change
can never silently compare vectors produced by two different models. NULL
embedding_model = stale (skipped by the matcher), same convention as the
provider/dimension columns added in y4z5a6b7c8d9.

Downgrade: drops ix_mappings_provider_dim_model, recreates the old
ix_mappings_provider_dim (embedding_provider, embedding_dimension), and drops
the embedding_model column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = 'hbsh5o3gbwv4'
down_revision: Union[str, None] = '0a3382154c27'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add the new nullable column.
    op.add_column(
        'query_template_mappings',
        sa.Column('embedding_model', sa.String(100), nullable=True),
    )

    # 2. Backfill: rows already tagged as OpenAI's 1536-dim embedding get the
    #    model name that produced them. Everything else (including rows with
    #    NULL provider/dimension) is left NULL — stale, skipped by the matcher.
    #
    #    Wrapped in try/except so a fresh test DB without the table doesn't
    #    crash the migration (mirrors y4z5a6b7c8d9's guarded bind execution).
    conn = op.get_bind()

    try:
        conn.execute(
            text(
                "UPDATE query_template_mappings "
                "SET embedding_model = 'text-embedding-3-small' "
                "WHERE embedding_provider = 'openai' AND embedding_dimension = 1536"
            )
        )
    except Exception:
        # Table may not exist (e.g. running on a test DB that was freshly created).
        pass

    # 3. Rework the covering index to include the model.
    op.drop_index('ix_mappings_provider_dim', table_name='query_template_mappings')
    op.create_index(
        'ix_mappings_provider_dim_model',
        'query_template_mappings',
        ['embedding_provider', 'embedding_dimension', 'embedding_model'],
    )


def downgrade() -> None:
    op.drop_index('ix_mappings_provider_dim_model', table_name='query_template_mappings')
    op.create_index(
        'ix_mappings_provider_dim',
        'query_template_mappings',
        ['embedding_provider', 'embedding_dimension'],
    )
    op.drop_column('query_template_mappings', 'embedding_model')
