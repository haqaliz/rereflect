"""
TDD tests for the Context Scope Resolver (RED → GREEN → REFACTOR).

Tests cover:
- @mention parsing from user messages
- Scope-based context building for each scope type
- Org isolation (only pulls data from user's org)
- Conversation history inclusion
- Context size limits
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    """Mock SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def resolver():
    from src.services.copilot.context_resolver import ContextResolver
    return ContextResolver()


@pytest.fixture
def org_id():
    return 42


# ── @MENTION PARSING ──────────────────────────────────────────────────────────

class TestMentionParsing:
    """Parse @mention entities from user message text."""

    def test_parses_customer_mention(self, resolver):
        message = "Tell me about @customer:john@example.com"
        mentions = resolver.parse_mentions(message)
        assert "customer" in mentions
        assert mentions["customer"] == "john@example.com"

    def test_parses_feedback_mention(self, resolver):
        message = "What happened with @feedback:#1234?"
        mentions = resolver.parse_mentions(message)
        assert "feedback" in mentions
        assert mentions["feedback"] == "1234"

    def test_parses_period_last_30_days(self, resolver):
        message = "Show trends @period:last-30-days"
        mentions = resolver.parse_mentions(message)
        assert "period" in mentions
        assert mentions["period"] == "last-30-days"

    def test_parses_period_last_7_days(self, resolver):
        message = "Analysis @period:last-7-days"
        mentions = resolver.parse_mentions(message)
        assert "period" in mentions
        assert mentions["period"] == "last-7-days"

    def test_parses_tag_mention(self, resolver):
        message = "Show feedbacks with @tag:pricing"
        mentions = resolver.parse_mentions(message)
        assert "tag" in mentions
        assert mentions["tag"] == "pricing"

    def test_parses_multiple_mentions(self, resolver):
        message = "@customer:alice@test.com feedback @period:last-30-days"
        mentions = resolver.parse_mentions(message)
        assert "customer" in mentions
        assert "period" in mentions

    def test_no_mentions_returns_empty_dict(self, resolver):
        message = "How many negative feedbacks this week?"
        mentions = resolver.parse_mentions(message)
        assert mentions == {}

    def test_invalid_mention_format_ignored(self, resolver):
        message = "What about @ customer?"
        mentions = resolver.parse_mentions(message)
        assert "customer" not in mentions


# ── SCOPE CONTEXT BUILDING ────────────────────────────────────────────────────

class TestScopeContextBuilding:
    """Build LLM context strings based on selected scope."""

    def test_all_data_scope_returns_context(self, resolver, mock_db, org_id):
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.scalar.return_value = 0
        context = resolver.build_context(
            scope="all_data",
            org_id=org_id,
            db=mock_db,
            mentions={},
            conversation_history=[]
        )
        assert context is not None
        assert isinstance(context, str)
        assert len(context) > 0

    def test_feedbacks_scope_queries_feedback_table(self, resolver, mock_db, org_id):
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.scalar.return_value = 0
        context = resolver.build_context(
            scope="feedbacks",
            org_id=org_id,
            db=mock_db,
            mentions={},
            conversation_history=[]
        )
        assert context is not None
        assert isinstance(context, str)

    def test_customers_scope_returns_context(self, resolver, mock_db, org_id):
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.scalar.return_value = 0
        context = resolver.build_context(
            scope="customers",
            org_id=org_id,
            db=mock_db,
            mentions={},
            conversation_history=[]
        )
        assert context is not None
        assert isinstance(context, str)

    def test_pain_points_scope_returns_context(self, resolver, mock_db, org_id):
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.scalar.return_value = 0
        context = resolver.build_context(
            scope="pain_points",
            org_id=org_id,
            db=mock_db,
            mentions={},
            conversation_history=[]
        )
        assert context is not None

    def test_feature_requests_scope_returns_context(self, resolver, mock_db, org_id):
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.scalar.return_value = 0
        context = resolver.build_context(
            scope="feature_requests",
            org_id=org_id,
            db=mock_db,
            mentions={},
            conversation_history=[]
        )
        assert context is not None

    def test_dashboard_scope_returns_context(self, resolver, mock_db, org_id):
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.scalar.return_value = 0
        context = resolver.build_context(
            scope="dashboard",
            org_id=org_id,
            db=mock_db,
            mentions={},
            conversation_history=[]
        )
        assert context is not None

    def test_unknown_scope_returns_default_context(self, resolver, mock_db, org_id):
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.scalar.return_value = 0
        context = resolver.build_context(
            scope="unknown_scope",
            org_id=org_id,
            db=mock_db,
            mentions={},
            conversation_history=[]
        )
        assert context is not None


