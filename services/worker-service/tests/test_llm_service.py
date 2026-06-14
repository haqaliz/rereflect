"""
Tests for LLM service layer (org_resolver + fallback) — BYOK-only.

NOTE: The old src/llm/service.py (dead parallel resolver with system-key
fallback) was deleted as part of Workstream A3 of the OSS pivot.
Its system-key and budget tests are superseded by test_byok_only.py.

This file retains tests for the active resolver (org_resolver.py) that
verify BYOK-path behaviour.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestCallLlmForOrg:
    """Tests for the active call_llm_for_org function in org_resolver."""

    def _make_request(self):
        from src.llm.types import LLMRequest
        return LLMRequest(messages=[{"role": "user", "content": "test"}])

    def _make_response(self, content='{"ok": true}', provider="openai", model="gpt-4o-mini"):
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

    def test_returns_response_when_byok_key_available(self):
        """call_llm_for_org should return LLMResponse when org has a valid BYOK key."""
        from src.llm.org_resolver import call_llm_for_org

        mock_response = self._make_response()
        mock_db = MagicMock()

        with patch("src.llm.org_resolver.build_fallback_chain") as mock_bfc, \
             patch("src.llm.org_resolver.log_usage") as mock_log:
            mock_chain = MagicMock()
            mock_chain.complete.return_value = mock_response
            mock_bfc.return_value = (mock_chain, True)

            result = call_llm_for_org(
                org_id=1,
                task_type="categorization",
                request=self._make_request(),
                provider="openai",
                model="gpt-4o-mini",
                db=mock_db,
            )

        assert result is mock_response
        mock_log.assert_called_once()

    def test_returns_none_when_no_byok_key(self):
        """call_llm_for_org should return None when org has no BYOK key."""
        from src.llm.org_resolver import call_llm_for_org

        mock_db = MagicMock()

        with patch("src.llm.org_resolver.build_fallback_chain") as mock_bfc:
            mock_bfc.return_value = (None, False)

            result = call_llm_for_org(
                org_id=1,
                task_type="categorization",
                request=self._make_request(),
                provider="openai",
                model="gpt-4o-mini",
                db=mock_db,
            )

        assert result is None

    def test_returns_none_when_llm_call_fails(self):
        """call_llm_for_org should return None when LLM chain fails."""
        from src.llm.org_resolver import call_llm_for_org

        mock_db = MagicMock()

        with patch("src.llm.org_resolver.build_fallback_chain") as mock_bfc:
            mock_chain = MagicMock()
            mock_chain.complete.return_value = None
            mock_bfc.return_value = (mock_chain, True)

            result = call_llm_for_org(
                org_id=1,
                task_type="categorization",
                request=self._make_request(),
                provider="openai",
                model="gpt-4o-mini",
                db=mock_db,
            )

        assert result is None

    def test_logs_usage_on_success(self):
        """call_llm_for_org should log usage after a successful call."""
        from src.llm.org_resolver import call_llm_for_org

        mock_response = self._make_response()
        mock_db = MagicMock()

        with patch("src.llm.org_resolver.build_fallback_chain") as mock_bfc, \
             patch("src.llm.org_resolver.log_usage") as mock_log:
            mock_chain = MagicMock()
            mock_chain.complete.return_value = mock_response
            mock_bfc.return_value = (mock_chain, True)

            call_llm_for_org(
                org_id=42,
                task_type="insights",
                request=self._make_request(),
                provider="anthropic",
                model="claude-haiku-4-5",
                db=mock_db,
            )

        mock_log.assert_called_once()
        call_args = mock_log.call_args[0]
        assert call_args[0] == 42  # org_id
        assert call_args[2] == "insights"  # task_type
        assert call_args[3] is True  # is_byok


class TestBuildFallbackChainOrgResolver:
    """Tests for build_fallback_chain in org_resolver — BYOK-only."""

    def test_returns_none_when_no_byok_key(self):
        """Should return (None, False) when org has no OrgApiKey row."""
        from src.llm.org_resolver import build_fallback_chain

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = None

        chain, is_byok = build_fallback_chain(1, "openai", "gpt-4o-mini", mock_db)

        assert chain is None
        assert is_byok is False

    def test_returns_chain_when_byok_key_exists(self):
        """Should return a chain and is_byok=True when a valid BYOK key is present."""
        from src.llm.org_resolver import build_fallback_chain

        mock_key = MagicMock()
        mock_key.encrypted_key = "encrypted-stub"

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_key

        with patch("src.llm.org_resolver._decrypt_api_key", return_value="sk-byok-key"), \
             patch("src.llm.org_resolver.LLMProviderFactory") as mock_factory:
            mock_factory.create.return_value = MagicMock()
            chain, is_byok = build_fallback_chain(1, "openai", "gpt-4o-mini", mock_db)

        assert chain is not None
        assert is_byok is True

    def test_returns_none_when_byok_key_decryption_fails(self):
        """Should return (None, False) when key exists but cannot be decrypted."""
        from src.llm.org_resolver import build_fallback_chain

        mock_key = MagicMock()
        mock_key.encrypted_key = "bad-encrypted-data"

        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = mock_key

        with patch("src.llm.org_resolver._decrypt_api_key", return_value=""):
            chain, is_byok = build_fallback_chain(1, "openai", "gpt-4o-mini", mock_db)

        assert chain is None
        assert is_byok is False
