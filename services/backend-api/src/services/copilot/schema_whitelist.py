"""
Schema Whitelist — defines the approved tables and columns for copilot SQL queries.

Only tables/columns in this whitelist are allowed in LLM-generated SQL.
Sensitive tables (users, subscriptions, org_api_keys) are excluded.

The whitelist can be loaded from the copilot_schema_whitelist DB table
(with 5-minute cache) or from the hardcoded DEFAULT_WHITELIST below.
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Cache TTL (seconds)
_CACHE_TTL = 300  # 5 minutes

# ── Default hardcoded whitelist ───────────────────────────────────────────────
# Used when copilot_schema_whitelist table is not yet available.
# Key: table_name, Value: list of allowed columns (None = all columns allowed)

DEFAULT_WHITELIST: dict[str, Optional[list]] = {
    "feedback_items": [
        "id",
        "organization_id",
        "text",
        "source",
        "sentiment_score",
        "sentiment_label",
        "extracted_issue",
        "tags",
        "is_urgent",
        "created_at",
        "pain_point_category",
        "pain_point_severity",
        "pain_point_text",
        "feature_request_category",
        "feature_request_priority",
        "feature_request_text",
        "urgent_category",
        "urgent_response_time",
        "churn_risk_score",
        "suggested_action",
        "workflow_status",
        "customer_email",
        "llm_analyzed",
    ],
    "customer_health_scores": [
        "id",
        "organization_id",
        "customer_email",
        "customer_name",
        "health_score",
        "churn_risk_component",
        "sentiment_component",
        "resolution_component",
        "frequency_component",
        "feedback_count",
        "last_feedback_at",
        "risk_level",
        "confidence_level",
        "confidence_score",
        "is_archived",
        "created_at",
        "updated_at",
    ],
    "anomaly_events": [
        "id",
        "organization_id",
        "detected_at",
        "anomaly_type",
        "severity",
        "description",
        "affected_count",
        "created_at",
    ],
    # Excluded tables (explicitly listed for reference):
    # - users (passwords, personal data)
    # - organizations (billing details)
    # - subscriptions (payment info)
    # - org_api_keys (encrypted API keys)
    # - sessions (auth tokens)
    # - team_invites (invite tokens)
    # - audit_logs (internal logs)
}

# Tables that are NEVER allowed, even if added to the DB whitelist
ALWAYS_EXCLUDED_TABLES = {
    "users",
    "organizations",
    "subscriptions",
    "org_api_keys",
    "sessions",
    "team_invites",
    "audit_logs",
    "llm_usage_logs",
    "org_ai_configs",
    "pending_feedbacks",
}


class SchemaWhitelistLoader:
    """
    Loads and caches the schema whitelist for copilot SQL validation.
    Falls back to DEFAULT_WHITELIST if DB table is not available.
    """

    def __init__(self):
        self._cache: Optional[dict] = None
        self._cache_time: float = 0.0

    def get_whitelist(self, db=None) -> dict:
        """
        Get the current schema whitelist.
        Loads from DB if available, with 5-minute cache.

        Args:
            db: SQLAlchemy session (optional; uses DEFAULT_WHITELIST if not provided)

        Returns:
            Dict mapping table_name → list of allowed columns (or None for all)
        """
        now = time.time()

        # Check cache
        if self._cache is not None and (now - self._cache_time) < _CACHE_TTL:
            return self._cache

        # Try loading from DB
        if db is not None:
            try:
                whitelist = self._load_from_db(db)
                if whitelist:
                    self._cache = whitelist
                    self._cache_time = now
                    return whitelist
            except Exception as e:
                logger.warning(f"Failed to load schema whitelist from DB: {e}")

        # Fall back to hardcoded default
        self._cache = DEFAULT_WHITELIST
        self._cache_time = now
        return DEFAULT_WHITELIST

    def invalidate_cache(self) -> None:
        """Invalidate the cache so next call reloads from DB."""
        self._cache = None
        self._cache_time = 0.0

    def _load_from_db(self, db) -> Optional[dict]:
        """Load whitelist from copilot_schema_whitelist table."""
        from sqlalchemy import text

        try:
            rows = db.execute(
                text(
                    "SELECT table_name, column_name FROM copilot_schema_whitelist "
                    "WHERE is_active = true ORDER BY table_name, column_name"
                )
            ).fetchall()
        except Exception:
            return None

        if not rows:
            return None

        whitelist: dict[str, Optional[list]] = {}
        for row in rows:
            table_name = row[0]
            column_name = row[1]  # None means "all columns"

            # Never allow excluded tables
            if table_name.lower() in ALWAYS_EXCLUDED_TABLES:
                continue

            if table_name not in whitelist:
                whitelist[table_name] = []

            if column_name is not None:
                whitelist[table_name].append(column_name)
            else:
                whitelist[table_name] = None  # All columns allowed

        return whitelist if whitelist else None


# Singleton instance
_loader = SchemaWhitelistLoader()


def get_whitelist(db=None) -> dict:
    """Get the current schema whitelist (uses singleton loader)."""
    return _loader.get_whitelist(db)


def invalidate_whitelist_cache() -> None:
    """Invalidate the whitelist cache."""
    _loader.invalidate_cache()
