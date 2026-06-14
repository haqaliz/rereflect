"""
TDD test for B4 second wave: drop remaining dead Stripe/billing columns.

RED → must fail before changes.
GREEN → must pass after migration, model removals, and org_resolver cleanup.

Columns being dropped:
  organizations:   stripe_customer_id, max_seats
  subscriptions:   stripe_subscription_id, stripe_price_id, billing_cycle,
                   trial_start, trial_end, current_period_start,
                   current_period_end, cancel_at_period_end, canceled_at
  usage_records:   overage_feedback
  llm_usage_logs:  is_byok

KEEP:  organizations.plan, subscriptions.plan, subscriptions.status
       (and all other non-listed columns)
"""

import sys
import os
import pytest
from sqlalchemy.inspection import inspect as sa_inspect


# ─── Backend-API: organizations table ─────────────────────────────────────────

class TestBackendOrganizationColumns:
    """organizations.stripe_customer_id and max_seats must be gone."""

    def test_no_stripe_customer_id(self):
        from src.models.organization import Organization
        assert not hasattr(Organization, "stripe_customer_id"), (
            "Organization.stripe_customer_id still declared — "
            "remove from services/backend-api/src/models/organization.py"
        )
        mapper = sa_inspect(Organization)
        cols = [c.key for c in mapper.mapper.column_attrs]
        assert "stripe_customer_id" not in cols

    def test_no_max_seats(self):
        from src.models.organization import Organization
        assert not hasattr(Organization, "max_seats"), (
            "Organization.max_seats still declared — "
            "remove from services/backend-api/src/models/organization.py"
        )
        mapper = sa_inspect(Organization)
        cols = [c.key for c in mapper.mapper.column_attrs]
        assert "max_seats" not in cols

    def test_keeps_plan(self):
        """organization.plan must survive — it is load-bearing."""
        from src.models.organization import Organization
        assert hasattr(Organization, "plan"), "Organization.plan must not be dropped"

    def test_keeps_other_core_columns(self):
        from src.models.organization import Organization
        for col in ("id", "name", "plan", "seat_count", "created_at",
                    "ai_analysis_enabled"):
            assert hasattr(Organization, col), f"Organization.{col} unexpectedly missing"


# ─── Backend-API: subscriptions table ─────────────────────────────────────────

class TestBackendSubscriptionColumns:
    """All listed stripe/billing columns must be gone from Subscription."""

    DROPPED = [
        "stripe_subscription_id", "stripe_price_id", "billing_cycle",
        "trial_start", "trial_end", "current_period_start",
        "current_period_end", "cancel_at_period_end", "canceled_at",
    ]

    def test_no_stripe_subscription_id(self):
        from src.models.subscription import Subscription
        assert not hasattr(Subscription, "stripe_subscription_id"), (
            "Subscription.stripe_subscription_id still declared"
        )

    def test_no_stripe_price_id(self):
        from src.models.subscription import Subscription
        assert not hasattr(Subscription, "stripe_price_id")

    def test_no_billing_cycle(self):
        from src.models.subscription import Subscription
        assert not hasattr(Subscription, "billing_cycle")

    def test_no_trial_start(self):
        from src.models.subscription import Subscription
        assert not hasattr(Subscription, "trial_start")

    def test_no_trial_end(self):
        from src.models.subscription import Subscription
        assert not hasattr(Subscription, "trial_end")

    def test_no_current_period_start(self):
        from src.models.subscription import Subscription
        assert not hasattr(Subscription, "current_period_start")

    def test_no_current_period_end(self):
        from src.models.subscription import Subscription
        assert not hasattr(Subscription, "current_period_end")

    def test_no_cancel_at_period_end(self):
        from src.models.subscription import Subscription
        assert not hasattr(Subscription, "cancel_at_period_end")

    def test_no_canceled_at(self):
        from src.models.subscription import Subscription
        assert not hasattr(Subscription, "canceled_at")

    def test_mapper_columns_clean(self):
        from src.models.subscription import Subscription
        mapper = sa_inspect(Subscription)
        cols = [c.key for c in mapper.mapper.column_attrs]
        for dropped in self.DROPPED:
            assert dropped not in cols, f"Subscription.{dropped} still in mapper columns"

    def test_keeps_plan(self):
        from src.models.subscription import Subscription
        assert hasattr(Subscription, "plan"), "Subscription.plan must not be dropped"

    def test_keeps_status(self):
        from src.models.subscription import Subscription
        assert hasattr(Subscription, "status"), "Subscription.status must not be dropped"

    def test_keeps_core_columns(self):
        from src.models.subscription import Subscription
        for col in ("id", "organization_id", "plan", "status", "created_at", "updated_at"):
            assert hasattr(Subscription, col), f"Subscription.{col} unexpectedly missing"


# ─── Backend-API: usage_records table ─────────────────────────────────────────

class TestBackendUsageRecordColumns:
    """usage_records.overage_feedback must be gone."""

    def test_no_overage_feedback(self):
        from src.models.usage import UsageRecord
        assert not hasattr(UsageRecord, "overage_feedback"), (
            "UsageRecord.overage_feedback still declared — "
            "remove from services/backend-api/src/models/usage.py"
        )
        mapper = sa_inspect(UsageRecord)
        cols = [c.key for c in mapper.mapper.column_attrs]
        assert "overage_feedback" not in cols

    def test_keeps_core_columns(self):
        from src.models.usage import UsageRecord
        for col in ("id", "organization_id", "period_start", "period_end",
                    "feedback_count", "api_calls_count", "created_at"):
            assert hasattr(UsageRecord, col), f"UsageRecord.{col} unexpectedly missing"


