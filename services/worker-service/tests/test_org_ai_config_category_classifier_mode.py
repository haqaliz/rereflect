"""
TDD test for per-org-category-classifier (M5.2 v2) — worker mirror of
OrgAIConfig.category_classifier_mode. Mirrors test_org_classifier_mirror.py's
test_worker_orgaiconfig_has_classifier_mode (sentiment -> category).
"""


def test_worker_orgaiconfig_has_category_classifier_mode():
    from src.models import OrgAIConfig

    assert hasattr(OrgAIConfig(), "category_classifier_mode")
