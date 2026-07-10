"""
Phase 2 RED: Tests for load_active_classifier — 3-tier fallback + corrupt-
artifact defense + per-org cache (backend-api).

Mirrors probability_updater._load_active_model / _deserialize_model
defensiveness (worker-service), adapted for OrgClassifierModel
(M5.2 predict-seam-resolver). Aspect B's predict()/score_from_proba() are NOT
exercised here (Phase 3) — this phase only covers the load/cache/deserialize
seam.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.models.organization import Organization
from src.models.org_classifier import OrgClassifierModel
from src.services.classifier_predict import (
    LoadedClassifier,
    load_active_classifier,
    _classifier_cache,
    _deserialize,
)


VALID_ARTIFACT = {
    "vectorizer": {
        "vocabulary": {"good": 0, "bad": 1},
        "idf": [1.0, 1.2],
        "token_pattern": r"(?u)\b\w\w+\b",
        "lowercase": True,
        "sublinear_tf": True,
        "norm": "l2",
    },
    "logreg": {"coef": [[0.5, -0.5]], "intercept": [0.0]},
    "classes": ["negative", "positive"],
}


@pytest.fixture(autouse=True)
def _reset_classifier_cache():
    _classifier_cache.clear()
    yield
    _classifier_cache.clear()


def _make_org(db, name="Org") -> Organization:
    org = Organization(name=name, plan="pro")
    db.add(org)
    db.commit()
    db.refresh(org)
    return org


def _make_model(
    db,
    *,
    organization_id=None,
    classifier_type="sentiment",
    model_json=None,
    is_active=True,
    fit_at=None,
) -> OrgClassifierModel:
    row = OrgClassifierModel(
        organization_id=organization_id,
        classifier_type=classifier_type,
        model_json=model_json if model_json is not None else VALID_ARTIFACT,
        label_count=10,
        fit_at=fit_at or datetime.utcnow(),
        is_active=is_active,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestThreeTierFallback:
    def test_org_active_row_loaded(self, db):
        org = _make_org(db)
        row = _make_model(db, organization_id=org.id)

        loaded = load_active_classifier(org.id, "sentiment", db)

        assert loaded is not None
        assert isinstance(loaded, LoadedClassifier)
        assert loaded.model_id == row.id

    def test_no_org_active_falls_back_to_global(self, db):
        org = _make_org(db)
        global_row = _make_model(db, organization_id=None)

        loaded = load_active_classifier(org.id, "sentiment", db)

        assert loaded is not None
        assert loaded.model_id == global_row.id

    def test_neither_returns_none_incumbent(self, db):
        org = _make_org(db)

        loaded = load_active_classifier(org.id, "sentiment", db)

        assert loaded is None

    def test_inactive_org_row_ignored_falls_back_to_global(self, db):
        org = _make_org(db)
        _make_model(db, organization_id=org.id, is_active=False)
        global_row = _make_model(db, organization_id=None)

        loaded = load_active_classifier(org.id, "sentiment", db)

        assert loaded is not None
        assert loaded.model_id == global_row.id


class TestCorruptArtifactDefense:
    def test_model_json_not_a_dict(self, db):
        org = _make_org(db)
        _make_model(db, organization_id=org.id, model_json="not-a-dict")

        loaded = load_active_classifier(org.id, "sentiment", db)

        assert loaded is None

    def test_empty_vocabulary(self, db):
        org = _make_org(db)
        bad_artifact = {
            "vectorizer": {**VALID_ARTIFACT["vectorizer"], "vocabulary": {}},
            "logreg": VALID_ARTIFACT["logreg"],
            "classes": VALID_ARTIFACT["classes"],
        }
        _make_model(db, organization_id=org.id, model_json=bad_artifact)

        loaded = load_active_classifier(org.id, "sentiment", db)

        assert loaded is None

    def test_bad_shape_missing_logreg(self, db):
        org = _make_org(db)
        bad_artifact = {
            "vectorizer": VALID_ARTIFACT["vectorizer"],
            "classes": VALID_ARTIFACT["classes"],
        }
        _make_model(db, organization_id=org.id, model_json=bad_artifact)

        loaded = load_active_classifier(org.id, "sentiment", db)

        assert loaded is None

    def test_never_raises_on_corrupt_artifact(self, db):
        org = _make_org(db)
        bad_artifact = {"vectorizer": None, "logreg": None, "classes": None}
        _make_model(db, organization_id=org.id, model_json=bad_artifact)

        # Should not raise.
        loaded = load_active_classifier(org.id, "sentiment", db)
        assert loaded is None

    def test_db_error_never_raises(self, db):
        org = _make_org(db)
        _make_model(db, organization_id=org.id)

        with patch("src.services.classifier_predict._deserialize", side_effect=Exception("boom")):
            loaded = load_active_classifier(org.id, "sentiment", db)

        assert loaded is None


class TestPerOrgCache:
    def test_cache_hit_skips_deserialize(self, db):
        org = _make_org(db)
        _make_model(db, organization_id=org.id)

        with patch(
            "src.services.classifier_predict._deserialize", wraps=_deserialize
        ) as spy_deserialize:
            first = load_active_classifier(org.id, "sentiment", db)
            second = load_active_classifier(org.id, "sentiment", db)

        assert first is not None
        assert second is not None
        assert first.model_id == second.model_id
        assert spy_deserialize.call_count == 1

    def test_cache_invalidation_after_promotion(self, db):
        org = _make_org(db)
        old_row = _make_model(
            db, organization_id=org.id, fit_at=datetime.utcnow() - timedelta(days=1)
        )

        first = load_active_classifier(org.id, "sentiment", db)
        assert first.model_id == old_row.id

        # Promote a newer model: flip old inactive, insert+activate new.
        old_row.is_active = False
        db.add(old_row)
        db.commit()
        new_row = _make_model(db, organization_id=org.id, fit_at=datetime.utcnow())

        second = load_active_classifier(org.id, "sentiment", db)

        assert second is not None
        assert second.model_id == new_row.id
        assert second.model_id != first.model_id

    def test_per_org_key_isolation(self, db):
        org_a = _make_org(db, name="Org A")
        org_b = _make_org(db, name="Org B")
        row_a = _make_model(db, organization_id=org_a.id)
        row_b = _make_model(db, organization_id=org_b.id)

        loaded_a = load_active_classifier(org_a.id, "sentiment", db)
        loaded_b = load_active_classifier(org_b.id, "sentiment", db)

        assert loaded_a.model_id == row_a.id
        assert loaded_b.model_id == row_b.id
        assert loaded_a.model_id != loaded_b.model_id