# ─── Backend-API: llm_usage_logs table ────────────────────────────────────────

class TestBackendLLMUsageLogColumns:
    """llm_usage_logs.is_byok must be gone."""

    def test_no_is_byok(self):
        from src.models.llm_usage_log import LLMUsageLog
        assert not hasattr(LLMUsageLog, "is_byok"), (
            "LLMUsageLog.is_byok still declared — "
            "remove from services/backend-api/src/models/llm_usage_log.py"
        )
        mapper = sa_inspect(LLMUsageLog)
        cols = [c.key for c in mapper.mapper.column_attrs]
        assert "is_byok" not in cols

    def test_keeps_core_columns(self):
        from src.models.llm_usage_log import LLMUsageLog
        for col in ("id", "organization_id", "provider", "model", "task_type",
                    "prompt_tokens", "completion_tokens", "total_tokens",
                    "estimated_cost_cents", "was_fallback", "created_at"):
            assert hasattr(LLMUsageLog, col), f"LLMUsageLog.{col} unexpectedly missing"


# ─── Worker mirror models ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def worker_models():
    """Import worker-service models by injecting the worker src path."""
    worker_src = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../worker-service")
    )
    if worker_src not in sys.path:
        sys.path.insert(0, worker_src)
    import importlib
    import src.models as _wm
    importlib.reload(_wm)
    return _wm


class TestWorkerMirrorModels:
    """Worker mirror must drop the same columns as backend."""

    def test_worker_organization_no_stripe_customer_id(self, worker_models):
        assert not hasattr(worker_models.Organization, "stripe_customer_id"), (
            "worker Organization.stripe_customer_id still declared — "
            "remove from services/worker-service/src/models/__init__.py"
        )

    def test_worker_organization_no_max_seats(self, worker_models):
        assert not hasattr(worker_models.Organization, "max_seats"), (
            "worker Organization.max_seats still declared — "
            "remove from services/worker-service/src/models/__init__.py"
        )

    def test_worker_subscription_dropped_columns(self, worker_models):
        dropped = [
            "stripe_subscription_id", "stripe_price_id", "billing_cycle",
            "trial_start", "trial_end", "current_period_start",
            "current_period_end", "cancel_at_period_end", "canceled_at",
        ]
        for col in dropped:
            assert not hasattr(worker_models.Subscription, col), (
                f"worker Subscription.{col} still declared — "
                "remove from services/worker-service/src/models/__init__.py"
            )

    def test_worker_usage_record_no_overage_feedback(self, worker_models):
        assert not hasattr(worker_models.UsageRecord, "overage_feedback"), (
            "worker UsageRecord.overage_feedback still declared — "
            "remove from services/worker-service/src/models/__init__.py"
        )

    def test_worker_llm_usage_log_no_is_byok(self, worker_models):
        assert not hasattr(worker_models.LLMUsageLog, "is_byok"), (
            "worker LLMUsageLog.is_byok still declared — "
            "remove from services/worker-service/src/models/__init__.py"
        )

    def test_worker_subscription_keeps_plan_and_status(self, worker_models):
        assert hasattr(worker_models.Subscription, "plan")
        assert hasattr(worker_models.Subscription, "status")

    def test_worker_organization_keeps_plan(self, worker_models):
        assert hasattr(worker_models.Organization, "plan")


# ─── org_resolver: is_byok write removed ──────────────────────────────────────

class TestOrgResolverNoBYOKWrite:
    """log_usage must not write is_byok; LLMUsageLog constructor call must not include it."""

    def test_log_usage_no_is_byok_param(self):
        """log_usage must not accept an is_byok parameter."""
        import inspect
        import sys
        worker_src = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../worker-service")
        )
        if worker_src not in sys.path:
            sys.path.insert(0, worker_src)

        # Import without actually connecting to DB / loading all deps
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "org_resolver_under_test",
            os.path.join(worker_src, "src/llm/org_resolver.py"),
        )
        # We only need the source text for signature inspection
        with open(os.path.join(worker_src, "src/llm/org_resolver.py")) as f:
            source = f.read()

        # log_usage must not have 'is_byok' as a parameter
        assert "def log_usage(" in source
        # Find the log_usage function signature
        sig_start = source.index("def log_usage(")
        sig_end = source.index(")", sig_start)
        sig_text = source[sig_start:sig_end + 1]
        assert "is_byok" not in sig_text, (
            f"log_usage still has is_byok param: {sig_text}"
        )

    def test_log_usage_no_is_byok_write(self):
        """log_usage body must not write is_byok= to LLMUsageLog."""
        worker_src = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../worker-service")
        )
        with open(os.path.join(worker_src, "src/llm/org_resolver.py")) as f:
            source = f.read()
        assert "is_byok=is_byok" not in source, (
            "log_usage still writes is_byok=is_byok to LLMUsageLog"
        )
        # also ensure the LLMUsageLog constructor call has no is_byok kwarg
        assert "is_byok=" not in source, (
            "org_resolver.py still references is_byok= keyword argument"
        )

    def test_call_llm_for_org_no_is_byok_arg(self):
        """call_llm_for_org must not pass is_byok to log_usage."""
        worker_src = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../worker-service")
        )
        with open(os.path.join(worker_src, "src/llm/org_resolver.py")) as f:
            source = f.read()
        # The call site in call_llm_for_org must not pass is_byok
        # We check that log_usage( ... is_byok is not in any call
        import re
        # Find all log_usage( calls
        calls = re.findall(r'log_usage\([^)]*\)', source, re.DOTALL)
        for call in calls:
            assert "is_byok" not in call, (
                f"call_llm_for_org still passes is_byok to log_usage: {call}"
            )
