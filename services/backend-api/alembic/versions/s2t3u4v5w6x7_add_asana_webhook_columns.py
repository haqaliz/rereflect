"""add asana webhook columns

Adds `asana_integrations.webhook_secret` (Text, nullable, Fernet-encrypted at
the receiver/route layer) and `asana_integrations.webhook_gid` (String(255),
nullable) for the asana-webhook aspect of status-sync-realtime-mapping (PRD).

Mirrors r1s2t3u4v5w6_add_jira_webhook_secret.py's posture: NULL
webhook_secret means the inbound real-time webhook has not completed its
handshake yet (fail-closed -- see src/api/routes/asana_webhook.py). Unlike
Jira (where we generate the secret ourselves), Asana's webhook_secret is
captured from the `X-Hook-Secret` header on the FIRST delivery (the
handshake) -- see POST /api/v1/integrations/asana/webhook/enable (Phase 2)
and the receiver's handshake branch (Phase 3). webhook_gid is the Asana
webhook gid returned by `POST /webhooks` (used to call `DELETE
/webhooks/{gid}` at Asana when the operator disables the webhook).
Additive-only; existing rows are unaffected.

HEAD VERIFICATION: `alembic heads` was re-run LIVE in this worktree
immediately before authoring this revision and returned exactly one line:
`r1s2t3u4v5w6 (head)`. This revision chains directly off that sole verified
head -- no merge revision, no static parse.

Revision ID: s2t3u4v5w6x7
Revises: r1s2t3u4v5w6
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "s2t3u4v5w6x7"
down_revision = "r1s2t3u4v5w6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("asana_integrations", sa.Column("webhook_secret", sa.Text(), nullable=True))
    op.add_column(
        "asana_integrations", sa.Column("webhook_gid", sa.String(length=255), nullable=True)
    )


def downgrade():
    op.drop_column("asana_integrations", "webhook_gid")
    op.drop_column("asana_integrations", "webhook_secret")
