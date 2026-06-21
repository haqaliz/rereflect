"""
Tests for Feature A: Local / Offline LLM (Ollama + OpenAI-compatible endpoint).

TDD sequence: RED first, then production code makes them GREEN.

Covers:
- OpenAICompatibleProvider: constructs with base_url, completes via that URL
- LLMProviderFactory: handles 'ollama' and 'openai_compatible' providers
- org_resolver.build_fallback_chain: keyless local path (no OrgApiKey needed);
  returns None when base_url is missing; cloud BYOK path unchanged
- No env/system LLM key is ever read in the local path
"""

import os
import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# OpenAICompatibleProvider
# ---------------------------------------------------------------------------

class TestOpenAICompatibleProvider:
    """Tests for src.llm.providers.openai_compatible.OpenAICompatibleProvider."""

    def test_constructs_with_base_url(self):
        """Provider must accept base_url and store it."""
        from src.llm.providers.openai_compatible import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(
            base_url="http://localhost:11434/v1",
            model="llama3",
            api_key="ollama",
        )
        assert provider.base_url == "http://localhost:11434/v1"
        assert provider.model == "llama3"

    def test_constructs_with_optional_api_key(self):
        """api_key should be optional; provider stores a dummy if omitted."""
        from src.llm.providers.openai_compatible import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(
            base_url="http://custom.example.com/v1",
            model="phi3",
            api_key=None,
        )
        # Should not raise; api_key stored as some non-None placeholder or ""
        assert provider.base_url == "http://custom.example.com/v1"
        assert provider.model == "phi3"

    def test_openai_client_initialized_with_correct_base_url(self):
        """The underlying OpenAI client must be configured with the provided base_url."""
        with patch("src.llm.providers.openai_compatible.OpenAI") as MockOpenAI:
            from src.llm.providers.openai_compatible import OpenAICompatibleProvider

            provider = OpenAICompatibleProvider(
                base_url="http://localhost:11434/v1",
                model="llama3",
                api_key="ollama",
            )
            # Trigger lazy client creation
            provider._get_client()

        MockOpenAI.assert_called_once()
        call_kwargs = MockOpenAI.call_args.kwargs
        assert call_kwargs.get("base_url") == "http://localhost:11434/v1"

    def test_complete_calls_chat_completions(self):
        """complete() must call the OpenAI-compatible chat.completions.create endpoint."""
        from src.llm.providers.openai_compatible import OpenAICompatibleProvider
        from src.llm.types import LLMRequest

        mock_choice = MagicMock()
        mock_choice.message.content = '{"sentiment_label": "negative"}'
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 50
        mock_usage.completion_tokens = 20
        mock_usage.total_tokens = 70
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("src.llm.providers.openai_compatible.OpenAI", return_value=mock_client):
            provider = OpenAICompatibleProvider(
                base_url="http://localhost:11434/v1",
                model="llama3",
                api_key="ollama",
            )
            request = LLMRequest(
                messages=[{"role": "user", "content": "Analyze this feedback."}],
            )
            response = provider.complete(request)

        mock_client.chat.completions.create.assert_called_once()
        assert response.content == '{"sentiment_label": "negative"}'
        assert response.provider == "openai_compatible"
        assert response.model == "llama3"
        assert response.prompt_tokens == 50
        assert response.completion_tokens == 20
        assert response.total_tokens == 70

    def test_validate_key_returns_true_for_keyless_local(self):
        """
        Local providers don't need a real key; validate_key should succeed
        by making a minimal probe or simply returning (True, "") for local endpoints.
        """
        from src.llm.providers.openai_compatible import OpenAICompatibleProvider

        mock_client = MagicMock()
        mock_client.models.list.return_value = []

        with patch("src.llm.providers.openai_compatible.OpenAI", return_value=mock_client):
            provider = OpenAICompatibleProvider(
                base_url="http://localhost:11434/v1",
                model="llama3",
                api_key="ollama",
            )
            valid, err = provider.validate_key()

        assert valid is True

    def test_is_subclass_of_openai_provider(self):
        """OpenAICompatibleProvider must extend OpenAIProvider to reuse complete() logic."""
        from src.llm.providers.openai_compatible import OpenAICompatibleProvider
        from src.llm.providers.openai import OpenAIProvider

        assert issubclass(OpenAICompatibleProvider, OpenAIProvider)

    def test_response_provider_field_is_openai_compatible(self):
        """LLMResponse.provider must be 'openai_compatible', not 'openai'."""
        from src.llm.providers.openai_compatible import OpenAICompatibleProvider
        from src.llm.types import LLMRequest

        mock_choice = MagicMock()
        mock_choice.message.content = "{}"
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5
        mock_usage.total_tokens = 15
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("src.llm.providers.openai_compatible.OpenAI", return_value=mock_client):
            provider = OpenAICompatibleProvider(
                base_url="http://myendpoint/v1",
                model="mistral",
                api_key=None,
            )
            response = provider.complete(
                LLMRequest(messages=[{"role": "user", "content": "test"}])
            )

        assert response.provider == "openai_compatible"


