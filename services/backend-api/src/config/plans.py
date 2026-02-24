"""
Pricing plan configuration for Rereflect.

Tiers:
- Free: $0, 250 feedback/mo, 2 seats
- Pro: $29/mo, 2,500 feedback/mo, 10 seats
- Business: $99/mo, 25,000 feedback/mo, 25 seats
- Enterprise: Contact sales, unlimited
"""
import os
from typing import Optional


# Stripe Price IDs (set via environment variables)
STRIPE_PRICE_PRO_MONTHLY = os.environ.get("STRIPE_PRICE_PRO_MONTHLY", "")
STRIPE_PRICE_PRO_ANNUAL = os.environ.get("STRIPE_PRICE_PRO_ANNUAL", "")
STRIPE_PRICE_BUSINESS_MONTHLY = os.environ.get("STRIPE_PRICE_BUSINESS_MONTHLY", "")
STRIPE_PRICE_BUSINESS_ANNUAL = os.environ.get("STRIPE_PRICE_BUSINESS_ANNUAL", "")
STRIPE_PRICE_ENTERPRISE_USAGE = os.environ.get("STRIPE_PRICE_ENTERPRISE_USAGE", "")
STRIPE_PRICE_RETENTION_ADDON = os.environ.get("STRIPE_PRICE_RETENTION_ADDON", "")


PLANS = {
    "free": {
        "id": "free",
        "name": "Free",
        "price_monthly": 0,  # cents
        "price_annual": 0,
        "feedback_limit": 250,
        "seat_limit": 2,
        "saved_views_limit": 5,
        "data_retention_days": 30,
        "features": [
            "basic_dashboard",
            "csv_import",
            "sentiment_analysis",
            "email_support",
            # Copilot: free users get basic access (no folders, no analysis)
        ],
        "stripe_price_monthly": None,
        "stripe_price_annual": None,
        "overage_enabled": False,
        "overage_price_cents": None,
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "price_monthly": 2900,  # $29
        "price_annual": 29000,  # $290 (17% off = ~$24/mo)
        "feedback_limit": 2500,
        "seat_limit": 10,
        "saved_views_limit": 15,
        "data_retention_days": 365,
        "features": [
            "basic_dashboard",
            "csv_import",
            "sentiment_analysis",
            "slack_integration",
            "intercom_integration",
            "email_integration",
            "webhooks",
            "data_export",
            "trends_analytics",
            "saved_views",
            "pdf_export",
            "dashboard_sharing",
            "priority_support",
            "enhanced_churn_prediction",
            "customer_health_scores",
            "churn_llm_insights",
            "multi_model_support",
            "byok_keys",
            "ai_usage_dashboard",
            # Copilot M2.2
            "conversation_folders",
            "copilot_analysis_queries",
            "copilot_dynamic_suggestions",
        ],
        "stripe_price_monthly": STRIPE_PRICE_PRO_MONTHLY,
        "stripe_price_annual": STRIPE_PRICE_PRO_ANNUAL,
        "overage_enabled": True,
        "overage_price_cents": 2,  # $0.02 per feedback
    },
    "business": {
        "id": "business",
        "name": "Business",
        "price_monthly": 9900,  # $99
        "price_annual": 99000,  # $990 (17% off = ~$82/mo)
        "feedback_limit": 25000,
        "seat_limit": 25,
        "saved_views_limit": None,  # Unlimited
        "data_retention_days": 730,  # 2 years
        "features": [
            "basic_dashboard",
            "csv_import",
            "sentiment_analysis",
            "slack_integration",
            "intercom_integration",
            "email_integration",
            "webhooks",
            "data_export",
            "trends_analytics",
            "saved_views",
            "pdf_export",
            "dashboard_sharing",
            "api_access",
            "advanced_analytics",
            "custom_categories",
            "dedicated_support",
            "enhanced_churn_prediction",
            "customer_health_scores",
            "churn_llm_insights",
            "ai_analysis_actions",
            "multi_model_support",
            "byok_keys",
            "ai_usage_dashboard",
            # Copilot M2.2
            "conversation_folders",
            "copilot_analysis_queries",
            "copilot_dynamic_suggestions",
            "copilot_entity_scopes",
            "copilot_query_templates_admin",
        ],
        "stripe_price_monthly": STRIPE_PRICE_BUSINESS_MONTHLY,
        "stripe_price_annual": STRIPE_PRICE_BUSINESS_ANNUAL,
        "overage_enabled": True,
        "overage_price_cents": 1,  # $0.01 per feedback
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise",
        "price_monthly": None,  # Contact sales (custom base fee)
        "price_annual": None,
        "feedback_limit": None,  # No hard limit - pay as you go
        "seat_limit": None,  # Unlimited
        "saved_views_limit": None,  # Unlimited
        "data_retention_days": None,  # Custom
        "features": [
            "basic_dashboard",
            "csv_import",
            "sentiment_analysis",
            "slack_integration",
            "intercom_integration",
            "email_integration",
            "webhooks",
            "data_export",
            "trends_analytics",
            "saved_views",
            "pdf_export",
            "dashboard_sharing",
            "api_access",
            "advanced_analytics",
            "custom_categories",
            "sso_saml",
            "custom_integrations",
            "sla",
            "dedicated_csm",
            "audit_logs",
            "custom_retention",
            "enhanced_churn_prediction",
            "customer_health_scores",
            "churn_llm_insights",
            "ai_analysis_actions",
            "multi_model_support",
            "byok_keys",
            "ai_usage_dashboard",
        ],
        "stripe_price_monthly": None,  # Custom base fee negotiated per customer
        "stripe_price_annual": None,
        "stripe_price_usage": STRIPE_PRICE_ENTERPRISE_USAGE,  # Metered usage price
        "overage_enabled": True,  # Track all usage for billing
        "overage_price_cents": 1,  # $0.01 per feedback
    },
}

