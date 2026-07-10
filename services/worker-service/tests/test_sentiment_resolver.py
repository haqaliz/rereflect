"""
Phase 1 RED: Tests for resolve_sentiment_provider (worker-service mirror).

Same degrade matrix as backend-api's test_sentiment_resolver.py, against the
worker's independent mirror resolver (reads the worker's own OrgAIConfig ORM
mirror, no cross-service import).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.services.sentiment_resolver import (
    resolve_sentiment_provider,
    ResolvedSentiment,
    VALID_SENTIMENT_PROVIDERS,
)


def _make_config(sentiment_provider=None) -> MagicMock:
    cfg = MagicMock()
    cfg.sentiment_provider = sentiment_provider
    return cfg


def _make_db_with_config(config) -> MagicMock:
    db = MagicMock()
    query_mock = MagicMock()
    query_mock.filter_by.return_value.first.return_value = config
    db.query.return_value = query_mock
    return db


def _make_db_without_config() -> MagicMock:
    db = MagicMock()
    query_mock = MagicMock()
    query_mock.filter_by.return_value.first.return_value = None
    db.query.return_value = query_mock
    return db


class TestResolveSentimentProvider:
    def test_unset_column_returns_none(self):
        config = _make_config(sentiment_provider=None)
        db = _make_db_with_config(config)

        result = resolve_sentiment_provider(org_id=1, db=db)

        assert result is None

    def test_no_org_ai_config_row_returns_none(self):
        db = _make_db_without_config()

        result = resolve_sentiment_provider(org_id=999, db=db)

        assert result is None

    def test_explicit_vader_returns_resolved_vader(self):
        config = _make_config(sentiment_provider="vader")
        db = _make_db_with_config(config)

        result = resolve_sentiment_provider(org_id=1, db=db)

        assert result is not None
        assert isinstance(result, ResolvedSentiment)
        assert result.provider == "vader"

    def test_explicit_transformer_returns_resolved_transformer(self):
        config = _make_config(sentiment_provider="transformer")
        db = _make_db_with_config(config)

        result = resolve_sentiment_provider(org_id=1, db=db)

        assert result is not None
        assert result.provider == "transformer"

    def test_unrecognized_value_returns_none(self):
        config = _make_config(sentiment_provider="nonsense")
        db = _make_db_with_config(config)

        result = resolve_sentiment_provider(org_id=1, db=db)

        assert result is None

    def test_db_query_exception_returns_none(self):
        db = MagicMock()
        db.query.side_effect = Exception("boom")

        result = resolve_sentiment_provider(org_id=1, db=db)

        assert result is None

    def test_cross_org_isolation(self):
        config_a = _make_config(sentiment_provider="transformer")
        db_a = _make_db_with_config(config_a)
        result_a = resolve_sentiment_provider(org_id=1, db=db_a)

        config_b = _make_config(sentiment_provider=None)
        db_b = _make_db_with_config(config_b)
        result_b = resolve_sentiment_provider(org_id=2, db=db_b)

        assert result_a is not None
        assert result_a.provider == "transformer"
        assert result_b is None

    def test_resolved_sentiment_provider_is_str(self):
        config = _make_config(sentiment_provider="vader")
        db = _make_db_with_config(config)

        result = resolve_sentiment_provider(org_id=1, db=db)

        assert isinstance(result.provider, str)

    def test_valid_sentiment_providers_constant(self):
        assert VALID_SENTIMENT_PROVIDERS == frozenset({"vader", "transformer"})
