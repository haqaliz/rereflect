"""add feedback source lookup index

Fix wave (post-review, zendesk-status-sync): both the worker's poll query
(services/worker-service/src/tasks/zendesk_status_sync.py) and the
webhook's `reconcile_ticket` (services/backend-api/src/services/
zendesk_status_reconcile.py) look up FeedbackItem rows by
(organization_id, source, source_external_id) — this triple was previously
unindexed on the hot feedback_items table. Adds a composite index to keep
that lookup fast as feedback volume grows. Mirrors the Jira status-sync
precedent's equivalent lookup shape.

Revision ID: 3e26b38cbd15
Revises: d5e6f7a8b9c0
Create Date: 2026-07-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e26b38cbd15'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_feedback_items_org_source_external',
        'feedback_items',
        ['organization_id', 'source', 'source_external_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_feedback_items_org_source_external', table_name='feedback_items')
