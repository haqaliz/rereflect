"""
Phase 1 RED: Tests for resolve_sentiment_provider (backend-api).

Degrade matrix:
  1. sentiment_provider is None/unset -> None (caller falls back to "vader")
  2. No OrgAIConfig row at all -> None
  3. sentiment_provider = "vader" -> ResolvedSentiment(provider="vader")
  4. sentiment_provider = "transformer" -> ResolvedSentiment(provider="transformer")
  5. Unrecognized value ("nonsense") -> None
  6. db.query raising -> None, never propagates
  7. Cross-org isolation: org A=transformer, org B=unset, independently resolved
  8. ResolvedSentiment.provider is a str
"""

from __future__ import annotations

from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from src.models.organization import Organization
from src.models.org_ai_config import OrgAIConfig
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
        """AC1: sentiment_provider=None -> None."""
        config = _make_config(sentiment_provider=None)
        db = _make_db_with_config(config)

        result = resolve_sentiment_provider(org_id=1, db=db)

        assert result is None

    def test_no_org_ai_config_row_returns_none(self):
        """AC1: no OrgAIConfig row -> None."""
        db = _make_db_without_config()

        result = resolve_sentiment_provider(org_id=999, db=db)

        assert result is None

    def test_explicit_vader_returns_resolved_vader(self):
        """AC2 baseline: explicit 'vader' resolves cleanly."""
        config = _make_config(sentiment_provider="vader")
        db = _make_db_with_config(config)

        result = resolve_sentiment_provider(org_id=1, db=db)

        assert result is not None
        assert isinstance(result, ResolvedSentiment)
        assert result.provider == "vader"

    def test_explicit_transformer_returns_resolved_transformer(self):
        """AC2: explicit 'transformer' resolves."""
        config = _make_config(sentiment_provider="transformer")
        db = _make_db_with_config(config)

        result = resolve_sentiment_provider(org_id=1, db=db)

        assert result is not None
        assert result.provider == "transformer"

    def test_unrecognized_value_returns_none(self):
        """AC3: unrecognized value degrades to None (-> vader at the caller)."""
        config = _make_config(sentiment_provider="nonsense")
        db = _make_db_with_config(config)

        result = resolve_sentiment_provider(org_id=1, db=db)

        assert result is None

    def test_db_query_exception_returns_none(self):
        """AC4: resolver never raises, even on a DB error."""
        db = MagicMock()
        db.query.side_effect = Exception("boom")

        result = resolve_sentiment_provider(org_id=1, db=db)

        assert result is None

    def test_cross_org_isolation(self, db: Session):
        """AC5: org A=transformer, org B=unset, resolved independently, no leakage.

        Uses a REAL DB session (in-memory SQLite, same fixture pattern as
        test_ai_settings_sentiment_provider.py) with two real OrgAIConfig rows
        for two distinct organizations, queried through the SAME session. This
        actually exercises `filter_by(organization_id=...)` scoping — a
        MagicMock hard-wired to always return one config would never catch a
        resolver that forgot to filter by org_id.
        """
        org_a = Organization(name="Org A", plan="pro")
        org_b = Organization(name="Org B", plan="pro")
        db.add(org_a)
        db.add(org_b)
        db.commit()
        db.refresh(org_a)
        db.refresh(org_b)

        config_a = OrgAIConfig(
            organization_id=org_a.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            sentiment_provider="transformer",
        )
        db.add(config_a)
        db.commit()
        # org_b intentionally gets NO OrgAIConfig row at all — the real "unset"
        # case. (Note: passing sentiment_provider=None explicitly would NOT
        # exercise this — the Column(default='vader') fires on INSERT whenever
        # no value is set, including an explicit None, so a config_b row would
        # actually persist as 'vader'.) Only one row exists in the whole table,
        # for org_a — if filter_by(organization_id=...) scoping were broken
        # (e.g. an unscoped `.first()`), resolving org_b would wrongly return
        # org_a's 'transformer' config instead of None.

        # Resolve both against the SAME session — proves filter_by(organization_id=...)
        # scoping, not just "different fixtures produce different results".
        result_a = resolve_sentiment_provider(org_id=org_a.id, db=db)
        result_b = resolve_sentiment_provider(org_id=org_b.id, db=db)

        assert result_a is not None
        assert result_a.provider == "transformer"
        assert result_b is None

    def test_resolved_sentiment_provider_is_str(self):
        """Shape check: ResolvedSentiment.provider is a plain string."""
        config = _make_config(sentiment_provider="vader")
        db = _make_db_with_config(config)

        result = resolve_sentiment_provider(org_id=1, db=db)

        assert isinstance(result.provider, str)

    def test_valid_sentiment_providers_constant(self):
        """VALID_SENTIMENT_PROVIDERS is exactly {'vader', 'transformer'}."""
        assert VALID_SENTIMENT_PROVIDERS == frozenset({"vader", "transformer"})