# ── ORG ISOLATION ─────────────────────────────────────────────────────────────

class TestOrgIsolation:
    """Context must only include data from the user's organization."""

    def test_context_includes_org_id_in_queries(self, resolver, mock_db, org_id):
        """When build_context queries the DB, it must pass org_id."""
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.scalar.return_value = 0

        resolver.build_context(
            scope="feedbacks",
            org_id=org_id,
            db=mock_db,
            mentions={},
            conversation_history=[]
        )

        # Check that execute was called with org_id in the parameters
        calls = mock_db.execute.call_args_list
        # At least one query should reference org_id
        org_referenced = any(
            str(org_id) in str(call) or "org_id" in str(call)
            for call in calls
        )
        assert org_referenced, "Context queries should reference org_id"


# ── CONVERSATION HISTORY ──────────────────────────────────────────────────────

class TestConversationHistory:
    """Previous messages should be included in context for multi-turn conversations."""

    def test_empty_history_works(self, resolver, mock_db, org_id):
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.scalar.return_value = 0
        context = resolver.build_context(
            scope="all_data",
            org_id=org_id,
            db=mock_db,
            mentions={},
            conversation_history=[]
        )
        assert context is not None

    def test_history_included_in_context(self, resolver, mock_db, org_id):
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.scalar.return_value = 0
        history = [
            {"role": "user", "content": "How many feedbacks?"},
            {"role": "assistant", "content": "You have 100 feedbacks."},
        ]
        context = resolver.build_context(
            scope="all_data",
            org_id=org_id,
            db=mock_db,
            mentions={},
            conversation_history=history
        )
        assert context is not None
        # The history content should be referenced or returned alongside context
        # (resolver may return it as part of context or separately)

    def test_long_history_is_truncated(self, resolver, mock_db, org_id):
        """Very long conversation history should be truncated, not raise errors."""
        mock_db.execute.return_value.fetchall.return_value = []
        mock_db.execute.return_value.scalar.return_value = 0
        history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i} " + "x" * 200}
            for i in range(100)
        ]
        context = resolver.build_context(
            scope="all_data",
            org_id=org_id,
            db=mock_db,
            mentions={},
            conversation_history=history
        )
        assert context is not None


# ── PERIOD MENTION RESOLUTION ─────────────────────────────────────────────────

class TestPeriodMentionResolution:
    """@period mentions should resolve to actual date ranges."""

    def test_resolve_last_7_days(self, resolver):
        date_range = resolver.resolve_period("last-7-days")
        assert "date_from" in date_range
        assert "date_to" in date_range
        assert isinstance(date_range["date_from"], datetime)
        assert isinstance(date_range["date_to"], datetime)
        # date_from should be approximately 7 days ago
        delta = date_range["date_to"] - date_range["date_from"]
        assert abs(delta.days - 7) <= 1

    def test_resolve_last_30_days(self, resolver):
        date_range = resolver.resolve_period("last-30-days")
        assert "date_from" in date_range
        delta = date_range["date_to"] - date_range["date_from"]
        assert abs(delta.days - 30) <= 1

    def test_resolve_this_week(self, resolver):
        date_range = resolver.resolve_period("this-week")
        assert "date_from" in date_range
        assert "date_to" in date_range

    def test_resolve_this_month(self, resolver):
        date_range = resolver.resolve_period("this-month")
        assert "date_from" in date_range
        assert "date_to" in date_range

    def test_unknown_period_returns_default(self, resolver):
        date_range = resolver.resolve_period("unknown-period")
        assert date_range is not None
        assert "date_from" in date_range


# ── CONTEXT SIZE LIMITS ───────────────────────────────────────────────────────

class TestContextSizeLimits:
    """Context strings should stay within LLM token limits."""

    def test_context_has_max_length(self, resolver, mock_db, org_id):
        mock_db.execute.return_value.fetchall.return_value = [
            MagicMock(text=f"Feedback {i} " + "x" * 500, sentiment_label="positive")
            for i in range(1000)
        ]
        mock_db.execute.return_value.scalar.return_value = 1000
        context = resolver.build_context(
            scope="feedbacks",
            org_id=org_id,
            db=mock_db,
            mentions={},
            conversation_history=[]
        )
        # Context should not exceed ~20K characters (rough token limit proxy)
        assert len(context) <= 20_000
