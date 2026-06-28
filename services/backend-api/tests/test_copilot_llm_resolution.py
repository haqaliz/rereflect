"""
Phase 1 TDD — LLM resolution for Copilot generation.

Tests for src/services/copilot/llm_resolver.py:
- Local org (openai_compatible + base_url, no key) → usable config, is_configured=True
- Cloud org (openai + valid BYOK key) → key-based config, is_configured=True
- Unconfigured org (no key AND no base_url) → is_configured=False, no crash

Also tests that copilot_ws._handle_query:
- Local org can proceed without a key (no early-return WS error)
- Unconfigured org receives an honest "configure a model" WS error, no 500
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ── Unit tests for the resolver helper ───────────────────────────────────────


class TestLLMResolverImport:
    """The resolver module must be importable before any usage."""

    def test_module_importable(self):
        from src.services.copilot.llm_resolver import resolve_generation_llm, LLMConfig  # noqa: F401

    def test_llm_config_is_dataclass(self):
        from src.services.copilot.llm_resolver import LLMConfig
        import dataclasses
        assert dataclasses.is_dataclass(LLMConfig)

    def test_llm_config_has_required_fields(self):
        from src.services.copilot.llm_resolver import LLMConfig
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(LLMConfig)}
        assert "provider" in field_names
        assert "model" in field_names
        assert "api_key" in field_names
        assert "base_url" in field_names
        assert "is_configured" in field_names


class TestResolveGenerationLLM:
    """Resolver returns the right config for each org type."""

    def _make_mock_db(self, ai_config=None):
        mock_db = MagicMock()
        mock_db.query.return_value.filter_by.return_value.first.return_value = ai_config
        return mock_db

    def test_local_provider_with_base_url_no_key_is_configured(self):
        """openai_compatible + base_url + no BYOK key → is_configured=True, api_key=None."""
        from src.services.copilot.llm_resolver import resolve_generation_llm

        # Simulate OrgAIConfig with local provider
        ai_cfg = MagicMock()
        ai_cfg.default_provider = "openai_compatible"
        ai_cfg.model_analysis = "llama3"
        ai_cfg.base_url = "http://localhost:11434/v1"

        mock_db = self._make_mock_db(ai_config=ai_cfg)

        result = resolve_generation_llm(org_id=1, db=mock_db)

        assert result.is_configured is True
        assert result.provider == "openai_compatible"
        assert result.model == "llama3"
        assert result.base_url == "http://localhost:11434/v1"
        assert result.api_key is None  # keyless local

    def test_ollama_provider_with_base_url_is_configured(self):
        """ollama + base_url → is_configured=True, keyless."""
        from src.services.copilot.llm_resolver import resolve_generation_llm

        ai_cfg = MagicMock()
        ai_cfg.default_provider = "ollama"
        ai_cfg.model_analysis = "mistral"
        ai_cfg.base_url = "http://localhost:11434/v1"

        mock_db = self._make_mock_db(ai_config=ai_cfg)

        result = resolve_generation_llm(org_id=2, db=mock_db)

        assert result.is_configured is True
        assert result.provider == "ollama"
        assert result.api_key is None
        assert result.base_url is not None

    def test_cloud_provider_with_byok_key_is_configured(self):
        """openai + valid BYOK key → is_configured=True, api_key set, base_url=None."""
        from src.services.copilot.llm_resolver import resolve_generation_llm

        ai_cfg = MagicMock()
        ai_cfg.default_provider = "openai"
        ai_cfg.model_analysis = "gpt-4o-mini"
        ai_cfg.base_url = None

        mock_db = self._make_mock_db(ai_config=ai_cfg)

        with patch("src.utils.byok.resolve_org_byok_key", return_value="sk-test-123"):
            result = resolve_generation_llm(org_id=3, db=mock_db)

        assert result.is_configured is True
        assert result.api_key == "sk-test-123"
        assert result.base_url is None

    def test_local_provider_without_base_url_is_unconfigured(self):
        """openai_compatible with no base_url → is_configured=False (no crash)."""
        from src.services.copilot.llm_resolver import resolve_generation_llm

        ai_cfg = MagicMock()
        ai_cfg.default_provider = "openai_compatible"
        ai_cfg.model_analysis = "llama3"
        ai_cfg.base_url = None  # Missing!

        mock_db = self._make_mock_db(ai_config=ai_cfg)

        result = resolve_generation_llm(org_id=4, db=mock_db)

        assert result.is_configured is False
        assert result.api_key is None
        # Must not raise

    def test_cloud_provider_without_key_is_unconfigured(self):
        """openai with no BYOK key → is_configured=False (no crash, no env fallback)."""
        from src.services.copilot.llm_resolver import resolve_generation_llm

        ai_cfg = MagicMock()
        ai_cfg.default_provider = "openai"
        ai_cfg.model_analysis = "gpt-4o-mini"
        ai_cfg.base_url = None

        mock_db = self._make_mock_db(ai_config=ai_cfg)

        with patch("src.utils.byok.resolve_org_byok_key", return_value=None):
            result = resolve_generation_llm(org_id=5, db=mock_db)

        assert result.is_configured is False
        assert result.api_key is None

    def test_no_org_ai_config_row_uses_defaults_with_byok(self):
        """No OrgAIConfig row → defaults to openai; if BYOK key exists, is_configured."""
        from src.services.copilot.llm_resolver import resolve_generation_llm

        # No config row
        mock_db = self._make_mock_db(ai_config=None)

        with patch("src.utils.byok.resolve_org_byok_key", return_value="sk-env-key"):
            result = resolve_generation_llm(org_id=6, db=mock_db)

        assert result.is_configured is True
        assert result.api_key == "sk-env-key"
        assert result.provider == "openai"

    def test_no_org_ai_config_and_no_key_is_unconfigured(self):
        """No OrgAIConfig and no BYOK key → is_configured=False."""
        from src.services.copilot.llm_resolver import resolve_generation_llm

        mock_db = self._make_mock_db(ai_config=None)

        with patch("src.utils.byok.resolve_org_byok_key", return_value=None):
            result = resolve_generation_llm(org_id=7, db=mock_db)

        assert result.is_configured is False


# ── Integration-style tests through _handle_query ─────────────────────────────


def _async_generator(items):
    """Build an async generator that yields mock chunks."""
    async def _gen():
        for item in items:
            yield item
    return _gen()


class TestHandleQueryLocalOrg:
    """
    _handle_query with a local-LLM org must proceed without a BYOK key.
    The new resolver must not early-return an error for keyless local orgs.
    """

    def _make_mock_org(self, org_id=99):
        org = MagicMock()
        org.id = org_id
        return org

    def _make_mock_user(self):
        user = MagicMock()
        user.id = 1
        return user

    def _make_mock_conv(self):
        conv = MagicMock()
        conv.id = 1
        return conv

    def _make_mock_db(self):
        db = MagicMock()
        db.execute.return_value = MagicMock()
        # query().filter_by().first() used for plan, OrgAIConfig, etc.
        mock_sub = MagicMock()
        mock_sub.plan = "pro"
        db.query.return_value.filter_by.return_value.first.return_value = mock_sub
        # query().filter().order_by().limit().all() for conversation history
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        return db

    @pytest.mark.asyncio
    async def test_local_org_does_not_receive_byok_error(self):
        """
        A local-configured org (openai_compatible + base_url, no key) must not
        receive an early error WS message.  The handler proceeds to streaming.
        """
        from src.api.routes.copilot_ws import _handle_query

        mock_ws = AsyncMock()
        mock_db = self._make_mock_db()
        mock_org = self._make_mock_org()
        mock_user = self._make_mock_user()
        mock_conv = self._make_mock_conv()

        from src.services.copilot.llm_resolver import LLMConfig
        local_config = LLMConfig(
            provider="openai_compatible",
            model="llama3",
            api_key=None,
            base_url="http://localhost:11434/v1",
            is_configured=True,
        )

        mock_chunks = [
            MagicMock(choices=[MagicMock(delta=MagicMock(content="result"))])
        ]

        with patch("src.services.copilot.llm_resolver.resolve_generation_llm", return_value=local_config), \
             patch("src.api.routes.copilot_ws.resolve_generation_llm", return_value=local_config), \
             patch("src.api.routes.copilot_ws.call_llm_stream",
                   side_effect=lambda **kwargs: _async_generator(mock_chunks)), \
             patch("src.api.routes.copilot_ws.TemplateMatcher"), \
             patch("src.api.routes.copilot_ws.TemplateSaver"), \
             patch("src.api.routes.copilot_ws.resolve_embedding_provider", return_value=None), \
             patch("src.api.routes.copilot_ws.IntentClassifier") as MockClassifier, \
             patch("src.api.routes.copilot_ws.ContextResolver") as MockResolver:

            MockClassifier.return_value.classify.return_value = {
                "intent": "general", "confidence": 0.9, "reason": ""
            }
            MockResolver.return_value.parse_mentions.return_value = []
            MockResolver.return_value.build_context.return_value = "ctx"

            try:
                await _handle_query(
                    websocket=mock_ws,
                    db=mock_db,
                    user=mock_user,
                    org=mock_org,
                    conversation=mock_conv,
                    content="hello",
                    context_scope="all_data",
                    message_id="msg_local_1",
                )
            except Exception:
                pass

        # Should NOT have received an error about BYOK / API key.
        # manager.send(websocket, data) calls websocket.send_json(data) with 1 positional arg.
        all_sent = [
            c.args[0] if c.args else next(iter(c.kwargs.values()), {})
            for c in mock_ws.send_json.call_args_list
        ]
        error_msgs = [m for m in all_sent if isinstance(m, dict) and m.get("type") == "error"]
        byok_errors = [m for m in error_msgs if "key" in m.get("message", "").lower()]
        assert len(byok_errors) == 0, (
            f"Local org should not get BYOK error; got: {byok_errors}"
        )

    @pytest.mark.asyncio
    async def test_unconfigured_org_receives_configure_model_message(self):
        """
        An org with no key AND no base_url must receive an honest
        'configure a model' message — not a crash or BYOK error.
        """
        from src.api.routes.copilot_ws import _handle_query
        from src.services.copilot.llm_resolver import LLMConfig

        mock_ws = AsyncMock()
        mock_db = self._make_mock_db()
        mock_org = self._make_mock_org()
        mock_user = self._make_mock_user()
        mock_conv = self._make_mock_conv()

        unconfigured = LLMConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key=None,
            base_url=None,
            is_configured=False,
        )

        with patch("src.api.routes.copilot_ws.resolve_generation_llm", return_value=unconfigured), \
             patch("src.api.routes.copilot_ws.resolve_embedding_provider", return_value=None), \
             patch("src.api.routes.copilot_ws.IntentClassifier") as MockClassifier, \
             patch("src.api.routes.copilot_ws.ContextResolver") as MockResolver:

            MockClassifier.return_value.classify.return_value = {
                "intent": "general", "confidence": 0.9, "reason": ""
            }
            MockResolver.return_value.parse_mentions.return_value = []
            MockResolver.return_value.build_context.return_value = "ctx"

            try:
                await _handle_query(
                    websocket=mock_ws,
                    db=mock_db,
                    user=mock_user,
                    org=mock_org,
                    conversation=mock_conv,
                    content="hello",
                    context_scope="all_data",
                    message_id="msg_unconfig_1",
                )
            except Exception:
                pass

        # manager.send(websocket, data) calls websocket.send_json(data) with 1 positional arg.
        all_sent = [
            c.args[0] if c.args else next(iter(c.kwargs.values()), {})
            for c in mock_ws.send_json.call_args_list
        ]
        error_msgs = [m for m in all_sent if isinstance(m, dict) and m.get("type") == "error"]
        assert len(error_msgs) >= 1, "Unconfigured org must send an error WS message"

        # The message must reference "Settings" or "configure" — not a stack trace
        combined = " ".join(
            (m.get("message", "") + m.get("error", "")).lower()
            for m in error_msgs
        )
        assert "settings" in combined or "configure" in combined or "model" in combined, (
            f"Error must reference settings/configure/model, got: {error_msgs}"
        )
