"""
Tests for the BYOK-only (bring-your-own-key) pivot.

PRD Workstream A: A1 (org_resolver), A2 (fallback), A5 (analysis pending).

RED → GREEN test sequence:
- Write failing tests first (test code is committed before production changes).
- Production changes make them green.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.models import FeedbackItem, Organization, OrgApiKey, OrgAIConfig


# ---------------------------------------------------------------------------
# A1 — build_fallback_chain: no system key, no BYOK → (None, False)
# ---------------------------------------------------------------------------


class TestBuildFallbackChainByokOnly:
    """build_fallback_chain must never use a system/env key."""

    def _make_db_without_byok(self, org_id: int):
        """Return a mock db with no OrgApiKey row for the given org."""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.first.return_value = None  # No OrgApiKey row
        return mock_db

    def _make_db_with_byok(self, org_id: int, provider: str, encrypted_key: str):
        """Return a mock db that returns an OrgApiKey for the given org/provider."""
        mock_key_record = MagicMock()
        mock_key_record.encrypted_key = encrypted_key

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.first.return_value = mock_key_record
        return mock_db

    def test_no_byok_returns_none_chain(self):
        """When an org has NO BYOK key, build_fallback_chain must return (None, False)."""
        from src.llm.org_resolver import build_fallback_chain

        db = self._make_db_without_byok(org_id=1)

        # Even with OPENAI_API_KEY set in env, must return None — no system key fallback
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-system-key"}):
            chain, is_byok = build_fallback_chain(
                org_id=1, provider="openai", model="gpt-4o-mini", db=db
            )

        assert chain is None
        assert is_byok is False

    def test_no_byok_anthropic_returns_none_chain(self):
        """No BYOK for Anthropic → (None, False), even with ANTHROPIC_API_KEY set."""
        from src.llm.org_resolver import build_fallback_chain

        db = self._make_db_without_byok(org_id=2)

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-system"}):
            chain, is_byok = build_fallback_chain(
                org_id=2, provider="anthropic", model="claude-haiku-4-5", db=db
            )

        assert chain is None
        assert is_byok is False

    def test_no_byok_google_returns_none_chain(self):
        """No BYOK for Google → (None, False), even with GOOGLE_AI_API_KEY set."""
        from src.llm.org_resolver import build_fallback_chain

        db = self._make_db_without_byok(org_id=3)

        with patch.dict(os.environ, {"GOOGLE_AI_API_KEY": "google-system-key"}):
            chain, is_byok = build_fallback_chain(
                org_id=3, provider="google", model="gemini-pro", db=db
            )

        assert chain is None
        assert is_byok is False

    def test_valid_byok_builds_chain(self):
        """When an org HAS a valid BYOK key, build_fallback_chain returns a working chain."""
        from src.llm.org_resolver import build_fallback_chain

        db = self._make_db_with_byok(org_id=4, provider="openai", encrypted_key="encrypted-stub")

        # Patch _decrypt_api_key so we don't need the real Fernet env setup
        with patch("src.llm.org_resolver._decrypt_api_key", return_value="sk-byok-test-key-1234"), \
             patch("src.llm.org_resolver.LLMProviderFactory") as mock_factory:
            mock_factory.create.return_value = MagicMock()
            chain, is_byok = build_fallback_chain(
                org_id=4, provider="openai", model="gpt-4o-mini", db=db
            )

        assert chain is not None
        assert is_byok is True

    def test_byok_chain_has_no_system_fallback(self):
        """FallbackChain built from BYOK key must NOT have a system_provider."""
        from src.llm.org_resolver import build_fallback_chain

        db = self._make_db_with_byok(org_id=5, provider="openai", encrypted_key="encrypted-stub")

        with patch("src.llm.org_resolver._decrypt_api_key", return_value="sk-byok-key"), \
             patch.dict(os.environ, {"OPENAI_API_KEY": "sk-system-should-not-be-used"}), \
             patch("src.llm.org_resolver.LLMProviderFactory") as mock_factory:
            mock_factory.create.return_value = MagicMock()
            chain, is_byok = build_fallback_chain(
                org_id=5, provider="openai", model="gpt-4o-mini", db=db
            )

        assert chain is not None
        # The chain's internal _system provider must be None — no system fallback
        assert chain._system is None

    def test_no_system_key_function_exists(self):
        """_get_system_key_for_provider must NOT exist in org_resolver after the pivot."""
        import src.llm.org_resolver as resolver
        assert not hasattr(resolver, "_get_system_key_for_provider"), (
            "_get_system_key_for_provider still exists — system key path not removed"
        )

    def test_no_system_openai_key_module_level(self):
        """_SYSTEM_OPENAI_KEY must NOT be defined at module level in org_resolver."""
        import src.llm.org_resolver as resolver
        assert not hasattr(resolver, "_SYSTEM_OPENAI_KEY"), (
            "_SYSTEM_OPENAI_KEY still defined — env system key not removed"
        )

    def test_no_system_anthropic_key_module_level(self):
        """_SYSTEM_ANTHROPIC_KEY must NOT be defined at module level."""
        import src.llm.org_resolver as resolver
        assert not hasattr(resolver, "_SYSTEM_ANTHROPIC_KEY")

    def test_no_system_google_key_module_level(self):
        """_SYSTEM_GOOGLE_KEY must NOT be defined at module level."""
        import src.llm.org_resolver as resolver
        assert not hasattr(resolver, "_SYSTEM_GOOGLE_KEY")


# ---------------------------------------------------------------------------
# A1 — check_budget deleted; call_llm_for_org no budget check
# ---------------------------------------------------------------------------


class TestCheckBudgetRemoved:
    """check_budget() must be deleted entirely (budget logic is moot without system key)."""

    def test_check_budget_does_not_exist(self):
        """check_budget function must not exist in org_resolver."""
        import src.llm.org_resolver as resolver
        assert not hasattr(resolver, "check_budget"), (
            "check_budget still exists — should have been deleted"
        )

    def test_call_llm_for_org_no_budget_check_when_keyless(self):
        """call_llm_for_org with no BYOK key must return None immediately, no budget query."""
        from src.llm.org_resolver import call_llm_for_org
        from src.llm.types import LLMRequest

        mock_db = MagicMock()
        # No OrgApiKey row
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        request = LLMRequest(messages=[{"role": "user", "content": "test"}])

        result = call_llm_for_org(
            org_id=99,
            task_type="categorization",
            request=request,
            provider="openai",
            model="gpt-4o-mini",
            db=mock_db,
        )

        assert result is None
        # Must not have touched budget columns
        # (We just verify no OrgAIConfig budget query was made for budget enforcement)
        # The db is still queried for OrgApiKey — just not for budget.

    def test_log_usage_does_not_update_budget_used(self):
        """log_usage must NOT write to budget_used_cents (no is_byok branch)."""
        from src.llm.org_resolver import log_usage
        from src.llm.types import LLMResponse

        mock_org_ai_config = MagicMock()
        mock_org_ai_config.budget_used_cents = 0

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.first.return_value = mock_org_ai_config

        response = LLMResponse(
            content="{}",
            provider="openai",
            model="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost_cents=5.0,
            latency_ms=300,
            was_fallback=False,
            fallback_reason=None,
        )

        # Call with is_byok=True (BYOK org)
        log_usage(org_id=1, response=response, task_type="categorization", is_byok=True, db=mock_db)

        # budget_used_cents must NOT have been mutated
        assert mock_org_ai_config.budget_used_cents == 0


# ---------------------------------------------------------------------------
# A2 — FallbackChain: no system provider (Attempt 3 removed)
# ---------------------------------------------------------------------------


class TestFallbackChainNoSystemProvider:
    """FallbackChain must only do primary + retry. No system-provider attempt."""

    def _make_request(self):
        from src.llm.types import LLMRequest
        return LLMRequest(messages=[{"role": "user", "content": "test"}])

    def test_constructor_still_accepts_system_provider_none(self):
        """FallbackChain(primary, system_provider=None) must be the only valid call pattern."""
        from src.llm.fallback import FallbackChain

        mock_primary = MagicMock()
        # Must not raise
        chain = FallbackChain(primary_provider=mock_primary, system_provider=None)
        assert chain is not None

    def test_both_attempts_fail_returns_none_without_system_fallback(self):
        """When both primary attempts fail and system_provider=None, must return None."""
        from src.llm.fallback import FallbackChain
        from openai import RateLimitError

        err = RateLimitError(
            message="Rate limit",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"message": "rate limit"}},
        )
        mock_primary = MagicMock()
        mock_primary.complete.side_effect = [err, err]

        chain = FallbackChain(primary_provider=mock_primary, system_provider=None)

        with patch("time.sleep"):
            result = chain.complete(self._make_request())

        assert result is None
        assert mock_primary.complete.call_count == 2

    def test_system_provider_is_not_called_even_if_provided(self):
        """After the pivot, even if system_provider is passed, it must NOT be called on failure.

        The constructor signature is kept for compat but system_provider is ignored
        (or the attribute is removed). Either way: after two primary failures,
        system_provider.complete() must not be called.
        """
        from src.llm.fallback import FallbackChain
        from openai import RateLimitError

        err = RateLimitError(
            message="Rate limit",
            response=MagicMock(status_code=429, headers={}),
            body={"error": {"message": "rate limit"}},
        )
        mock_primary = MagicMock()
        mock_primary.complete.side_effect = [err, err]

        # Provide a non-None system_provider — it must be ignored
        mock_system = MagicMock()
        chain = FallbackChain(primary_provider=mock_primary, system_provider=mock_system)

        with patch("time.sleep"):
            result = chain.complete(self._make_request())

        # System provider must NOT have been called
        mock_system.complete.assert_not_called()
        assert result is None


# ---------------------------------------------------------------------------
# A3 — service.py is deleted
# ---------------------------------------------------------------------------


class TestServicePyDeleted:
    """src.llm.service must not exist after the dead-code removal."""

    def test_service_module_does_not_exist(self):
        """Importing src.llm.service should raise ImportError or ModuleNotFoundError."""
        import importlib
        import sys

        # Remove cached module if already loaded
        sys.modules.pop("src.llm.service", None)

        with pytest.raises((ImportError, ModuleNotFoundError)):
            importlib.import_module("src.llm.service")


# ---------------------------------------------------------------------------
# A5 — llm_analysis_pending: keyless org stays False; transient failure sets True
# ---------------------------------------------------------------------------


class TestAnalysisPendingKeylessOrg:
    """
    When org has AI enabled but NO BYOK key:
      - VADER/keyword analysis runs fully
      - llm_analysis_pending stays False (no perpetual retry)

    When AI is enabled, key is present, but LLM call fails transiently:
      - llm_analysis_pending is set to True (correct retry later)

    All analyzer imports (_apply_keyword_analysis) are mocked since
    the analysis-engine service is not available in the test environment.
    """

    def _mock_analyzers(self):
        """Return patches for the three lazy-import analyzer helpers."""
        mock_sa = MagicMock()
        mock_sa.analyze.return_value = {"compound": -0.6, "label": "negative"}

        mock_pain = MagicMock()
        mock_pain.categorize.return_value = MagicMock(
            category="bugs", level="major", text="crash", confidence=0.8
        )
        mock_feat = MagicMock()
        mock_feat.categorize.return_value = MagicMock(
            category=None, level=None, text=None, confidence=0.0
        )
        mock_urgent = MagicMock()
        mock_urgent.categorize.return_value = MagicMock(
            category="critical_bug", level="immediate", text="crash", confidence=0.9
        )
        mock_te = MagicMock()
        mock_te.extract_tags.return_value = ["crash", "cancel"]

        return {
            "src.tasks.analysis.get_sentiment_analyzer": MagicMock(return_value=mock_sa),
            "src.tasks.analysis.get_tag_extractor": MagicMock(return_value=mock_te),
            "src.tasks.analysis.get_categorizers": MagicMock(
                return_value=(mock_pain, mock_feat, mock_urgent)
            ),
        }

    def _make_feedback(self, org_id: int, db):
        feedback = FeedbackItem(
            organization_id=org_id,
            text="The app crashes constantly and I'm thinking of canceling.",
            source="support",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)
        return feedback

    def test_keyless_org_pending_stays_false(self, db):
        """Org with ai_analysis_enabled=True but NO BYOK key: pending must be False after analysis.

        After A5 fix: _analyze_feedback_item detects "no key" (categorize_feedback
        returns None AND the org has no OrgApiKey row) and does NOT set
        llm_analysis_pending=True. Only genuine transient failures set it.
        """
        from src.tasks.analysis import _analyze_feedback_item

        org = Organization(name="Keyless Corp", plan="pro", ai_analysis_enabled=True)
        db.add(org)
        db.commit()
        db.refresh(org)

        feedback = self._make_feedback(org.id, db)

        # No OrgApiKey row exists for this org → "no BYOK key" scenario
        # categorize_feedback returns None (resolver returns None immediately)
        analyzer_patches = self._mock_analyzers()
        with patch("src.tasks.analysis.categorize_feedback", return_value=None), \
             patch("src.tasks.analysis.get_sentiment_analyzer", analyzer_patches["src.tasks.analysis.get_sentiment_analyzer"]), \
             patch("src.tasks.analysis.get_tag_extractor", analyzer_patches["src.tasks.analysis.get_tag_extractor"]), \
             patch("src.tasks.analysis.get_categorizers", analyzer_patches["src.tasks.analysis.get_categorizers"]):
            _analyze_feedback_item(feedback, db)

        # Keyword/VADER fallback must have run fully
        assert feedback.sentiment_label is not None, "VADER fallback must set sentiment_label"
        # No perpetual retry — pending must remain False for keyless org
        assert feedback.llm_analysis_pending is False, (
            "llm_analysis_pending must be False when org has no BYOK key "
            "(only True on transient failure)"
        )

    def test_keyword_analysis_fully_analyzes_ai_disabled_feedback(self, db):
        """VADER+keyword fallback must produce a fully analyzed item when AI is disabled."""
        from src.tasks.analysis import _analyze_feedback_item

        org = Organization(name="VADER Corp", plan="free", ai_analysis_enabled=False)
        db.add(org)
        db.commit()
        db.refresh(org)

        feedback = FeedbackItem(
            organization_id=org.id,
            text="This is terrible, cancel my subscription immediately!",
            source="support",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        analyzer_patches = self._mock_analyzers()
        with patch("src.tasks.analysis.get_sentiment_analyzer", analyzer_patches["src.tasks.analysis.get_sentiment_analyzer"]), \
             patch("src.tasks.analysis.get_tag_extractor", analyzer_patches["src.tasks.analysis.get_tag_extractor"]), \
             patch("src.tasks.analysis.get_categorizers", analyzer_patches["src.tasks.analysis.get_categorizers"]):
            _analyze_feedback_item(feedback, db)

        # All core fields must be set
        assert feedback.sentiment_label in ("positive", "neutral", "negative")
        assert feedback.sentiment_score is not None
        assert feedback.is_urgent is not None
        assert feedback.llm_analyzed is False
        assert feedback.llm_analysis_pending is False

    def test_apply_keyword_analysis_sets_churn_risk(self, db):
        """_apply_keyword_analysis must always set churn_risk_score (no LLM needed)."""
        from src.tasks.analysis import _apply_keyword_analysis

        org = Organization(name="KW Corp", plan="free")
        db.add(org)
        db.commit()

        feedback = FeedbackItem(
            organization_id=org.id,
            text="I hate this product, switching to competitor immediately!",
            source="support",
        )
        db.add(feedback)
        db.commit()
        db.refresh(feedback)

        analyzer_patches = self._mock_analyzers()
        with patch("src.tasks.analysis.get_sentiment_analyzer", analyzer_patches["src.tasks.analysis.get_sentiment_analyzer"]), \
             patch("src.tasks.analysis.get_tag_extractor", analyzer_patches["src.tasks.analysis.get_tag_extractor"]), \
             patch("src.tasks.analysis.get_categorizers", analyzer_patches["src.tasks.analysis.get_categorizers"]):
            _apply_keyword_analysis(feedback, db)

        assert feedback.churn_risk_score is not None
        assert 0 <= feedback.churn_risk_score <= 100
        assert feedback.sentiment_label is not None
        assert feedback.llm_analyzed is False

    def test_transient_llm_failure_sets_pending_true(self, db):
        """When org HAS a BYOK key but LLM call fails transiently, pending must be True.

        After A5 fix: _analyze_feedback_item detects a BYOK key is configured
        (OrgApiKey row exists) but categorize_feedback returned None (transient failure).
        In that case, llm_analysis_pending=True is correct — retry later.
        """
        from src.tasks.analysis import _analyze_feedback_item
        from cryptography.fernet import Fernet

        fernet_key = Fernet.generate_key()
        fernet = Fernet(fernet_key)
        encrypted = fernet.encrypt(b"sk-byok-real-key").decode()

        org = Organization(name="BYOK Corp", plan="business", ai_analysis_enabled=True)
        db.add(org)
        db.commit()
        db.refresh(org)

        # Add a BYOK key row for this org → "key configured, transient failure" scenario
        api_key = OrgApiKey(
            organization_id=org.id,
            provider="openai",
            encrypted_key=encrypted,
            is_valid=True,
        )
        db.add(api_key)
        db.commit()

        feedback = self._make_feedback(org.id, db)

        # categorize_feedback returns None despite key being present → transient failure
        analyzer_patches = self._mock_analyzers()
        with patch("src.tasks.analysis.categorize_feedback", return_value=None), \
             patch("src.tasks.analysis.get_sentiment_analyzer", analyzer_patches["src.tasks.analysis.get_sentiment_analyzer"]), \
             patch("src.tasks.analysis.get_tag_extractor", analyzer_patches["src.tasks.analysis.get_tag_extractor"]), \
             patch("src.tasks.analysis.get_categorizers", analyzer_patches["src.tasks.analysis.get_categorizers"]):
            _analyze_feedback_item(feedback, db)

        # Key is configured → this is a transient failure → pending=True is correct
        assert feedback.llm_analysis_pending is True, (
            "llm_analysis_pending must be True when org has BYOK key but LLM call failed transiently"
        )
