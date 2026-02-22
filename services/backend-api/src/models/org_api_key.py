from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, Index, UniqueConstraint
from datetime import datetime
from .base import Base


class OrgApiKey(Base):
    __tablename__ = "org_api_keys"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    provider = Column(String(20), nullable=False)  # openai, anthropic, google
    encrypted_key = Column(Text, nullable=False)  # Fernet-encrypted API key
    key_hint = Column(String(8), nullable=True)  # Last 4 chars for display: "...abc1"
    is_valid = Column(Boolean, default=True)  # Set false on persistent auth errors
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint('organization_id', 'provider', name='uq_org_api_key_org_provider'),
        Index('idx_org_api_keys_org', 'organization_id'),
    )

    def __repr__(self):
        return f"<OrgApiKey(org={self.organization_id}, provider='{self.provider}', valid={self.is_valid})>"
