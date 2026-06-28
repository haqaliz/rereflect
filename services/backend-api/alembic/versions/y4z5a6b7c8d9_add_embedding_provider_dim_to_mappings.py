"""add_embedding_provider_dim_to_mappings

Revision ID: y4z5a6b7c8d9
Revises: x3y4z5a6b7c8
Create Date: 2026-06-28 00:00:00.000000

Adds embedding_provider (String(50), nullable) and embedding_dimension (Integer,
nullable) to query_template_mappings with a length-based backfill:

  len(question_embedding) == 1536  →  provider='openai', dimension=1536
  null / any other length           →  provider=NULL, dimension=NULL  (stale)

Stale rows are silently excluded from cosine comparisons by the template matcher
(provider/dim mismatch filter), so this backfill is safe for all existing data.

An index on (embedding_provider, embedding_dimension) is created to speed up the
skip-filter query once the matcher uses a DB-side filter in the future.

Downgrade: drops the index and the two columns (data loss for new vectors only).
"""
from typing import Sequence, Union

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = 'y4z5a6b7c8d9'
down_revision: Union[str, None] = 'x3y4z5a6b7c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add the two new nullable columns
    op.add_column(
        'query_template_mappings',
        sa.Column('embedding_provider', sa.String(50), nullable=True),
    )
    op.add_column(
        'query_template_mappings',
        sa.Column('embedding_dimension', sa.Integer(), nullable=True),
    )

    # 2. Length-based backfill.
    #
    #    We cannot rely on a portable SQL json_array_length() across SQLite and
    #    PostgreSQL in a single statement, so we use a Python loop here.  This is
    #    safe: query_template_mappings is expected to be small at migration time
    #    (15 system templates × 4 patterns = ~60 rows), so in-process iteration
    #    is negligible.
    #
    #    Rule: if the stored vector has exactly 1536 floats it must have been
    #    written by the old OpenAI-only code path → tag as ('openai', 1536).
    #    Anything else (null, empty, other dim) is left as stale (NULL/NULL).
    conn = op.get_bind()

    try:
        rows = conn.execute(
            text("SELECT id, question_embedding FROM query_template_mappings")
        ).fetchall()
    except Exception:
        # Table may not exist (e.g. running on a test DB that was freshly created).
        rows = []

    for row in rows:
        row_id = row[0]
        raw = row[1]

        if raw is None:
            continue  # Already stale, no update needed

        try:
            if isinstance(raw, str):
                vec = json.loads(raw)
            elif isinstance(raw, list):
                vec = raw
            else:
                continue
        except (json.JSONDecodeError, TypeError):
            continue

        if isinstance(vec, list) and len(vec) == 1536:
            conn.execute(
                text(
                    "UPDATE query_template_mappings "
                    "SET embedding_provider = 'openai', embedding_dimension = 1536 "
                    "WHERE id = :id"
                ),
                {"id": row_id},
            )
        # else: leave NULL (stale)

    # 3. Optional index on (embedding_provider, embedding_dimension) for future
    #    DB-side provider/dim filter queries.
    op.create_index(
        'ix_mappings_provider_dim',
        'query_template_mappings',
        ['embedding_provider', 'embedding_dimension'],
    )


def downgrade() -> None:
    op.drop_index('ix_mappings_provider_dim', table_name='query_template_mappings')
    op.drop_column('query_template_mappings', 'embedding_dimension')
    op.drop_column('query_template_mappings', 'embedding_provider')
