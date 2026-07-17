"""add saml config table

Creates saml_configs (one row/org, plaintext idp_x509_cert — a PUBLIC signing
certificate, not a secret, so it is NOT Fernet-encrypted, unlike
oidc_configs.client_secret) for the config-model-and-crud aspect of
saml-sso (PRD M1/M6). Stores idp_entity_id/idp_sso_url/idp_x509_cert/
email_attribute, the enabled switch, allowed_email_domains (JSON list,
deny-all when empty/absent), and button_label.

No DB-level partial unique index on `enabled`: SQLite (test DB) doesn't
enforce Postgres partial unique indexes, so the one-enabled-per-deployment
guard (D5 same-provider, plus the cross-provider M6 guard) is enforced in
the route layer instead, which works on both dialects. Mirrors
oidc_configs' c9d0e1f2a3b4 header note verbatim — see
docs/planning/saml-sso/config-model-and-crud/spec.md.

HEAD VERIFICATION: `alembic heads` was re-run LIVE in this worktree
immediately before authoring this revision and returned exactly one line:
`n8o9p0q1r2s3 (head)`. This revision chains directly off that sole
verified head — no merge revision, no static parse.

Revision ID: o9p0q1r2s3t4
Revises: n8o9p0q1r2s3
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "o9p0q1r2s3t4"
down_revision = "n8o9p0q1r2s3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "saml_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("idp_entity_id", sa.String(length=255), nullable=False),
        sa.Column("idp_sso_url", sa.String(length=512), nullable=False),
        sa.Column("idp_x509_cert", sa.Text(), nullable=False),
        sa.Column("email_attribute", sa.String(length=255), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allowed_email_domains", sa.JSON(), nullable=True),
        sa.Column("button_label", sa.String(length=255), nullable=False, server_default="Sign in with SSO"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_saml_configs_org_id"),
    )
    op.create_index(
        "ix_saml_configs_org_id", "saml_configs", ["organization_id"]
    )
    op.create_index(
        op.f("ix_saml_configs_id"), "saml_configs", ["id"]
    )


def downgrade():
    op.drop_index(op.f("ix_saml_configs_id"), table_name="saml_configs")
    op.drop_index("ix_saml_configs_org_id", table_name="saml_configs")
    op.drop_table("saml_configs")
