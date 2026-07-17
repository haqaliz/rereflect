"""add saml auth requests

Creates saml_auth_requests, the DB-backed InResponseTo / replay store for the
provider-and-replay-store aspect of saml-sso (PRD M3 replay defense). One row
per SP-initiated AuthnRequest we issue: request_id (the AuthnRequest ID) is the
PK, consumed_at is flipped exactly once by a race-safe conditional UPDATE at
the ACS, and expires_at (issue time + SAML_REQUEST_TTL_SECONDS) drives expiry +
opportunistic cleanup. No secret material is stored here.

No DB-level partial index tricks are needed: the one-time-consume guarantee is
the conditional UPDATE in src/services/saml_replay.py, portable across SQLite
(tests) and PostgreSQL (prod).

HEAD VERIFICATION: `alembic heads` was re-run LIVE in this worktree
immediately before authoring this revision and returned exactly one line:
`p0q1r2s3t4u5 (head)`. This revision chains directly off that sole verified
head — no merge revision, no static parse.

Revision ID: q1r2s3t4u5v6
Revises: p0q1r2s3t4u5
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "q1r2s3t4u5v6"
down_revision = "p0q1r2s3t4u5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "saml_auth_requests",
        sa.Column("request_id", sa.String(length=255), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index(
        "ix_saml_auth_requests_org_id", "saml_auth_requests", ["organization_id"]
    )
    op.create_index(
        "ix_saml_auth_requests_expires_at", "saml_auth_requests", ["expires_at"]
    )


def downgrade():
    op.drop_index("ix_saml_auth_requests_expires_at", table_name="saml_auth_requests")
    op.drop_index("ix_saml_auth_requests_org_id", table_name="saml_auth_requests")
    op.drop_table("saml_auth_requests")
