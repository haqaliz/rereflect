"""add local-llm base_url + health weights to org_ai_config; create api_keys

Feature batch (Local LLM / Custom AI / Public API):
- org_ai_config: base_url (local/custom OpenAI-compatible endpoint) +
  4 per-org customer-health-score component weights (default 35/25/25/15).
- api_keys: public-API access keys (sha256 hash + prefix; distinct from
  OrgApiKey which holds BYOK LLM keys).

Revision ID: x3y4z5a6b7c8
Revises: w2x3y4z5a6b7
Create Date: 2026-06-22 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "x3y4z5a6b7c8"
down_revision = "w2x3y4z5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── org_ai_config: local endpoint + per-org health weights ──────────────
    op.add_column("org_ai_config", sa.Column("base_url", sa.String(length=500), nullable=True))
    op.add_column(
        "org_ai_config",
        sa.Column("health_weight_churn", sa.Integer(), nullable=False, server_default="35"),
    )
    op.add_column(
        "org_ai_config",
        sa.Column("health_weight_sentiment", sa.Integer(), nullable=False, server_default="25"),
    )
    op.add_column(
        "org_ai_config",
        sa.Column("health_weight_resolution", sa.Integer(), nullable=False, server_default="25"),
    )
    op.add_column(
        "org_ai_config",
        sa.Column("health_weight_frequency", sa.Integer(), nullable=False, server_default="15"),
    )

    # ── api_keys: public-API access keys ────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=128), nullable=False),
        sa.Column("scopes", sa.String(length=100), nullable=False, server_default="read"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_keys_id", "api_keys", ["id"], unique=False)
    op.create_index("ix_api_keys_organization_id", "api_keys", ["organization_id"], unique=False)
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"], unique=False)
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_index("ix_api_keys_key_prefix", table_name="api_keys")
    op.drop_index("ix_api_keys_organization_id", table_name="api_keys")
    op.drop_index("ix_api_keys_id", table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_column("org_ai_config", "health_weight_frequency")
    op.drop_column("org_ai_config", "health_weight_resolution")
    op.drop_column("org_ai_config", "health_weight_sentiment")
    op.drop_column("org_ai_config", "health_weight_churn")
    op.drop_column("org_ai_config", "base_url")
