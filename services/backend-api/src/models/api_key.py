from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime
from .base import Base


class ApiKey(Base):
    """Public-API access key (distinct from OrgApiKey, which holds BYOK LLM keys).

    The full key (format ``rrf_<random>``) is shown to the user exactly once at
    creation; only its sha256 hash + a short prefix are stored.
    """

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(100), nullable=False)
    key_prefix = Column(String(16), nullable=False, index=True)
    key_hash = Column(String(128), nullable=False, unique=True, index=True)
    scopes = Column(String(100), default="read", nullable=False)  # comma list: read,ingest
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ApiKey(id={self.id}, org={self.organization_id}, prefix='{self.key_prefix}')>"
