"""add jira webhook secret

Adds `jira_integrations.webhook_secret` (Text, nullable, Fernet-encrypted at
the route layer) for the jira-webhook aspect of status-sync-realtime-mapping
(PRD). Mirrors `zendesk_integrations.webhook_secret` (see
z1a2b3c4d5e6_add_zendesk_integration_tables.py) exactly: NULL means the
inbound real-time webhook has not been enabled for this org (fail-closed —
see src/api/routes/jira_webhook.py); a non-NULL value is generated via
secrets.token_urlsafe(32) and encrypted with encrypt_api_key when an
admin/owner enables it (POST /api/v1/integrations/jira/webhook/enable).
Additive-only; existing rows are unaffected.

HEAD VERIFICATION: `alembic heads` was re-run LIVE in this worktree
immediately before authoring this revision and returned exactly one line:
`q1r2s3t4u5v6 (head)`. This revision chains directly off that sole verified
head — no merge revision, no static parse.

Revision ID: r1s2t3u4v5w6
Revises: q1r2s3t4u5v6
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "r1s2t3u4v5w6"
down_revision = "q1r2s3t4u5v6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jira_integrations", sa.Column("webhook_secret", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("jira_integrations", "webhook_secret")
