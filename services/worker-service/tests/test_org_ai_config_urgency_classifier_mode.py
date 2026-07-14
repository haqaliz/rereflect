"""
TDD test for per-org-urgency-classifier (urgency-classifier-head,
data-and-config aspect) — worker mirror of OrgAIConfig.urgency_classifier_mode.
Mirrors test_org_ai_config_category_classifier_mode.py (category -> urgency).
"""


def test_worker_orgaiconfig_has_urgency_classifier_mode():
    from src.models import OrgAIConfig

    assert hasattr(OrgAIConfig(), "urgency_classifier_mode")
