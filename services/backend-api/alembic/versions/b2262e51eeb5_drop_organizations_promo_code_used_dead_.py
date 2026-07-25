"""drop organizations.promo_code_used (dead stripe promo surface)

Revision ID: b2262e51eeb5
Revises: 8bbf7dfee1e9
Create Date: 2026-07-26 00:44:26.425588

Completes the OSS-pivot Stripe teardown (see w2x3y4z5a6b7). The promo-code
feature was Stripe-backed: `admin_promo.py` proxied Stripe Promotion Codes
and was never mounted in `main.py` after the pivot, so this column has had
no writer since. Dropped along with the route, the admin UI page, and the
sidebar entry that pointed at it.

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b2262e51eeb5"
down_revision = "8bbf7dfee1e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("organizations", "promo_code_used")


def downgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("promo_code_used", sa.String(length=50), nullable=True),
    )
