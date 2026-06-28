"""
Phase 1 RED: Tests for the EmbeddingProvider abstract base interface.

Asserts:
- EmbeddingProvider is abstract (cannot be instantiated directly)
- embed(text: str) -> list[float] is required
- dimension property is required
- Concrete subclass must implement both; omitting either raises TypeError
"""

import pytest
from abc import ABC

from src.services.embeddings.base import EmbeddingProvider


class TestEmbeddingProviderIsAbstract:
    """EmbeddingProvider must be an ABC that cannot be instantiated."""

    def test_cannot_instantiate_directly(self):
        """Direct instantiation must raise TypeError."""
        with pytest.raises(TypeError):
            EmbeddingProvider()

    def test_is_abstract_base_class(self):
        """EmbeddingProvider must be a subclass of ABC."""
        assert issubclass(EmbeddingProvider, ABC)

    def test_embed_is_abstract(self):
        """Subclass omitting embed() must raise TypeError at instantiation."""
        class MissingEmbed(EmbeddingProvider):
            @property
            def dimension(self) -> int:
                return 1536

        with pytest.raises(TypeError, match="embed"):
            MissingEmbed()

    def test_dimension_is_abstract(self):
        """Subclass omitting dimension must raise TypeError at instantiation."""
        class MissingDimension(EmbeddingProvider):
            def embed(self, text: str) -> list:
                return [0.0]

        with pytest.raises(TypeError, match="dimension"):
            MissingDimension()

    def test_concrete_subclass_works(self):
        """Fully implemented subclass must instantiate and work correctly."""
        class ConcreteProvider(EmbeddingProvider):
            def embed(self, text: str) -> list:
                return [0.1, 0.2, 0.3]

            @property
            def dimension(self) -> int:
                return 3

        provider = ConcreteProvider()
        result = provider.embed("hello")
        assert isinstance(result, list)
        assert len(result) == 3
        assert provider.dimension == 3

    def test_embed_signature_accepts_text_string(self):
        """embed() must accept a str argument and return a list."""
        class SimpleProvider(EmbeddingProvider):
            def embed(self, text: str) -> list:
                return [float(ord(c)) for c in text[:3]]

            @property
            def dimension(self) -> int:
                return 3

        provider = SimpleProvider()
        result = provider.embed("abc")
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)