# ---------------------------------------------------------------------------
# LLMProviderFactory — ollama and openai_compatible
# ---------------------------------------------------------------------------

class TestLLMProviderFactoryLocalProviders:
    """Factory must handle 'ollama' and 'openai_compatible' provider names."""

    def test_factory_creates_ollama_provider(self):
        """create('ollama', ...) must return an OpenAICompatibleProvider."""
        with patch("src.llm.providers.openai_compatible.OpenAI"):
            from src.llm.factory import LLMProviderFactory
            from src.llm.providers.openai_compatible import OpenAICompatibleProvider

            provider = LLMProviderFactory.create(
                "ollama",
                api_key="",
                model="llama3",
            )

        assert isinstance(provider, OpenAICompatibleProvider)

    def test_factory_ollama_default_base_url(self):
        """Ollama preset must default to http://localhost:11434/v1 when no base_url given."""
        with patch("src.llm.providers.openai_compatible.OpenAI"):
            from src.llm.factory import LLMProviderFactory

            provider = LLMProviderFactory.create("ollama", api_key="", model="llama3")

        assert provider.base_url == "http://localhost:11434/v1"

    def test_factory_ollama_overridable_base_url(self):
        """Ollama preset base_url can be overridden via the base_url kwarg."""
        with patch("src.llm.providers.openai_compatible.OpenAI"):
            from src.llm.factory import LLMProviderFactory

            provider = LLMProviderFactory.create(
                "ollama", api_key="", model="llama3",
                base_url="http://remote-ollama:11434/v1",
            )

        assert provider.base_url == "http://remote-ollama:11434/v1"

    def test_factory_creates_openai_compatible_provider(self):
        """create('openai_compatible', ...) must return an OpenAICompatibleProvider."""
        with patch("src.llm.providers.openai_compatible.OpenAI"):
            from src.llm.factory import LLMProviderFactory
            from src.llm.providers.openai_compatible import OpenAICompatibleProvider

            provider = LLMProviderFactory.create(
                "openai_compatible",
                api_key="",
                model="phi3",
                base_url="http://custom.endpoint/v1",
            )

        assert isinstance(provider, OpenAICompatibleProvider)

    def test_factory_openai_compatible_uses_provided_base_url(self):
        """openai_compatible provider must use the provided base_url."""
        with patch("src.llm.providers.openai_compatible.OpenAI"):
            from src.llm.factory import LLMProviderFactory

            provider = LLMProviderFactory.create(
                "openai_compatible",
                api_key="",
                model="phi3",
                base_url="http://my-inference-server/v1",
            )

        assert provider.base_url == "http://my-inference-server/v1"

    def test_factory_openai_compatible_with_api_key(self):
        """openai_compatible may accept an optional api_key for secured endpoints."""
        with patch("src.llm.providers.openai_compatible.OpenAI"):
            from src.llm.factory import LLMProviderFactory

            provider = LLMProviderFactory.create(
                "openai_compatible",
                api_key="my-secret",
                model="phi3",
                base_url="http://secured.endpoint/v1",
            )

        assert provider.api_key == "my-secret"

    def test_factory_unknown_provider_still_raises(self):
        """Factory must still raise ValueError for completely unknown providers."""
        from src.llm.factory import LLMProviderFactory

        with pytest.raises(ValueError, match="Unknown provider"):
            LLMProviderFactory.create("completely_unknown", api_key="", model="model")

    def test_cloud_providers_unchanged(self):
        """Existing cloud providers (openai/anthropic/google) must still work."""
        from src.llm.factory import LLMProviderFactory
        from src.llm.providers.openai import OpenAIProvider
        from src.llm.providers.anthropic import AnthropicProvider
        from src.llm.providers.google import GoogleProvider

        with patch("src.llm.providers.openai.OpenAI"):
            p = LLMProviderFactory.create("openai", "sk-key", "gpt-4o-mini")
        assert isinstance(p, OpenAIProvider)

        with patch("src.llm.providers.anthropic.Anthropic"):
            p = LLMProviderFactory.create("anthropic", "sk-ant-key", "claude-haiku-4-5")
        assert isinstance(p, AnthropicProvider)

        with patch("src.llm.providers.google.genai"):
            p = LLMProviderFactory.create("google", "goog-key", "gemini-2.0-flash")
        assert isinstance(p, GoogleProvider)


