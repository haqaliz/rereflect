"""
Aspect 2 / Task 1 RED: Tests for LocalEmbeddingProvider.

In-process, CPU, air-gappable embedding provider using sentence-transformers.
Mirrors the M5.1 TransformerSentimentProvider lazy-singleton pattern:
  - model is loaded lazily (never in __init__)
  - loaded once per process, cached across instances (module-level cache)
  - offline env vars (HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE) force
    local_files_only=True so no network call is attempted
  - dimension is derived from the actual output, never hardcoded

NO factory/settings wiring here (Task 2) — this only exercises the class directly.
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def stub_sentence_transformers(request):
    """Make `sentence_transformers` patchable without installing it.

    Every test below patches `sentence_transformers.SentenceTransformer` with a
    MagicMock — none of them exercise the real library, they exercise this
    repo's provider logic (lazy load, caching, offline env, 2-D coercion).
    But `mock.patch` has to import the target module to patch it, so without
    the package installed all seven fail with ModuleNotFoundError.

    `sentence-transformers` pulls in torch (~2 GB), which we do not want in the
    unit-test CI job. So when the real package is absent we register a minimal
    stub module for the duration of the test. When it IS installed (the
    real-model smoke test below needs it) this fixture does nothing.
    """
    import sys

    # The real-model smoke test genuinely needs the real library — it must keep
    # skipping (not silently pass against a MagicMock) when it is absent.
    if request.node.get_closest_marker("needs_real_sentence_transformers"):
        yield
        return

    if "sentence_transformers" in sys.modules:
        yield
        return

    try:
        import sentence_transformers  # noqa: F401
    except ModuleNotFoundError:
        pass
    else:
        yield
        return

    import types as _types

    stub = _types.ModuleType("sentence_transformers")
    stub.SentenceTransformer = MagicMock(name="SentenceTransformer")
    sys.modules["sentence_transformers"] = stub
    try:
        yield
    finally:
        sys.modules.pop("sentence_transformers", None)


def _reload_local_provider_module():
    """Reload the module under test so its module-level loader cache
    (_loaded_models) starts empty for each test — the cache is process-global
    by design (mirrors transformer.py), so tests must reset it explicitly
    rather than relying on import caching."""
    import src.services.embeddings.providers.local as local_module

    importlib.reload(local_module)
    return local_module


class TestLocalEmbeddingProviderEmbed:
    """AC1 + AC4: embed() returns a flat list[float]; dimension is derived."""

    def test_embed_returns_flat_list_and_dimension(self):
        module = _reload_local_provider_module()

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1, 0.2, 0.3, 0.4])
        mock_cls = MagicMock(return_value=mock_model)

        with patch("sentence_transformers.SentenceTransformer", mock_cls):
            provider = module.LocalEmbeddingProvider()
            result = provider.embed("hi")

        assert result == pytest.approx([0.1, 0.2, 0.3, 0.4])
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)
        assert provider.dimension == 4

    def test_2d_single_row_output_coerced_to_1d(self):
        """AC4: a single-string .encode() returning shape (1, n) must be
        coerced to a flat 1-D list, not a nested list."""
        module = _reload_local_provider_module()

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[0.5, 0.6, 0.7]])
        mock_cls = MagicMock(return_value=mock_model)

        with patch("sentence_transformers.SentenceTransformer", mock_cls):
            provider = module.LocalEmbeddingProvider()
            result = provider.embed("hi")

        assert result == pytest.approx([0.5, 0.6, 0.7])
        assert all(isinstance(v, float) for v in result)
        assert provider.dimension == 3


class TestLocalEmbeddingProviderLazyLoad:
    """AC2: __init__ must not construct/load the model."""

    def test_init_does_not_construct_model(self):
        module = _reload_local_provider_module()

        mock_cls = MagicMock()

        with patch("sentence_transformers.SentenceTransformer", mock_cls):
            module.LocalEmbeddingProvider()
            assert mock_cls.call_count == 0

    def test_dimension_before_embed_is_zero(self):
        module = _reload_local_provider_module()
        provider = module.LocalEmbeddingProvider()
        assert provider.dimension == 0


class TestLocalEmbeddingProviderOfflineEnv:
    """AC3: HF_HUB_OFFLINE=1 forces local_files_only=True on the loader."""

    def test_offline_env_sets_local_files_only_true(self, monkeypatch):
        module = _reload_local_provider_module()
        monkeypatch.setenv("HF_HUB_OFFLINE", "1")

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1, 0.2])
        mock_cls = MagicMock(return_value=mock_model)

        with patch("sentence_transformers.SentenceTransformer", mock_cls):
            provider = module.LocalEmbeddingProvider()
            provider.embed("hi")

        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs.get("local_files_only") is True
        assert call_kwargs.get("device") == "cpu"

    def test_online_env_sets_local_files_only_false(self, monkeypatch):
        module = _reload_local_provider_module()
        monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
        monkeypatch.delenv("TRANSFORMERS_OFFLINE", raising=False)

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1, 0.2])
        mock_cls = MagicMock(return_value=mock_model)

        with patch("sentence_transformers.SentenceTransformer", mock_cls):
            provider = module.LocalEmbeddingProvider()
            provider.embed("hi")

        call_kwargs = mock_cls.call_args.kwargs
        assert call_kwargs.get("local_files_only") is False


class TestLocalEmbeddingProviderCaching:
    """AC5: two embed() calls with the same model id construct the model once."""

    def test_model_constructed_once_across_instances(self):
        module = _reload_local_provider_module()

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1, 0.2, 0.3])
        mock_cls = MagicMock(return_value=mock_model)

        with patch("sentence_transformers.SentenceTransformer", mock_cls):
            provider_a = module.LocalEmbeddingProvider()
            provider_b = module.LocalEmbeddingProvider()
            provider_a.embed("hello")
            provider_b.embed("world")

        assert mock_cls.call_count == 1

    def test_model_constructed_once_across_multiple_embed_calls_same_instance(self):
        module = _reload_local_provider_module()

        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([0.1, 0.2, 0.3])
        mock_cls = MagicMock(return_value=mock_model)

        with patch("sentence_transformers.SentenceTransformer", mock_cls):
            provider = module.LocalEmbeddingProvider()
            provider.embed("hello")
            provider.embed("world")

        assert mock_cls.call_count == 1


class TestLocalEmbeddingProviderRealModelSmoke:
    """AC6: one real-model smoke test — SKIP (not FAIL) when unavailable
    (no network / no cached weights), so no-network CI stays green."""

    @pytest.mark.needs_real_sentence_transformers
    def test_real_model_loads_and_embeds(self):
        pytest.importorskip("sentence_transformers")

        module = _reload_local_provider_module()

        try:
            provider = module.LocalEmbeddingProvider()
            result = provider.embed("This is a real smoke test sentence.")
        except Exception as exc:  # noqa: BLE001 - any load/network failure -> skip
            pytest.skip(f"Real model unavailable (no network/cache?): {exc}")

        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(v, float) for v in result)
        assert provider.dimension == len(result)
