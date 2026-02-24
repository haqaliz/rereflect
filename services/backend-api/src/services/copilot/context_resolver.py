"""
Context Scope Resolver — builds LLM context based on selected scope + @mentions.

Scopes: all_data, feedbacks, customers, pain_points, feature_requests, dashboard
@mentions: @customer:email, @feedback:#id, @period:last-30-days, @tag:name
"""

import re
import logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import text

logger = logging.getLogger(__name__)

# Max context size (characters) to avoid LLM token overflow
_MAX_CONTEXT_CHARS = 15_000

# @mention patterns
_MENTION_PATTERNS = {
    "customer": re.compile(r"@customer:([\w.+@-]+)", re.IGNORECASE),
    "feedback": re.compile(r"@feedback:#(\d+)", re.IGNORECASE),
    "period": re.compile(r"@period:([\w-]+)", re.IGNORECASE),
    "tag": re.compile(r"@tag:([\w-]+)", re.IGNORECASE),
}

# Max conversation history messages to include in context
_MAX_HISTORY_MESSAGES = 10


class ContextResolver:
    """
    Resolves context for the AI copilot based on scope and @mentions.
    Builds a structured context string for use in LLM prompts.
    """

    def parse_mentions(self, message: str) -> dict:
        """
        Parse @mention entities from message text.

        Returns:
            Dict with mention types as keys, e.g.:
            {"customer": "john@example.com", "period": "last-30-days"}
        """
        mentions = {}
        for mention_type, pattern in _MENTION_PATTERNS.items():
            match = pattern.search(message)
            if match:
                mentions[mention_type] = match.group(1)
        return mentions

    def resolve_period(self, period: str) -> dict:
        """
        Resolve a period string to a date range dict.

        Returns:
            {"date_from": datetime, "date_to": datetime}
        """
        now = datetime.utcnow()

        _PERIOD_MAP = {
            "last-7-days": timedelta(days=7),
            "last-14-days": timedelta(days=14),
            "last-30-days": timedelta(days=30),
            "last-90-days": timedelta(days=90),
        }

        if period in _PERIOD_MAP:
            return {
                "date_from": now - _PERIOD_MAP[period],
                "date_to": now,
            }

        if period == "this-week":
            # Start of current week (Monday)
            weekday = now.weekday()  # 0=Monday
            week_start = now - timedelta(days=weekday)
            return {
                "date_from": week_start.replace(hour=0, minute=0, second=0, microsecond=0),
                "date_to": now,
            }

        if period == "this-month":
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return {
                "date_from": month_start,
                "date_to": now,
            }

        if period == "today":
            return {
                "date_from": now.replace(hour=0, minute=0, second=0, microsecond=0),
                "date_to": now,
            }

        # Default: last 30 days for unknown periods
        return {
            "date_from": now - timedelta(days=30),
            "date_to": now,
        }

    def build_context(
        self,
        scope: str,
        org_id: int,
        db,
        mentions: dict,
        conversation_history: list,
    ) -> str:
        """
        Build a context string for the LLM prompt based on scope and @mentions.

        Args:
            scope: One of all_data, feedbacks, customers, pain_points,
                   feature_requests, dashboard
            org_id: Organization ID for data isolation
            db: SQLAlchemy session
            mentions: Parsed @mentions dict
            conversation_history: List of previous messages [{role, content}]

        Returns:
            Context string for LLM prompt (max ~15K chars)
        """
        parts = []

        # Add conversation history (truncated)
        if conversation_history:
            history_text = self._format_history(conversation_history)
            parts.append(history_text)

        # Resolve period if mentioned
        date_filter = None
        if "period" in mentions:
            date_filter = self.resolve_period(mentions["period"])

        # Build scope-specific context
        scope_context = self._build_scope_context(scope, org_id, db, mentions, date_filter)
        parts.append(scope_context)

        # Join parts and truncate
        context = "\n\n".join(parts)
        if len(context) > _MAX_CONTEXT_CHARS:
            context = context[:_MAX_CONTEXT_CHARS] + "\n... [context truncated]"

        return context

    def _build_scope_context(
        self,
        scope: str,
        org_id: int,
        db,
        mentions: dict,
        date_filter: Optional[dict],
    ) -> str:
        """Build context for a specific scope."""
        scope_builders = {
            "all_data": self._context_all_data,
            "feedbacks": self._context_feedbacks,
            "customers": self._context_customers,
            "pain_points": self._context_pain_points,
            "feature_requests": self._context_feature_requests,
            "dashboard": self._context_dashboard,
        }

        builder = scope_builders.get(scope, self._context_all_data)
        return builder(org_id, db, mentions, date_filter)

    def _context_all_data(self, org_id: int, db, mentions: dict, date_filter: Optional[dict]) -> str:
        """Build summary context across all data types."""
        parts = ["## Data Summary\n"]

        # Feedback counts
        try:
            total = self._safe_scalar(
                db, "SELECT COUNT(*) FROM feedback_items WHERE organization_id = :org_id",
                {"org_id": org_id}
            )
            negative = self._safe_scalar(
                db,
                "SELECT COUNT(*) FROM feedback_items WHERE organization_id = :org_id AND sentiment_label = 'negative'",
                {"org_id": org_id}
            )
            urgent = self._safe_scalar(
                db,
                "SELECT COUNT(*) FROM feedback_items WHERE organization_id = :org_id AND is_urgent = true",
                {"org_id": org_id}
            )
            parts.append(f"**Feedback**: {total} total, {negative} negative, {urgent} urgent")
        except Exception as e:
            logger.warning(f"Failed to fetch feedback summary: {e}")
            parts.append("**Feedback**: (unavailable)")

        # Customer counts
        try:
            customer_count = self._safe_scalar(
                db,
                "SELECT COUNT(*) FROM customer_health_scores WHERE organization_id = :org_id",
                {"org_id": org_id}
            )
            at_risk = self._safe_scalar(
                db,
                "SELECT COUNT(*) FROM customer_health_scores WHERE organization_id = :org_id AND risk_level IN ('at_risk', 'critical')",
                {"org_id": org_id}
            )
            parts.append(f"**Customers**: {customer_count} total, {at_risk} at risk")
        except Exception as e:
            logger.warning(f"Failed to fetch customer summary: {e}")
            parts.append("**Customers**: (unavailable)")

        return "\n".join(parts)

    def _context_feedbacks(self, org_id: int, db, mentions: dict, date_filter: Optional[dict]) -> str:
        """Build feedback-focused context."""
        parts = ["## Feedback Context\n"]

        try:
            params = {"org_id": org_id}
            date_clause = ""
            if date_filter:
                date_clause = " AND created_at >= :date_from AND created_at <= :date_to"
                params["date_from"] = date_filter["date_from"]
                params["date_to"] = date_filter["date_to"]

            total = self._safe_scalar(
                db,
                f"SELECT COUNT(*) FROM feedback_items WHERE organization_id = :org_id{date_clause}",
                params
            )
            parts.append(f"**Total feedbacks**: {total}")

            # Sentiment breakdown
            rows = self._safe_fetchall(
                db,
                f"SELECT sentiment_label, COUNT(*) as cnt FROM feedback_items WHERE organization_id = :org_id{date_clause} GROUP BY sentiment_label",
                params
            )
            if rows:
                breakdown = ", ".join(f"{r[0] or 'unknown'}: {r[1]}" for r in rows)
                parts.append(f"**Sentiment breakdown**: {breakdown}")

        except Exception as e:
            logger.warning(f"Failed to fetch feedback context: {e}")
            parts.append("(feedback data unavailable)")

        # Handle @tag mention
        if "tag" in mentions:
            parts.append(f"**Filter**: Tag = {mentions['tag']}")

        return "\n".join(parts)

    def _context_customers(self, org_id: int, db, mentions: dict, date_filter: Optional[dict]) -> str:
        """Build customer-focused context."""
        parts = ["## Customer Context\n"]

        try:
            params = {"org_id": org_id}
            total = self._safe_scalar(
                db,
                "SELECT COUNT(*) FROM customer_health_scores WHERE organization_id = :org_id",
                params
            )
            avg_score = self._safe_scalar(
                db,
                "SELECT COALESCE(CAST(AVG(health_score) AS INTEGER), 0) FROM customer_health_scores WHERE organization_id = :org_id",
                params
            )
            parts.append(f"**Total customers**: {total}")
            parts.append(f"**Average health score**: {avg_score}/100")

            # Risk distribution
            rows = self._safe_fetchall(
                db,
                "SELECT risk_level, COUNT(*) as cnt FROM customer_health_scores WHERE organization_id = :org_id GROUP BY risk_level",
                params
            )
            if rows:
                breakdown = ", ".join(f"{r[0] or 'unknown'}: {r[1]}" for r in rows)
                parts.append(f"**Risk distribution**: {breakdown}")

        except Exception as e:
            logger.warning(f"Failed to fetch customer context: {e}")
            parts.append("(customer data unavailable)")

        # Handle specific @customer mention
        if "customer" in mentions:
            parts.append(f"**Focus**: Customer = {mentions['customer']}")

        return "\n".join(parts)

    def _context_pain_points(self, org_id: int, db, mentions: dict, date_filter: Optional[dict]) -> str:
        """Build pain points context."""
        parts = ["## Pain Points Context\n"]

        try:
            params = {"org_id": org_id}
            total = self._safe_scalar(
                db,
                "SELECT COUNT(*) FROM feedback_items WHERE organization_id = :org_id AND pain_point_category IS NOT NULL",
                params
            )
            parts.append(f"**Total pain points identified**: {total}")

            # Category breakdown
            rows = self._safe_fetchall(
                db,
                "SELECT pain_point_category, COUNT(*) as cnt FROM feedback_items WHERE organization_id = :org_id AND pain_point_category IS NOT NULL GROUP BY pain_point_category ORDER BY cnt DESC LIMIT 5",
                params
            )
            if rows:
                top_cats = ", ".join(f"{r[0]}: {r[1]}" for r in rows)
                parts.append(f"**Top categories**: {top_cats}")

        except Exception as e:
            logger.warning(f"Failed to fetch pain points context: {e}")
            parts.append("(pain points data unavailable)")

        return "\n".join(parts)

    def _context_feature_requests(self, org_id: int, db, mentions: dict, date_filter: Optional[dict]) -> str:
        """Build feature requests context."""
        parts = ["## Feature Requests Context\n"]

        try:
            params = {"org_id": org_id}
            total = self._safe_scalar(
                db,
                "SELECT COUNT(*) FROM feedback_items WHERE organization_id = :org_id AND feature_request_category IS NOT NULL",
                params
            )
            parts.append(f"**Total feature requests**: {total}")

            rows = self._safe_fetchall(
                db,
                "SELECT feature_request_category, COUNT(*) as cnt FROM feedback_items WHERE organization_id = :org_id AND feature_request_category IS NOT NULL GROUP BY feature_request_category ORDER BY cnt DESC LIMIT 5",
                params
            )
            if rows:
                top_cats = ", ".join(f"{r[0]}: {r[1]}" for r in rows)
                parts.append(f"**Top categories**: {top_cats}")

        except Exception as e:
            logger.warning(f"Failed to fetch feature requests context: {e}")
            parts.append("(feature requests data unavailable)")

        return "\n".join(parts)

    def _context_dashboard(self, org_id: int, db, mentions: dict, date_filter: Optional[dict]) -> str:
        """Build dashboard summary context."""
        parts = ["## Dashboard Summary\n"]

        try:
            params = {"org_id": org_id}
            total_fb = self._safe_scalar(
                db,
                "SELECT COUNT(*) FROM feedback_items WHERE organization_id = :org_id",
                params
            )
            urgent_fb = self._safe_scalar(
                db,
                "SELECT COUNT(*) FROM feedback_items WHERE organization_id = :org_id AND is_urgent = true",
                params
            )
            customers = self._safe_scalar(
                db,
                "SELECT COUNT(*) FROM customer_health_scores WHERE organization_id = :org_id",
                params
            )
            parts.append(f"**Total feedback**: {total_fb}")
            parts.append(f"**Urgent feedback**: {urgent_fb}")
            parts.append(f"**Total customers tracked**: {customers}")

        except Exception as e:
            logger.warning(f"Failed to fetch dashboard context: {e}")
            parts.append("(dashboard data unavailable)")

        return "\n".join(parts)

    def _format_history(self, history: list) -> str:
        """Format conversation history for inclusion in context."""
        # Take last N messages only
        recent = history[-_MAX_HISTORY_MESSAGES:]
        lines = ["## Conversation History\n"]
        for msg in recent:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")[:500]  # Truncate long messages
            lines.append(f"**{role}**: {content}")
        return "\n".join(lines)

    def _safe_scalar(self, db, sql: str, params: dict):
        """Execute a scalar query safely, returning 0 on error."""
        try:
            result = db.execute(text(sql), params)
            return result.scalar() or 0
        except Exception:
            return 0

    def _safe_fetchall(self, db, sql: str, params: dict):
        """Execute a fetchall query safely, returning [] on error."""
        try:
            result = db.execute(text(sql), params)
            return result.fetchall()
        except Exception:
            return []
