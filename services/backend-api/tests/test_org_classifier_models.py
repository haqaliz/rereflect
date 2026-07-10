"""
TDD tests for M5.2 per-org-corrections-classifier — data-layer aspect.

OrgClassifierModel + OrgClassifierEvalRun mirror the proven
ChurnCalibrationModel / ChurnBacktestRun conventions:
  - organization_id NULL = global/base model.
  - Partial-unique "one active per (organization_id, classifier_type)".
  - model_json is JSON, never pickle.
"""

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.organization import Organization


def test_import_from_models_package():
    from src.models import OrgClassifierModel, OrgClassifierEvalRun  # noqa: F401


class TestOrgClassifierModelColumns:
    def test_org_classifier_model_columns(self, db: Session, test_organization: Organization):
        from src.models import OrgClassifierModel

        model = OrgClassifierModel(
            organization_id=test_organization.id,
            classifier_type="sentiment",
            model_json={"vocab": {"good": 0}, "coef": [[0.1, 0.2]], "classes": ["negative", "positive"]},
            label_count=50,
        )
        db.add(model)
        db.commit()
        db.refresh(model)

        for attr in (
            "id",
            "organization_id",
            "classifier_type",
            "model_json",
            "label_count",
            "precision",
            "recall",
            "macro_f1",
            "accuracy",
            "fit_at",
            "is_active",
        ):
            assert hasattr(model, attr), f"OrgClassifierModel missing attr {attr}"

    def test_eval_run_columns(self, db: Session, test_organization: Organization):
        from src.models import OrgClassifierEvalRun

        run = OrgClassifierEvalRun(
            organization_id=test_organization.id,
            classifier_type="sentiment",
            decision="retained",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        for attr in (
            "id",
            "organization_id",
            "classifier_model_id",
            "classifier_type",
            "incumbent_macro_f1",
            "challenger_macro_f1",
            "macro_f1_delta",
            "decision",
            "n",
            "duration_ms",
            "notes",
            "created_at",
        ):
            assert hasattr(run, attr), f"OrgClassifierEvalRun missing attr {attr}"


class TestOrgClassifierModelBehavior:
    def test_organization_id_nullable(self, db: Session):
        """organization_id=None (global/base model) is allowed."""
        from src.models import OrgClassifierModel

        model = OrgClassifierModel(
            organization_id=None,
            classifier_type="sentiment",
            model_json={"vocab": {}, "coef": [[0.0]], "classes": ["negative", "positive"]},
            label_count=100,
        )
        db.add(model)
        db.commit()
        db.refresh(model)

        assert model.id is not None
        assert model.organization_id is None
        assert model.is_active is False  # default

    def test_model_json_roundtrip(self, db: Session, test_organization: Organization):
        """model_json round-trips exactly through the JSON column (proves JSON, not pickle)."""
        from src.models import OrgClassifierModel

        payload = {
            "vocab": {"great": 0, "bad": 1},
            "coef": [[0.5, -0.3], [-0.2, 0.4]],
            "classes": ["negative", "neutral", "positive"],
        }
        model = OrgClassifierModel(
            organization_id=test_organization.id,
            classifier_type="sentiment",
            model_json=payload,
            label_count=10,
        )
        db.add(model)
        db.commit()
        db.refresh(model)

        assert model.model_json == payload

    def test_partial_unique_one_active_per_org_type(self, db: Session, test_organization: Organization):
        """Two is_active=True rows for the same (org, classifier_type) violate the partial-unique index."""
        from src.models import OrgClassifierModel

        m1 = OrgClassifierModel(
            organization_id=test_organization.id,
            classifier_type="sentiment",
            model_json={"v": 1},
            label_count=10,
            is_active=True,
        )
        m2 = OrgClassifierModel(
            organization_id=test_organization.id,
            classifier_type="sentiment",
            model_json={"v": 2},
            label_count=20,
            is_active=True,
        )
        db.add(m1)
        db.commit()
        db.add(m2)

        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_partial_unique_allows_different_type(self, db: Session, test_organization: Organization):
        """Different classifier_type for the same org is allowed even if both are active."""
        from src.models import OrgClassifierModel

        m1 = OrgClassifierModel(
            organization_id=test_organization.id,
            classifier_type="sentiment",
            model_json={"v": 1},
            label_count=10,
            is_active=True,
        )
        m2 = OrgClassifierModel(
            organization_id=test_organization.id,
            classifier_type="category",
            model_json={"v": 2},
            label_count=20,
            is_active=True,
        )
        db.add(m1)
        db.add(m2)
        db.commit()

        assert m1.id is not None
        assert m2.id is not None

    def test_partial_unique_allows_inactive(self, db: Session, test_organization: Organization):
        """Many is_active=False rows for the same (org, classifier_type) are allowed."""
        from src.models import OrgClassifierModel

        rows = [
            OrgClassifierModel(
                organization_id=test_organization.id,
                classifier_type="sentiment",
                model_json={"v": i},
                label_count=10 + i,
                is_active=False,
            )
            for i in range(3)
        ]
        db.add_all(rows)
        db.commit()

        assert all(r.id is not None for r in rows)

    def test_numeric_precision_scale(self, db: Session, test_organization: Organization):
        """macro_f1 rounds to 4 decimal places (Numeric(5, 4))."""
        from src.models import OrgClassifierModel

        model = OrgClassifierModel(
            organization_id=test_organization.id,
            classifier_type="sentiment",
            model_json={"v": 1},
            label_count=10,
            macro_f1=Decimal("0.7134"),
        )
        db.add(model)
        db.commit()
        db.refresh(model)

        assert Decimal(model.macro_f1) == Decimal("0.7134")
