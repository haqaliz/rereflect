"""add oidc config table

Creates oidc_configs (one row/org, Fernet-encrypted client_secret) for the
oidc-config aspect of oidc-sso (PRD M2). Stores issuer_url/client_id/
client_secret/secret_hint, the enabled switch, allowed_email_domains
(JSON list, deny-all when empty/absent), and button_label. Encryption
happens in the route layer, not here — see src/models/oidc_config.py.

No DB-level partial unique index on `enabled`: SQLite (test DB) doesn't
enforce Postgres partial unique indexes, so the one-enabled-per-deployment
guard (D5) is enforced in the route layer instead, which works on both
dialects. See docs/planning/oidc-sso/oidc-config/spec.md R1.

HEAD VERIFICATION: `alembic heads` was re-run LIVE in this worktree
immediately before authoring this revision and returned exactly one line:
`b8c9d0e1f2a3 (head)`. This revision chains directly off that sole
verified head — no merge revision, no static parse.

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "oidc_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("issuer_url", sa.String(length=255), nullable=False),
        sa.Column("client_id", sa.String(length=255), nullable=False),
        sa.Column("client_secret", sa.Text(), nullable=False),
        sa.Column("secret_hint", sa.String(length=8), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allowed_email_domains", sa.JSON(), nullable=True),
        sa.Column("button_label", sa.String(length=255), nullable=False, server_default="Sign in with SSO"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_oidc_configs_org_id"),
    )
    op.create_index(
        "ix_oidc_configs_org_id", "oidc_configs", ["organization_id"]
    )
    op.create_index(
        op.f("ix_oidc_configs_id"), "oidc_configs", ["id"]
    )


def downgrade():
    op.drop_index(op.f("ix_oidc_configs_id"), table_name="oidc_configs")
    op.drop_index("ix_oidc_configs_org_id", table_name="oidc_configs")
    op.drop_table("oidc_configs")
