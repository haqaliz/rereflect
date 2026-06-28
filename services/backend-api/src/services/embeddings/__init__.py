"""
Embeddings package — provider-agnostic embedding abstraction for backend-api.

Public surface:
  EmbeddingProvider          — ABC (for type hints in consumers)
  EmbeddingProviderFactory   — name → provider instance
  resolve_embedding_provider — org_id + db → ResolvedEmbedder | None
  ResolvedEmbedder           — dataclass returned by resolver
"""

from src.services.embeddings.base import EmbeddingProvider
from src.services.embeddings.factory import EmbeddingProviderFactory
from src.services.embeddings.resolver import resolve_embedding_provider, ResolvedEmbedder

__all__ = [
    "EmbeddingProvider",
    "EmbeddingProviderFactory",
    "resolve_embedding_provider",
    "ResolvedEmbedder",
]
