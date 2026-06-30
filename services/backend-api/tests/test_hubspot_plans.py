"""
Tests for HubSpot feature registration in plans.py (Phase 1).
"""
from unittest.mock import patch
import os
from src.config.plans import has_feature, get_plan_for_feature, PLANS, FEATURE_PLANS


class TestHubSpotFeatureRegistration:
    def test_hubspot_integration_in_feature_plans(self):
        assert "hubspot_integration" in FEATURE_PLANS

    def test_hubspot_integration_min_plan_is_free(self):
        # Self-hosted: should map to "free" so every org passes
        assert FEATURE_PLANS["hubspot_integration"] == "free"

    def test_hubspot_integration_in_all_plan_feature_lists(self):
        for plan_id in ("free", "pro", "business", "enterprise"):
            assert "hubspot_integration" in PLANS[plan_id]["features"], (
                f"hubspot_integration missing from {plan_id} plan features"
            )

    def test_hubspot_integration_unlocked_self_hosted(self):
        with patch.dict(os.environ, {"SELF_HOSTED": "true"}):
            assert has_feature("free", "hubspot_integration") is True

    def test_hubspot_integration_unlocked_self_hosted_all_plans(self):
        with patch.dict(os.environ, {"SELF_HOSTED": "true"}):
            for plan_id in ("free", "pro", "business", "enterprise"):
                assert has_feature(plan_id, "hubspot_integration") is True

    def test_hubspot_integration_gated_non_self_hosted(self):
        # When SELF_HOSTED=false, feature must appear in the plan's list to pass
        with patch.dict(os.environ, {"SELF_HOSTED": "false"}):
            assert has_feature("free", "hubspot_integration") is True
