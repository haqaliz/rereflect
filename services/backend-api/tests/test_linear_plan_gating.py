"""
TDD tests for Linear integration plan gating.

Covers:
1. plans.py — linear_integration feature present in Pro, Business, Enterprise; absent in Free
2. FEATURE_PLANS — linear_integration maps to "pro"
3. has_feature() helper for each plan tier
4. require_feature("linear_integration") dependency returns 403 for Free, passes for Pro+
"""
import pytest
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from src.models.organization import Organization
from src.models.user import User
from src.api.auth import hash_password, create_access_token


# ---------------------------------------------------------------------------
# 1. plans.py feature presence
# ---------------------------------------------------------------------------
class TestLinearFeatureInPlans:

    def test_linear_integration_not_in_free(self):
        from src.config.plans import PLANS
        assert "linear_integration" not in PLANS["free"]["features"]

    def test_linear_integration_in_pro(self):
        from src.config.plans import PLANS
        assert "linear_integration" in PLANS["pro"]["features"]

    def test_linear_integration_in_business(self):
        from src.config.plans import PLANS
        assert "linear_integration" in PLANS["business"]["features"]

    def test_linear_integration_in_enterprise(self):
        from src.config.plans import PLANS
        assert "linear_integration" in PLANS["enterprise"]["features"]


# ---------------------------------------------------------------------------
# 2. FEATURE_PLANS mapping
# ---------------------------------------------------------------------------
class TestLinearFeaturePlanMapping:

    def test_linear_integration_maps_to_pro(self):
        from src.config.plans import FEATURE_PLANS
        assert FEATURE_PLANS.get("linear_integration") == "pro"

    def test_get_plan_for_feature_returns_pro(self):
        from src.config.plans import get_plan_for_feature
        assert get_plan_for_feature("linear_integration") == "pro"


# ---------------------------------------------------------------------------
# 3. has_feature() for each plan
# ---------------------------------------------------------------------------
class TestLinearHasFeature:

    def test_free_plan_does_not_have_linear(self):
        from src.config.plans import has_feature
        assert has_feature("free", "linear_integration") is False

    def test_pro_plan_has_linear(self):
        from src.config.plans import has_feature
        assert has_feature("pro", "linear_integration") is True

    def test_business_plan_has_linear(self):
        from src.config.plans import has_feature
        assert has_feature("business", "linear_integration") is True

    def test_enterprise_plan_has_linear(self):
        from src.config.plans import has_feature
        assert has_feature("enterprise", "linear_integration") is True


# ---------------------------------------------------------------------------
# 4. require_feature("linear_integration") dependency — unit tests
# ---------------------------------------------------------------------------
class TestRequireLinearFeatureDependency:
    """Test the require_feature dependency raises HTTPException for Free, passes for Pro+."""

    def _make_org(self, db: Session, plan: str) -> Organization:
        org = Organization(name=f"Test Org ({plan})", plan=plan)
        db.add(org)
        db.commit()
        db.refresh(org)
        return org

    def test_free_plan_raises_403(self, db: Session):
        """require_feature raises HTTPException for free plan."""
        from fastapi import HTTPException
        from src.api.dependencies import require_feature

        org = self._make_org(db, "free")
        dep = require_feature("linear_integration")

        with pytest.raises(HTTPException) as exc_info:
            dep(current_org=org)

        assert exc_info.value.status_code == 403
        detail = exc_info.value.detail
        assert detail["error"] == "feature_not_available"
        assert detail["feature"] == "linear_integration"
        assert detail["required_plan"] == "pro"
        assert "upgrade_url" in detail

    def test_pro_plan_does_not_raise(self, db: Session):
        """require_feature does not raise for pro plan."""
        from src.api.dependencies import require_feature

        org = self._make_org(db, "pro")
        dep = require_feature("linear_integration")
        result = dep(current_org=org)
        assert result is True

    def test_business_plan_does_not_raise(self, db: Session):
        """require_feature does not raise for business plan."""
        from src.api.dependencies import require_feature

        org = self._make_org(db, "business")
        dep = require_feature("linear_integration")
        result = dep(current_org=org)
        assert result is True

    def test_enterprise_plan_does_not_raise(self, db: Session):
        """require_feature does not raise for enterprise plan."""
        from src.api.dependencies import require_feature

        org = self._make_org(db, "enterprise")
        dep = require_feature("linear_integration")
        result = dep(current_org=org)
        assert result is True

    def test_403_detail_includes_upgrade_url(self, db: Session):
        """403 detail includes upgrade_url."""
        from fastapi import HTTPException
        from src.api.dependencies import require_feature

        org = self._make_org(db, "free")
        dep = require_feature("linear_integration")

        with pytest.raises(HTTPException) as exc_info:
            dep(current_org=org)

        assert exc_info.value.detail["upgrade_url"] == "/settings/billing"
