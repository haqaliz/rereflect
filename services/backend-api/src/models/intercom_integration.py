"""Org-wide Intercom connection via a private-app Access Token (token-paste).

Mirrors ZendeskIntegration: one row per organization, BYO credential, secrets
Fernet-encrypted at the route layer.

Why a dedicated table rather than a row in `integrations`: the generic
`Integration` table stores OAuth tokens in PLAINTEXT (see the comment on
`models/integration.py`), and every newer BYO-token integration -- Zendesk,
Jira, Asana, HubSpot, Salesforce -- uses its own encrypted table instead. This
follows that precedent, so the new path is encrypted from birth rather than
inheriting a defect that still needs a backfill migration to fix.

`client_secret` is the Developer Hub app's client secret, which is the key
Intercom signs `X-Hub-Signature` with. It is collected here because obtaining
an Access Token requires creating an app that has one; storing it per-org is
what lets webhook verification become per-tenant instead of keying off a single
global env var. Nullable: an operator who only wants the pull path is not made
to hand over a secret nothing reads.

See docs/planning/intercom-selfhost-ingestion/token-paste-connect/.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)

from .base import Base


class IntercomIntegration(Base):
    """Org-wide Intercom connection (private-app Access Token). One row per org."""

    __tablename__ = "intercom_integrations"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )

    # Fernet-encrypted via encrypt_api_key (route-layer concern, as with Zendesk).
    access_token = Column(Text, nullable=False)
    client_secret = Column(Text, nullable=True)
    token_hint = Column(String(8), nullable=True)  # last chars of plaintext

    # From GET https://api.intercom.io/me. workspace_id is the tenancy
    # discriminator the worker matches inbound events against -- a row without
    # one can never match a feedback source, so the route rejects that case.
    workspace_id = Column(String(255), nullable=False)
    workspace_name = Column(String(255), nullable=True)
    admin_id = Column(String(255), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    connected_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    connected_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Pull cursor. Read by the sync task as `last_synced_at or connected_at` --
    # never epoch/None, so a missing cursor cannot trigger a historical backfill.
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), nullable=True)
    last_error = Column(Text, nullable=True)

    # Backlog drain estimate (intercom-backlog-drain-visibility): how many
    # conversations remain in the sync window after the last completed run.
    # Written by the worker sync task; reset to NULL on error paths. None =
    # no estimate (never-synced, error reset, OAuth path has no pull).
    backlog_remaining = Column(Integer, nullable=True)

    # Intercom write-back (intercom-writeback aspect): per-org opt-in, off by
    # default, + status readout. Mirrors the CRM writeback column set
    # (hubspot_integration.py). writeback_action is validated at the Pydantic
    # layer (note_only | note_and_close) — no DB CHECK.
    writeback_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    writeback_action = Column(String(32), nullable=False, default="note_and_close", server_default="note_and_close")
    last_writeback_at = Column(DateTime(timezone=True), nullable=True)
    last_writeback_status = Column(String(64), nullable=True)
    last_writeback_error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_intercom_integrations_org_id"),
        Index("ix_intercom_integrations_org_id", "organization_id"),
        Index("ix_intercom_integrations_workspace_id", "workspace_id"),
    )

    def __repr__(self):
        return (
            f"<IntercomIntegration(id={self.id}, org={self.organization_id}, "
            f"workspace='{self.workspace_id}', active={self.is_active})>"
        )
