"""
RED → GREEN TDD test for B4: drop dead billing/budget columns.

Tests assert that the FOUR columns that have zero live code references
outside model declarations have been removed from the ORM model classes
AND are absent from the SQLAlchemy mapper column attributes.

Columns under test (safe-to-drop set):
  usage_records.overage_reported_to_stripe
  org_ai_config.monthly_budget_cents
  org_ai_config.budget_used_cents
  org_ai_config.budget_reset_at

Columns intentionally NOT tested (still referenced in live code — skipped):
  organizations.stripe_customer_id        — admin_orgs.py reads
  organizations.max_seats                 — admin_orgs.py reads
  subscriptions.stripe_*                  — billing.py reads
  subscriptions.trial_*/period_*/cancel_* — billing.py + dependencies.py
  usage_records.overage_feedback          — billing.py + feedback.py
  llm_usage_logs.is_byok                  — org_resolver.py writes
"""

import sys
import os
import pytest
from sqlalchemy.inspection import inspect as sa_inspect


# ─── Backend-API model tests ───────────────────────────────────────────────────

def test_usage_record_no_overage_reported_to_stripe():
    """overage_reported_to_stripe must NOT be a mapped column on UsageRecord."""
    from src.models.usage import UsageRecord
    assert not hasattr(UsageRecord, "overage_reported_to_stripe"), (
        "UsageRecord.overage_reported_to_stripe still declared — "
        "remove the Column() from services/backend-api/src/models/usage.py"
    )
    mapper = sa_inspect(UsageRecord)
    col_names = [c.key for c in mapper.mapper.column_attrs]
    assert "overage_reported_to_stripe" not in col_names, (
        "overage_reported_to_stripe still present in UsageRecord mapper columns"
    )


def test_org_ai_config_no_monthly_budget_cents():
    """monthly_budget_cents must NOT be a mapped column on OrgAIConfig."""
    from src.models.org_ai_config import OrgAIConfig
    assert not hasattr(OrgAIConfig, "monthly_budget_cents"), (
        "OrgAIConfig.monthly_budget_cents still declared — "
        "remove the Column() from services/backend-api/src/models/org_ai_config.py"
    )
    mapper = sa_inspect(OrgAIConfig)
    col_names = [c.key for c in mapper.mapper.column_attrs]
    assert "monthly_budget_cents" not in col_names


def test_org_ai_config_no_budget_used_cents():
    """budget_used_cents must NOT be a mapped column on OrgAIConfig."""
    from src.models.org_ai_config import OrgAIConfig
    assert not hasattr(OrgAIConfig, "budget_used_cents"), (
        "OrgAIConfig.budget_used_cents still declared — "
        "remove the Column() from services/backend-api/src/models/org_ai_config.py"
    )
    mapper = sa_inspect(OrgAIConfig)
    col_names = [c.key for c in mapper.mapper.column_attrs]
    assert "budget_used_cents" not in col_names


def test_org_ai_config_no_budget_reset_at():
    """budget_reset_at must NOT be a mapped column on OrgAIConfig."""
    from src.models.org_ai_config import OrgAIConfig
    assert not hasattr(OrgAIConfig, "budget_reset_at"), (
        "OrgAIConfig.budget_reset_at still declared — "
        "remove the Column() from services/backend-api/src/models/org_ai_config.py"
    )
    mapper = sa_inspect(OrgAIConfig)
    col_names = [c.key for c in mapper.mapper.column_attrs]
    assert "budget_reset_at" not in col_names


def test_org_ai_config_keeps_core_columns():
    """Sanity: OrgAIConfig must still have its non-dead columns."""
    from src.models.org_ai_config import OrgAIConfig
    for col in ("id", "organization_id", "default_provider",
                "model_categorization", "model_analysis", "model_insights",
                "created_at", "updated_at"):
        assert hasattr(OrgAIConfig, col), f"OrgAIConfig.{col} unexpectedly missing"


def test_usage_record_keeps_core_columns():
    """Sanity: UsageRecord must still have its non-dead columns."""
    from src.models.usage import UsageRecord
    for col in ("id", "organization_id", "period_start", "period_end",
                "feedback_count", "api_calls_count", "overage_feedback", "created_at"):
        assert hasattr(UsageRecord, col), f"UsageRecord.{col} unexpectedly missing"


# ─── Worker-service mirror model tests ────────────────────────────────────────

@pytest.fixture(scope="module")
def worker_models():
    """Import worker-service models by injecting the worker src path."""
    worker_src = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../../../worker-service")
    )
    if worker_src not in sys.path:
        sys.path.insert(0, worker_src)
    # Import fresh (avoid stale cache if backend's models.__init__ shadows it)
    import importlib
    import src.models as _wm
    importlib.reload(_wm)
    return _wm


def test_worker_usage_record_no_overage_reported_to_stripe(worker_models):
    """Worker mirror UsageRecord must not declare overage_reported_to_stripe."""
    WorkerUsageRecord = worker_models.UsageRecord
    assert not hasattr(WorkerUsageRecord, "overage_reported_to_stripe"), (
        "worker-service UsageRecord.overage_reported_to_stripe still declared — "
        "remove it from services/worker-service/src/models/__init__.py"
    )


def test_worker_org_ai_config_no_budget_columns(worker_models):
    """Worker mirror OrgAIConfig must not declare any budget columns."""
    WorkerOrgAIConfig = worker_models.OrgAIConfig
    for col in ("monthly_budget_cents", "budget_used_cents", "budget_reset_at"):
        assert not hasattr(WorkerOrgAIConfig, col), (
            f"worker-service OrgAIConfig.{col} still declared — "
            "remove it from services/worker-service/src/models/__init__.py"
        )
