"""
TDD tests for M5.2 per-org-corrections-classifier — worker mirror aspect.

Adds the currently-missing `AICorrection` mirror (table `ai_corrections`),
lightweight `OrgClassifierModel` + `OrgClassifierEvalRun` mirrors (worker is
the sole writer of org_classifier_models — trainer, aspect C — so the
mirror KEEPS the partial-unique index, unlike the read-only
ChurnCalibrationModel mirror), and `OrgAIConfig.classifier_mode`.
"""

from datetime import datetime

from sqlalchemy import inspect


def test_import_aicorrection():
    from src.models import AICorrection

    instance = AICorrection(
        organization_id=1,
        correction_type="sentiment",
        entity_type="feedback_item",
        signal="correction",
        corrected_value="negative",
    )
    for attr in (
        "id",
        "organization_id",
        "user_id",
        "correction_type",
        "entity_type",
        "entity_id",
        "signal",
        "original_value",
        "corrected_value",
        "feedback_text",
        "created_at",
    ):
        assert hasattr(instance, attr), f"AICorrection missing attr {attr}"


def test_import_new_models():
    from src.models import OrgClassifierModel, OrgClassifierEvalRun  # noqa: F401


def test_worker_orgaiconfig_has_classifier_mode():
    from src.models import OrgAIConfig

    assert hasattr(OrgAIConfig(), "classifier_mode")


def test_query_ai_corrections_roundtrip(db, test_org):
    """Proves the trainer (aspect C) can read ai_corrections in the shared DB."""
    from src.models import AICorrection

    correction = AICorrection(
        organization_id=test_org.id,
        correction_type="sentiment",
        entity_type="feedback_item",
        entity_id=42,
        signal="correction",
        original_value="positive",
        corrected_value="negative",
        created_at=datetime.utcnow(),
    )
    db.add(correction)
    db.commit()
    db.refresh(correction)

    fetched = (
        db.query(AICorrection)
        .filter(AICorrection.organization_id == test_org.id)
        .filter(AICorrection.correction_type == "sentiment")
        .first()
    )
    assert fetched is not None
    assert fetched.corrected_value == "negative"


def test_partial_unique_mirror_present():
    """
    The worker is the sole writer of org_classifier_models (trainer, aspect C),
    so — unlike the read-only ChurnCalibrationModel mirror — the worker mirror
    MUST keep the partial-unique index so the DB-level guard holds on insert.
    """
    from src.models import OrgClassifierModel

    idx_names = {idx.name for idx in OrgClassifierModel.__table__.indexes}
    assert "uq_org_classifier_one_active" in idx_names, idx_names