# ---------------------------------------------------------------------------
# org_resolver.build_fallback_chain — local (keyless) path
# ---------------------------------------------------------------------------

class TestBuildFallbackChainLocalProviders:
    """
    build_fallback_chain must support a keyless path for local providers.

    Key invariants:
    - ollama/openai_compatible providers do NOT require an OrgApiKey row.
    - If OrgAIConfig.base_url is missing for a local provider → (None, False).
    - Cloud BYOK path is unchanged.
    - No env/system LLM key is ever read.
    """

    def _make_db_with_ai_config(self, org_id, provider, base_url=None):
        """Return a mock db with OrgAIConfig returning the given provider + base_url."""
        mock_config = MagicMock()
        mock_config.default_provider = provider
        mock_config.base_url = base_url
        mock_config.model_categorization = "llama3"

        mock_db = MagicMock()

        def query_side_effect(model_class):
            mock_q = MagicMock()
            mock_q.filter_by.return_value = mock_q
            # OrgAIConfig query returns our config; OrgApiKey query returns None
            from src.models import OrgAIConfig, OrgApiKey
            if model_class is OrgAIConfig:
                mock_q.first.return_value = mock_config
            elif model_class is OrgApiKey:
                mock_q.first.return_value = None  # No BYOK key row needed
            else:
                mock_q.first.return_value = None
            return mock_q

        mock_db.query.side_effect = query_side_effect
        return mock_db, mock_config

    def test_ollama_with_base_url_builds_chain_without_api_key(self):
        """
        When default_provider='ollama' and base_url is set,
        build_fallback_chain must return a valid chain WITHOUT requiring an OrgApiKey row.
        """
        from src.llm.org_resolver import build_fallback_chain
        from src.models import OrgAIConfig

        mock_config = MagicMock(spec=OrgAIConfig)
        mock_config.default_provider = "ollama"
        mock_config.base_url = "http://localhost:11434/v1"
        mock_config.model_categorization = "llama3"

        mock_db = MagicMock()
        mock_q = MagicMock()
        mock_db.query.return_value = mock_q
        mock_q.filter_by.return_value = mock_q
        mock_q.first.return_value = mock_config

        with patch("src.llm.providers.openai_compatible.OpenAI"):
            chain, is_byok = build_fallback_chain(
                org_id=1,
                provider="ollama",
                model="llama3",
                db=mock_db,
                base_url="http://localhost:11434/v1",
            )

        assert chain is not None, "Chain must be built for ollama with a base_url"
        assert is_byok is False, "Local providers are not BYOK — is_byok must be False"

    def test_openai_compatible_with_base_url_builds_chain_without_api_key(self):
        """openai_compatible + base_url → chain built without OrgApiKey."""
        from src.llm.org_resolver import build_fallback_chain

        with patch("src.llm.providers.openai_compatible.OpenAI"):
            chain, is_byok = build_fallback_chain(
                org_id=2,
                provider="openai_compatible",
                model="phi3",
                db=MagicMock(),
                base_url="http://my-custom-server/v1",
            )

        assert chain is not None
        assert is_byok is False

    def test_ollama_without_base_url_returns_none(self):
        """
        When provider='ollama' but base_url is None (not configured),
        build_fallback_chain must return (None, False) — disabled, VADER fallback.
        """
        from src.llm.org_resolver import build_fallback_chain

        chain, is_byok = build_fallback_chain(
            org_id=3,
            provider="ollama",
            model="llama3",
            db=MagicMock(),
            base_url=None,
        )

        assert chain is None, "Missing base_url must disable local provider"
        assert is_byok is False

    def test_openai_compatible_without_base_url_returns_none(self):
        """openai_compatible without base_url → (None, False)."""
        from src.llm.org_resolver import build_fallback_chain

        chain, is_byok = build_fallback_chain(
            org_id=4,
            provider="openai_compatible",
            model="phi3",
            db=MagicMock(),
            base_url=None,
        )

        assert chain is None
        assert is_byok is False

    def test_local_provider_never_reads_env_llm_key(self):
        """
        build_fallback_chain for a local provider must NOT touch any
        OPENAI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_AI_API_KEY env vars.
        """
        from src.llm.org_resolver import build_fallback_chain

        dangerous_env = {
            "OPENAI_API_KEY": "sk-should-never-be-used",
            "ANTHROPIC_API_KEY": "sk-ant-should-never",
            "GOOGLE_AI_API_KEY": "goog-should-never",
        }

        with patch.dict(os.environ, dangerous_env), \
             patch("src.llm.providers.openai_compatible.OpenAI") as MockOpenAI:
            chain, _ = build_fallback_chain(
                org_id=5,
                provider="ollama",
                model="llama3",
                db=MagicMock(),
                base_url="http://localhost:11434/v1",
            )

        # The OpenAI client must NOT have been called with any of the system keys
        assert chain is not None
        if MockOpenAI.call_count > 0:
            for c in MockOpenAI.call_args_list:
                api_key_used = c.kwargs.get("api_key", c.args[0] if c.args else None)
                assert api_key_used not in dangerous_env.values(), (
                    f"Local provider used an env system key: {api_key_used}"
                )

    def test_cloud_byok_path_unchanged_for_openai(self):
        """
        Standard cloud (openai/anthropic/google) BYOK path must still work.
        Regression guard: adding local provider support must not break existing behavior.
        """
        from src.llm.org_resolver import build_fallback_chain

        mock_key_record = MagicMock()
        mock_key_record.encrypted_key = "encrypted-stub"

        mock_db = MagicMock()
        mock_q = MagicMock()
        mock_db.query.return_value = mock_q
        mock_q.filter_by.return_value = mock_q
        mock_q.first.return_value = mock_key_record

        with patch("src.llm.org_resolver._decrypt_api_key", return_value="sk-byok-key"), \
             patch("src.llm.providers.openai.OpenAI"):
            chain, is_byok = build_fallback_chain(
                org_id=10,
                provider="openai",
                model="gpt-4o-mini",
                db=mock_db,
            )

        assert chain is not None
        assert is_byok is True

    def test_local_provider_has_no_system_fallback(self):
        """FallbackChain built for local provider must have _system == None."""
        from src.llm.org_resolver import build_fallback_chain

        with patch("src.llm.providers.openai_compatible.OpenAI"):
            chain, _ = build_fallback_chain(
                org_id=6,
                provider="ollama",
                model="llama3",
                db=MagicMock(),
                base_url="http://localhost:11434/v1",
            )

        assert chain is not None
        assert chain._system is None

    def test_no_env_key_attribute_on_resolver(self):
        """
        Regression guard: org_resolver must not expose any module-level
        OPENAI/ANTHROPIC/GOOGLE API key attributes after the local-LLM addition.
        """
        import src.llm.org_resolver as resolver

        for attr in ("_OPENAI_API_KEY", "_ANTHROPIC_API_KEY", "_GOOGLE_API_KEY",
                     "_SYSTEM_OPENAI_KEY", "_SYSTEM_ANTHROPIC_KEY", "_SYSTEM_GOOGLE_KEY"):
            assert not hasattr(resolver, attr), (
                f"org_resolver must not expose {attr!r} — would violate BYOK-only invariant"
            )