# Plan hierarchy for comparison
PLAN_HIERARCHY = ["free", "pro", "business", "enterprise"]

# Feature to minimum plan mapping
FEATURE_PLANS = {
    "basic_dashboard": "free",
    "csv_import": "free",
    "sentiment_analysis": "free",
    "email_support": "free",
    "slack_integration": "pro",
    "intercom_integration": "pro",
    "email_integration": "pro",
    "webhooks": "pro",
    "data_export": "pro",
    "trends_analytics": "pro",
    "saved_views": "pro",
    "pdf_export": "pro",
    "dashboard_sharing": "pro",
    "priority_support": "pro",
    "api_access": "business",
    "advanced_analytics": "business",
    "custom_categories": "business",
    "dedicated_support": "business",
    "sso_saml": "enterprise",
    "custom_integrations": "enterprise",
    "sla": "enterprise",
    "dedicated_csm": "enterprise",
    "audit_logs": "enterprise",
    "custom_retention": "enterprise",
    "enhanced_churn_prediction": "pro",
    "customer_health_scores": "pro",
    "churn_llm_insights": "pro",
    "ai_analysis_actions": "business",
    "multi_model_support": "pro",
    "byok_keys": "pro",
    "ai_usage_dashboard": "pro",
    # AI Copilot features (M2.2)
    "conversation_folders": "pro",
    "copilot_analysis_queries": "pro",
    "copilot_dynamic_suggestions": "pro",
    "copilot_entity_scopes": "business",
    "copilot_query_templates_admin": "business",
    "copilot_audit_trail": "enterprise",
}


def get_plan(plan_id: str) -> dict:
    """Get plan configuration by ID."""
    return PLANS.get(plan_id, PLANS["free"])


def get_plan_for_feature(feature: str) -> str:
    """Get the minimum plan required for a feature."""
    return FEATURE_PLANS.get(feature, "enterprise")


def has_feature(plan_id: str, feature: str) -> bool:
    """Check if a plan has access to a feature."""
    plan = get_plan(plan_id)
    return feature in plan.get("features", [])


def plan_includes(current_plan: str, required_plan: str) -> bool:
    """Check if current plan includes/exceeds the required plan level."""
    try:
        current_idx = PLAN_HIERARCHY.index(current_plan)
        required_idx = PLAN_HIERARCHY.index(required_plan)
        return current_idx >= required_idx
    except ValueError:
        return False


def get_feedback_limit(plan_id: str) -> Optional[int]:
    """Get feedback limit for a plan. None means unlimited."""
    plan = get_plan(plan_id)
    return plan.get("feedback_limit")


def get_seat_limit(plan_id: str) -> Optional[int]:
    """Get seat limit for a plan. None means unlimited."""
    plan = get_plan(plan_id)
    return plan.get("seat_limit")


def get_saved_views_limit(plan_id: str) -> Optional[int]:
    """Get saved views limit for a plan. None means unlimited."""
    plan = get_plan(plan_id)
    return plan.get("saved_views_limit")


def get_stripe_price_id(plan_id: str, billing_cycle: str) -> Optional[str]:
    """Get Stripe price ID for a plan and billing cycle."""
    plan = get_plan(plan_id)
    if billing_cycle == "annual":
        return plan.get("stripe_price_annual")
    return plan.get("stripe_price_monthly")
