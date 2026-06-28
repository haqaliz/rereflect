"""
Embeddings package — provider-agnostic embedding abstraction for backend-api.

Public surface (populated incrementally as modules are built):
  EmbeddingProvider          — ABC (base interface)
  EmbeddingProviderFactory   — name → provider instance
  resolve_embedding_provider — org_id + db → ResolvedEmbedder | None
  ResolvedEmbedder           — dataclass returned by resolver
"""
