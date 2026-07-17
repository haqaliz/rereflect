"""add user oidc sub

Adds `users.oidc_sub` (String(255), unique, nullable, indexed) for the
oidc-login-flow aspect of oidc-sso (PRD M7). Populated on JIT-provision/link
during OIDC callback handling; existing users are unaffected (nullable,
additive only).

HEAD VERIFICATION: `alembic heads` was re-run LIVE in this worktree
immediately before authoring this revision and returned exactly one line:
`c9d0e1f2a3b4 (head)`. This revision chains directly off that sole
verified head — no merge revision, no static parse.

Revision ID: n8o9p0q1r2s3
Revises: c9d0e1f2a3b4
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "n8o9p0q1r2s3"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("oidc_sub", sa.String(length=255), nullable=True))
    op.create_index("ix_users_oidc_sub", "users", ["oidc_sub"], unique=True)


def downgrade():
    op.drop_index("ix_users_oidc_sub", table_name="users")
    op.drop_column("users", "oidc_sub")
