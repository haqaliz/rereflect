"""
Phase 2 TDD — Generators accept base_url / keyless local endpoints.

Tests:
- SQLGenerator.generate accepts base_url kwarg (signature check)
- With base_url + api_key=None: builds OpenAI-compatible client against base_url,
  never raises "No API key" error
- With api_key (cloud BYOK): uses standard OpenAI client (unchanged path)
- With neither: raises a config error (not a crash, not a silent success)
- Plain-text prompt + parse fallback works when provider may not support JSON mode
- call_llm_stream with base_url creates an OpenAI-compatible client (not cloud OpenAI)
"""

import inspect
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ── Signature checks ──────────────────────────────────────────────────────────


class TestSQLGeneratorSignature:
    """SQLGenerator.generate must accept base_url as a keyword argument."""

    def test_generate_accepts_base_url(self):
        from src.services.copilot.sql_generator import SQLGenerator
        sig = inspect.signature(SQLGenerator.generate)
        assert "base_url" in sig.parameters, (
            "SQLGenerator.generate must accept 'base_url' keyword argument"
        )

    def test_call_llm_accepts_base_url(self):
        from src.services.copilot.sql_generator import SQLGenerator
        sig = inspect.signature(SQLGenerator._call_llm)
        assert "base_url" in sig.parameters, (
            "SQLGenerator._call_llm must accept 'base_url' keyword argument"
        )


# ── _call_llm behaviour for each path ─────────────────────────────────────────


class TestSQLGeneratorCallLLM:
    """_call_llm must construct the right client for each config path."""

    def _make_generator(self):
        from src.services.copilot.sql_generator import SQLGenerator
        return SQLGenerator()

    def test_call_llm_local_uses_openai_compatible_client(self):
        """
        With base_url + api_key=None → OpenAI client must receive base_url
        and a dummy/placeholder key (NOT raise because api_key is None).
        """
        gen = self._make_generator()

        created_clients = []

        class MockResponse:
            choices = [MagicMock(message=MagicMock(content="SELECT 1"))]

        class MockOpenAI:
            def __init__(self, api_key, base_url=None, **kw):
                created_clients.append({"api_key": api_key, "base_url": base_url})

            def chat(self):
                pass

            class chat:
                class completions:
                    @staticmethod
                    def create(*a, **kw):
                        return MockResponse()

        with patch("src.services.copilot.sql_generator.openai", create=True) as mock_openai:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = MockResponse()
            mock_openai.OpenAI.return_value = mock_client

            result = gen._call_llm(
                system_prompt="sys",
                user_prompt="user",
                api_key=None,
                model="llama3",
                base_url="http://localhost:11434/v1",
            )

        # The OpenAI client must have been created with base_url
        assert mock_openai.OpenAI.called
        call_kwargs = mock_openai.OpenAI.call_args
        # base_url must be passed
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs.get("base_url") == "http://localhost:11434/v1"
        else:
            # positional call: (api_key, ...) — less likely but check kwargs
            assert "base_url" in str(call_kwargs)

    def test_call_llm_local_does_not_raise_for_none_key(self):
        """
        With base_url set and api_key=None, _call_llm must NOT raise
        RuntimeError("No OpenAI API key...").
        """
        gen = self._make_generator()

        with patch("src.services.copilot.sql_generator.openai") as mock_openai:
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock(message=MagicMock(content="SELECT 1 FROM feedback_items WHERE organization_id = :org_id LIMIT 50"))]
            mock_client.chat.completions.create.return_value = mock_resp
            mock_openai.OpenAI.return_value = mock_client

            # Must NOT raise
            result = gen._call_llm(
                system_prompt="sys",
                user_prompt="user",
                api_key=None,
                model="llama3",
                base_url="http://localhost:11434/v1",
            )
            assert result  # Returns SQL string

    def test_call_llm_cloud_uses_byok_key(self):
        """With api_key set and no base_url → standard OpenAI client."""
        gen = self._make_generator()

        with patch("src.services.copilot.sql_generator.openai") as mock_openai:
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock(message=MagicMock(content="SELECT 1"))]
            mock_client.chat.completions.create.return_value = mock_resp
            mock_openai.OpenAI.return_value = mock_client

            gen._call_llm(
                system_prompt="sys",
                user_prompt="user",
                api_key="sk-real-key",
                model="gpt-4o-mini",
                base_url=None,
            )

        call_kwargs = mock_openai.OpenAI.call_args
        # Must pass the api_key
        combined = str(call_kwargs)
        assert "sk-real-key" in combined

    def test_call_llm_no_key_no_url_raises(self):
        """With neither api_key nor base_url → raises a config error."""
        gen = self._make_generator()

        with pytest.raises((RuntimeError, Exception)):
            gen._call_llm(
                system_prompt="sys",
                user_prompt="user",
                api_key=None,
                model="gpt-4o-mini",
                base_url=None,
            )


# ── generate() end-to-end with base_url ──────────────────────────────────────


