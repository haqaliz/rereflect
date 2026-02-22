"""
Tests for LLM service — high-level wrapper for org config, factory, and fallback.
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock


class TestCallLlm:
    """Tests for the call_llm high-level function."""

    def _mock_org_config(self, provider="openai", budget_exceeded=False, byok_key=None):
        """Build a mock org config dict."""
        byok_keys = {}
        if byok_key:
            byok_keys[provider] = byok_key
        return {
            "provider": provider,
            "model_categorization": "gpt-4o-mini",
            "model_analysis": "gpt-4o-mini",
            "model_insights": "gpt-4o-mini",
            "byok_keys": byok_keys,
            "budget_exceeded": budget_exceeded,
        }

    def _mock_llm_response(self, content='{"ok": true}', provider="openai", model="gpt-4o-mini"):
        from src.llm.types import LLMResponse
        return LLMResponse(
            content=content,
            provider=provider,
            model=model,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_cost_cents=0.01,
            latency_ms=500,
            was_fallback=False,
            fallback_reason=None,
        )

    @patch("src.llm.service._log_usage")
    @patch("src.llm.service._build_chain")
    @patch("src.llm.service._get_org_config")
    def test_returns_content_provider_model_on_success(self, mock_config, mock_chain, mock_log):
        """call_llm should return (content, provider, model) on success."""
        from src.llm.service import call_llm

        mock_config.return_value = self._mock_org_config()
        mock_chain_instance = MagicMock()
        mock_chain_instance.complete.return_value = self._mock_llm_response()
        mock_chain.return_value = (mock_chain_instance, False)

        result = call_llm(
            org_id=1,
            task_type="categorization",
            messages=[{"role": "user", "content": "test"}],
            db=MagicMock(),
        )

        assert result is not None
        content, provider, model = result
        assert content == '{"ok": true}'
        assert provider == "openai"
        assert model == "gpt-4o-mini"

    @patch("src.llm.service._get_org_config")
    def test_returns_none_when_budget_exceeded(self, mock_config):
        """call_llm should return None when org budget is exceeded."""
        from src.llm.service import call_llm

        mock_config.return_value = self._mock_org_config(budget_exceeded=True)

        result = call_llm(
            org_id=1,
            task_type="categorization",
            messages=[{"role": "user", "content": "test"}],
            db=MagicMock(),
        )

        assert result is None

    @patch("src.llm.service._build_chain")
    @patch("src.llm.service._get_org_config")
    def test_returns_none_when_no_api_key(self, mock_config, mock_chain):
        """call_llm should return None when no API key is available."""
        from src.llm.service import call_llm

        mock_config.return_value = self._mock_org_config()
        mock_chain.return_value = (None, False)

        result = call_llm(
            org_id=1,
            task_type="categorization",
            messages=[{"role": "user", "content": "test"}],
            db=MagicMock(),
        )

        assert result is None

    @patch("src.llm.service._log_usage")
    @patch("src.llm.service._build_chain")
    @patch("src.llm.service._get_org_config")
    def test_returns_none_when_llm_fails(self, mock_config, mock_chain, mock_log):
        """call_llm should return None when LLM call fails."""
        from src.llm.service import call_llm

        mock_config.return_value = self._mock_org_config()
        mock_chain_instance = MagicMock()
        mock_chain_instance.complete.return_value = None
        mock_chain.return_value = (mock_chain_instance, False)

        result = call_llm(
            org_id=1,
            task_type="categorization",
            messages=[{"role": "user", "content": "test"}],
            db=MagicMock(),
        )

        assert result is None

    @patch("src.llm.service._log_usage")
    @patch("src.llm.service._build_chain")
    @patch("src.llm.service._get_org_config")
    def test_logs_usage_on_success(self, mock_config, mock_chain, mock_log):
        """call_llm should log usage on success."""
        from src.llm.service import call_llm

        mock_config.return_value = self._mock_org_config()
        response = self._mock_llm_response()
        mock_chain_instance = MagicMock()
        mock_chain_instance.complete.return_value = response
        mock_chain.return_value = (mock_chain_instance, False)

        mock_db = MagicMock()
        call_llm(org_id=1, task_type="categorization", messages=[{"role": "user", "content": "test"}], db=mock_db)

        mock_log.assert_called_once()
        call_args = mock_log.call_args
        # Positional args: (org_id, response, task_type, is_byok, db)
        assert call_args[0][0] == 1

    @patch("src.llm.service._log_usage")
    @patch("src.llm.service._build_chain")
    @patch("src.llm.service._get_org_config")
    def test_uses_correct_model_for_task_type(self, mock_config, mock_chain, mock_log):
        """call_llm should select the correct model based on task_type."""
        from src.llm.service import call_llm

        config = self._mock_org_config(provider="anthropic")
        config["model_analysis"] = "claude-sonnet-4-6"
        mock_config.return_value = config

        mock_chain_instance = MagicMock()
        mock_chain_instance.complete.return_value = self._mock_llm_response(provider="anthropic", model="claude-sonnet-4-6")
        mock_chain.return_value = (mock_chain_instance, False)

        result = call_llm(
            org_id=1,
            task_type="analysis",
            messages=[{"role": "user", "content": "test"}],
            db=MagicMock(),
        )

        assert result is not None
        _, provider, model = result
        assert provider == "anthropic"


class TestBuildChain:
    """Tests for the _build_chain helper."""

    @patch("src.llm.service._get_system_key", return_value="sk-system")
    def test_creates_chain_with_system_key(self, mock_sys_key):
        """Should create chain with system key when no BYOK."""
        from src.llm.service import _build_chain

        with patch("src.llm.service.LLMProviderFactory") as mock_factory:
            mock_provider = MagicMock()
            mock_factory.create.return_value = mock_provider

            chain, is_byok = _build_chain("openai", "gpt-4o-mini", {})

        assert chain is not None
        assert is_byok is False

    @patch("src.llm.service._get_system_key", return_value="sk-system")
    def test_creates_chain_with_byok_key(self, mock_sys_key):
        """Should create chain with BYOK key and system fallback."""
        from src.llm.service import _build_chain

        with patch("src.llm.service.LLMProviderFactory") as mock_factory:
            mock_provider = MagicMock()
            mock_factory.create.return_value = mock_provider

            chain, is_byok = _build_chain("anthropic", "claude-haiku-4-5", {"anthropic": "sk-ant-byok"})

        assert chain is not None
        assert is_byok is True
        # Factory should be called twice: once for primary, once for system fallback
        assert mock_factory.create.call_count == 2

    @patch("src.llm.service._get_system_key", return_value="")
    def test_returns_none_when_no_key(self, mock_sys_key):
        """Should return None when no key available."""
        from src.llm.service import _build_chain

        chain, is_byok = _build_chain("openai", "gpt-4o-mini", {})

        assert chain is None
        assert is_byok is False


class TestResolveApiKey:
    """Tests for _resolve_api_key."""

    def test_prefers_byok_over_system(self):
        """BYOK key should take priority over system key."""
        from src.llm.service import _resolve_api_key

        with patch("src.llm.service._get_system_key", return_value="sk-system"):
            key, is_byok = _resolve_api_key("openai", {"openai": "sk-byok"})

        assert key == "sk-byok"
        assert is_byok is True

    def test_falls_back_to_system(self):
        """Should fall back to system key when no BYOK."""
        from src.llm.service import _resolve_api_key

        with patch("src.llm.service._get_system_key", return_value="sk-system"):
            key, is_byok = _resolve_api_key("openai", {})

        assert key == "sk-system"
        assert is_byok is False

    def test_returns_empty_when_no_keys(self):
        """Should return empty string when no keys available."""
        from src.llm.service import _resolve_api_key

        with patch("src.llm.service._get_system_key", return_value=""):
            key, is_byok = _resolve_api_key("openai", {})

        assert key == ""
        assert is_byok is False
