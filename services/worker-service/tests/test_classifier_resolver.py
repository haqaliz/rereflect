"""
Phase 1 RED: Tests for resolve_classifier (worker-service mirror).

Same degrade matrix as backend-api's test_classifier_resolver.py, against the
worker's independent mirror resolver (reads the worker's own OrgAIConfig ORM
mirror, no cross-service import).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.models import Organization, OrgAIConfig
from src.services.classifier_resolver import (
    resolve_classifier,
    ResolvedClassifier,
    VALID_CLASSIFIER_MODES,
)


def _make_config(classifier_mode=None, category_classifier_mode=None) -> MagicMock:
    cfg = MagicMock()
    cfg.classifier_mode = classifier_mode
    cfg.category_classifier_mode = category_classifier_mode
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


class TestResolveClassifier:
    def test_off_returns_none(self):
        config = _make_config(classifier_mode="off")
        db = _make_db_with_config(config)

        result = resolve_classifier(org_id=1, classifier_type="sentiment", db=db)

        assert result is None

    def test_no_org_ai_config_row_returns_none(self):
        db = _make_db_without_config()

        result = resolve_classifier(org_id=999, classifier_type="sentiment", db=db)

        assert result is None

    def test_shadow_returns_resolved_shadow(self):
        config = _make_config(classifier_mode="shadow")
        db = _make_db_with_config(config)

        result = resolve_classifier(org_id=1, classifier_type="sentiment", db=db)

        assert result is not None
        assert isinstance(result, ResolvedClassifier)
        assert result.mode == "shadow"

    def test_auto_returns_resolved_auto(self):
        config = _make_config(classifier_mode="auto")
        db = _make_db_with_config(config)

        result = resolve_classifier(org_id=1, classifier_type="sentiment", db=db)

        assert result is not None
        assert result.mode == "auto"

    def test_unrecognized_value_returns_none(self):
        config = _make_config(classifier_mode="nonsense")
        db = _make_db_with_config(config)

        result = resolve_classifier(org_id=1, classifier_type="sentiment", db=db)

        assert result is None

    def test_unset_column_returns_none(self):
        config = _make_config(classifier_mode=None)
        db = _make_db_with_config(config)

        result = resolve_classifier(org_id=1, classifier_type="sentiment", db=db)

        assert result is None

    def test_missing_classifier_mode_column_returns_none(self):
        """Un-migrated-DB case: the ORM row has no classifier_mode attribute at
        all (getattr default fires, never raises)."""
        config = MagicMock(spec=[])
        db = _make_db_with_config(config)

        result = resolve_classifier(org_id=1, classifier_type="sentiment", db=db)

        assert result is None

    def test_db_query_exception_returns_none(self):
        db = MagicMock()
        db.query.side_effect = Exception("boom")

        result = resolve_classifier(org_id=1, classifier_type="sentiment", db=db)

        assert result is None

    def test_cross_org_isolation(self, db):
        """Real DB session, two orgs, only org_a has a row -> no leakage."""
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
            classifier_mode="auto",
        )
        db.add(config_a)
        db.commit()
        # org_b intentionally gets no OrgAIConfig row.

        result_a = resolve_classifier(org_id=org_a.id, classifier_type="sentiment", db=db)
        result_b = resolve_classifier(org_id=org_b.id, classifier_type="sentiment", db=db)

        assert result_a is not None
        assert result_a.mode == "auto"
        assert result_b is None

    def test_valid_classifier_modes_constant(self):
        assert VALID_CLASSIFIER_MODES == frozenset({"shadow", "auto"})


class TestPerTypeModeColumn:
    def test_category_reads_category_column_independent_of_sentiment(self):
        config = _make_config(classifier_mode="shadow", category_classifier_mode="auto")
        db = _make_db_with_config(config)

        result = resolve_classifier(org_id=1, classifier_type="category", db=db)

        assert result is not None
        assert result.mode == "auto"

    def test_sentiment_reads_sentiment_column_independent_of_category(self):
        config = _make_config(classifier_mode="auto", category_classifier_mode="shadow")
        db = _make_db_with_config(config)

        result = resolve_classifier(org_id=1, classifier_type="sentiment", db=db)

        assert result is not None
        assert result.mode == "auto"

    def test_category_off_returns_none(self):
        config = _make_config(category_classifier_mode="off")
        db = _make_db_with_config(config)

        assert resolve_classifier(org_id=1, classifier_type="category", db=db) is None

    def test_category_unset_column_returns_none(self):
        config = _make_config()  # both None
        db = _make_db_with_config(config)

        assert resolve_classifier(org_id=1, classifier_type="category", db=db) is None

    def test_category_unrecognized_value_returns_none(self):
        config = _make_config(category_classifier_mode="nonsense")
        db = _make_db_with_config(config)

        assert resolve_classifier(org_id=1, classifier_type="category", db=db) is None

    def test_missing_category_classifier_mode_column_returns_none(self):
        """Un-migrated-DB case: ORM row has no category_classifier_mode
        attribute at all (getattr default fires, never raises)."""
        config = MagicMock(spec=[])
        db = _make_db_with_config(config)

        assert resolve_classifier(org_id=1, classifier_type="category", db=db) is None

    def test_unrecognized_classifier_type_returns_none(self):
        config = _make_config(classifier_mode="auto", category_classifier_mode="auto")
        db = _make_db_with_config(config)

        assert resolve_classifier(org_id=1, classifier_type="urgency", db=db) is None

    def test_mode_column_by_classifier_type_constant(self):
        from src.services.classifier_resolver import MODE_COLUMN_BY_CLASSIFIER_TYPE

        assert MODE_COLUMN_BY_CLASSIFIER_TYPE == {
            "sentiment": "classifier_mode",
            "category": "category_classifier_mode",
        }

    def test_cross_type_isolation_same_org(self, db):
        """Same org, sentiment=auto + category=off -> only sentiment resolves."""
        org = Organization(name="Org C", plan="pro")
        db.add(org)
        db.commit()
        db.refresh(org)

        config = OrgAIConfig(
            organization_id=org.id,
            default_provider="openai",
            model_categorization="gpt-4o-mini",
            model_analysis="gpt-4o-mini",
            model_insights="gpt-4o-mini",
            classifier_mode="auto",
            category_classifier_mode="off",
        )
        db.add(config)
        db.commit()

        sentiment_result = resolve_classifier(org_id=org.id, classifier_type="sentiment", db=db)
        category_result = resolve_classifier(org_id=org.id, classifier_type="category", db=db)

        assert sentiment_result is not None and sentiment_result.mode == "auto"
        assert category_result is None
