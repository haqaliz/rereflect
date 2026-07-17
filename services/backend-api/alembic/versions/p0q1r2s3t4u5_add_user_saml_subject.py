"""add user saml subject

Adds `users.saml_subject` (String(255), unique, nullable, indexed) for the
config-model-and-crud aspect of saml-sso (PRD M1). Populated on
JIT-provision/link during SAML ACS handling in a later aspect; existing
users are unaffected (nullable, additive only). Mirrors n8o9p0q1r2s3's
`users.oidc_sub` migration verbatim.

HEAD VERIFICATION: `alembic heads` was re-run LIVE in this worktree
immediately before authoring this revision and returned exactly one line:
`o9p0q1r2s3t4 (head)`. This revision chains directly off that sole
verified head — no merge revision, no static parse.

Revision ID: p0q1r2s3t4u5
Revises: o9p0q1r2s3t4
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "p0q1r2s3t4u5"
down_revision = "o9p0q1r2s3t4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("saml_subject", sa.String(length=255), nullable=True))
    op.create_index("ix_users_saml_subject", "users", ["saml_subject"], unique=True)


def downgrade():
    op.drop_index("ix_users_saml_subject", table_name="users")
    op.drop_column("users", "saml_subject")
