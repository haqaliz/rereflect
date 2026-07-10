"""
Per-org corrections-classifier loader + predict + override helper —
backend-api (M5.2 predict-seam-resolver).

Independent mirror of services/worker-service/src/services/classifier_predict.py.
No cross-service import: this reads the backend's own OrgClassifierModel /
FeedbackItem ORM models (src/models/). The two copies are byte-identical
except for import lines, docstring header, and the `allow_override` value
each call-site passes in — see test_classifier_predict_mirror.py.

Three responsibilities, mirroring existing precedents:
  1. `load_active_classifier` — 3-tier fallback (org active -> global active
     -> None/incumbent) + corrupt-artifact defense, mirroring
     probability_updater._load_active_model / _deserialize_model
     (worker-service).
  2. `LoadedClassifier.predict` — thin wrapper around aspect B's pure
     `predict()` + `score_from_proba()` (analysis-engine's
     corrections_classifier package), imported lazily so this module stays
     importable in ML-wheel-less environments.
  3. `apply_classifier_override` — the single off/shadow/auto branching
     helper invoked from both sentiment call-sites (worker
     tasks/analysis.py, backend routes/feedback.py), mirroring
     resolve_sentiment_provider's never-raises posture. The ONLY difference
     between the two services' copies is which value each call-site passes
     for `allow_override` (worker: True/authoritative auto; backend inline:
     False/shadow-only even in auto mode).

Per-org cache: module-level dict keyed (org_id, classifier_type) ->
(model_id, fit_at, LoadedClassifier). A cheap active-pointer query (id,
fit_at only) decides hit vs miss; a newer active fit_at/id invalidates and
rebuilds (skips the deserialize step on a cache hit — see
test_classifier_predict_loader.py::TestPerOrgCache).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Dedicated structured logger for shadow-mode predictions (per-item, NOT a DB
# write — see tech-plan locked decision #1). caplog-testable by name.
shadow_logger = logging.getLogger("rereflect.classifier.shadow")

# Module-level per-org cache: (org_id, classifier_type) -> (model_id, fit_at, LoadedClassifier)
_classifier_cache: dict = {}


@dataclass
class LoadedClassifier:
    """A deserialized, ready-to-predict per-org classifier artifact.

    Attributes:
        model_id: OrgClassifierModel.id this artifact was loaded from.
        fit_at: OrgClassifierModel.fit_at, used as the cache invalidation key
            alongside model_id.
        artifact: The raw model_json dict (TF-IDF vocab/idf + logreg
            coef/intercept + classes), handed as-is to aspect B's predict().
    """

    model_id: Optional[int]
    fit_at: Optional[datetime]
    artifact: dict

    def predict(self, text: str) -> tuple[str, float]:
        """Predict (label, score) for `text` via aspect B's pure predict().

        score = score_from_proba(proba) = clamp(P(positive) - P(negative), -1, 1).
        Lazy import so importing this module never requires the
        analysis-engine's corrections_classifier package (or its stdlib-only
        predict.py) to be installed/importable until actually predicting.
        """
        from analyzer.corrections_classifier.predict import predict as _predict, score_from_proba

        label, proba = _predict(self.artifact, text)
        score = score_from_proba(proba)
        return label, score


def _deserialize(db_row) -> Optional[LoadedClassifier]:
    """Deserialize an OrgClassifierModel row's model_json into a LoadedClassifier.

    Falls back to None (incumbent) on any structural defect — mirrors
    probability_updater._deserialize_model's defensiveness (worker-service).
    Never raises.
    """
    try:
        mj = db_row.model_json
        if not isinstance(mj, dict):
            raise ValueError("model_json is not a dict")

        vectorizer = mj.get("vectorizer")
        logreg = mj.get("logreg")
        classes = mj.get("classes")

        if not isinstance(vectorizer, dict) or not isinstance(logreg, dict) or not isinstance(classes, list):
            raise ValueError("model_json missing vectorizer/logreg/classes")

        vocabulary = vectorizer.get("vocabulary")
        if not vocabulary:
            raise ValueError("empty vocabulary")

        coef = logreg.get("coef")
        intercept = logreg.get("intercept")
        if not coef or not intercept:
            raise ValueError("empty coef/intercept")

        if len(coef) != len(intercept):
            raise ValueError("coef/intercept shape mismatch")

        return LoadedClassifier(model_id=db_row.id, fit_at=db_row.fit_at, artifact=mj)
    except Exception as exc:
        logger.warning(
            "Corrupted model_json for OrgClassifierModel id=%s: %s. "
            "Falling back to incumbent.",
            getattr(db_row, "id", None), exc,
        )
        return None


def load_active_classifier(org_id: int, classifier_type: str, db) -> Optional[LoadedClassifier]:
    """Load the active classifier for (org_id, classifier_type). 3-tier fallback.

    1. Org-specific active OrgClassifierModel row.
    2. Global active row (organization_id IS NULL).
    3. None -> caller keeps the incumbent (analyzer) value.

    Corrupt/unparseable model_json degrades to None (never raises). Cache
    key is per-org (not provider-name-only): a per-org active-pointer query
    (id, fit_at only — cheap, uses the partial-unique index) decides cache
    hit vs miss, skipping the (comparatively expensive) deserialize step on
    a hit. A newer active fit_at/id invalidates and rebuilds.
    """
    try:
        from src.models.org_classifier import OrgClassifierModel

        pointer = (
            db.query(OrgClassifierModel.id, OrgClassifierModel.fit_at)
            .filter(
                OrgClassifierModel.organization_id == org_id,
                OrgClassifierModel.classifier_type == classifier_type,
                OrgClassifierModel.is_active == True,  # noqa: E712
            )
            .first()
        )

        if pointer is None:
            pointer = (
                db.query(OrgClassifierModel.id, OrgClassifierModel.fit_at)
                .filter(
                    OrgClassifierModel.organization_id.is_(None),
                    OrgClassifierModel.classifier_type == classifier_type,
                    OrgClassifierModel.is_active == True,  # noqa: E712
                )
                .first()
            )

        if pointer is None:
            return None  # No active model anywhere -> incumbent.

        model_id, fit_at = pointer
        cache_key = (org_id, classifier_type)
        cached = _classifier_cache.get(cache_key)
        if cached is not None and cached[0] == model_id and cached[1] == fit_at:
            return cached[2]

        db_row = db.query(OrgClassifierModel).filter(OrgClassifierModel.id == model_id).first()
        if db_row is None:
            return None

        loaded = _deserialize(db_row)
        if loaded is None:
            return None

        _classifier_cache[cache_key] = (model_id, fit_at, loaded)
        return loaded

    except Exception as exc:
        logger.warning(
            "load_active_classifier: failed for org=%s classifier_type=%s: %s",
            org_id, classifier_type, exc, exc_info=True,
        )
        return None