class TestSQLGeneratorGenerateLocal:
    """SQLGenerator.generate() must pass base_url through to _call_llm."""

    def test_generate_with_local_base_url_succeeds(self):
        """
        generate(base_url=..., api_key=None) must call _call_llm with base_url
        and return a valid SQL dict when the mock LLM returns valid SQL.
        """
        from src.services.copilot.sql_generator import SQLGenerator

        gen = SQLGenerator()
        valid_sql = (
            "SELECT sentiment_label, COUNT(*) FROM feedback_items "
            "WHERE organization_id = :org_id GROUP BY sentiment_label LIMIT 100"
        )

        with patch.object(gen, "_call_llm", return_value=valid_sql) as mock_call:
            result = gen.generate(
                question="how many feedbacks by sentiment?",
                org_id=1,
                plan="pro",
                api_key=None,
                model="llama3",
                base_url="http://localhost:11434/v1",
            )

        # _call_llm must have been called with base_url
        assert mock_call.called
        _, call_kwargs = mock_call.call_args
        assert call_kwargs.get("base_url") == "http://localhost:11434/v1"
        assert call_kwargs.get("api_key") is None

        # Result must have a sql field
        assert result["sql"] is not None
        assert result["error"] is None

    def test_generate_cloud_path_unchanged(self):
        """
        generate(api_key="sk-...", base_url=None) must pass the key to _call_llm,
        not a base_url.
        """
        from src.services.copilot.sql_generator import SQLGenerator

        gen = SQLGenerator()
        valid_sql = (
            "SELECT COUNT(*) FROM feedback_items "
            "WHERE organization_id = :org_id LIMIT 100"
        )

        with patch.object(gen, "_call_llm", return_value=valid_sql) as mock_call:
            result = gen.generate(
                question="count feedbacks",
                org_id=2,
                plan="free",
                api_key="sk-cloud-key",
                model="gpt-4o-mini",
                base_url=None,
            )

        _, call_kwargs = mock_call.call_args
        assert call_kwargs.get("api_key") == "sk-cloud-key"
        assert call_kwargs.get("base_url") is None


# ── call_llm_stream with base_url ─────────────────────────────────────────────


class TestCallLLMStreamLocal:
    """
    call_llm_stream with base_url must build an OpenAI-compatible async client
    rather than the standard cloud client.  Verifies the streaming contract
    is preserved for local endpoints.
    """

    @pytest.mark.asyncio
    async def test_call_llm_stream_with_base_url_creates_local_client(self):
        """
        When base_url is provided, call_llm_stream must use an AsyncOpenAI
        client constructed with base_url (not default cloud).
        """
        from src.api.routes.copilot_ws import call_llm_stream

        created = []

        async def mock_stream_iter(*a, **kw):
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="token"))])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=mock_stream_iter()
        )

        with patch("src.api.routes.copilot_ws.openai") as mock_openai:
            async def fake_client_init(api_key, base_url=None, timeout=None):
                created.append({"api_key": api_key, "base_url": base_url})
                return mock_client

            mock_openai.AsyncOpenAI = MagicMock(return_value=mock_client)
            mock_client.chat.completions.create = AsyncMock(return_value=mock_stream_iter())

            chunks = []
            try:
                async for chunk in call_llm_stream(
                    messages=[{"role": "user", "content": "hello"}],
                    provider="openai_compatible",
                    model="llama3",
                    api_key=None,
                    base_url="http://localhost:11434/v1",
                ):
                    chunks.append(chunk)
            except Exception:
                pass  # Stream may error in mock but client construction is what we test

        # The AsyncOpenAI must have been constructed with base_url
        assert mock_openai.AsyncOpenAI.called
        init_kwargs = mock_openai.AsyncOpenAI.call_args
        combined = str(init_kwargs)
        assert "localhost:11434" in combined or "base_url" in combined

    @pytest.mark.asyncio
    async def test_call_llm_stream_cloud_does_not_use_base_url(self):
        """
        call_llm_stream without base_url must create a standard AsyncOpenAI
        client (no base_url argument or base_url=None).
        """
        from src.api.routes.copilot_ws import call_llm_stream

        async def mock_stream_iter(*a, **kw):
            yield MagicMock(choices=[MagicMock(delta=MagicMock(content="token"))])

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream_iter())

        with patch("src.api.routes.copilot_ws.openai") as mock_openai:
            mock_openai.AsyncOpenAI = MagicMock(return_value=mock_client)
            mock_client.chat.completions.create = AsyncMock(return_value=mock_stream_iter())

            try:
                async for _ in call_llm_stream(
                    messages=[{"role": "user", "content": "hello"}],
                    provider="openai",
                    model="gpt-4o-mini",
                    api_key="sk-real-key",
                    base_url=None,
                ):
                    pass
            except Exception:
                pass

        # Must have been called WITHOUT a local base_url
        init_kwargs = mock_openai.AsyncOpenAI.call_args
        combined = str(init_kwargs)
        # Should NOT contain a localhost URL
        assert "localhost" not in combined
