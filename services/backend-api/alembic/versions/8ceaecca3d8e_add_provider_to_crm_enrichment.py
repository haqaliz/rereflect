"""add provider to crm_enrichment

Revision ID: 8ceaecca3d8e
Revises: d4e5f6a7b8c9
Create Date: 2026-07-01 16:48:07.548159

Adds crm_enrichment.provider (crm-provider-generalization, aspect 1 of 4 of
salesforce-crm-enrichment). Foundation for a second CRM (Salesforce) sharing
the same crm_enrichment table alongside HubSpot.

server_default='hubspot' backfills every existing row so pre-generalization
HubSpot-enriched orgs read back identically (zero score/API-output movement
— see tests/test_crm_provider_generalization.py).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8ceaecca3d8e'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'crm_enrichment',
        sa.Column('provider', sa.String(length=50), nullable=False, server_default='hubspot'),
    )


def downgrade() -> None:
    op.drop_column('crm_enrichment', 'provider')
