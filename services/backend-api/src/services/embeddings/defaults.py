"""
Provider → default embedding model lookup.

Pure helper, no route/DB imports. Mirrors
src/api/routes/ai_settings.py::_default_embedding_model exactly (see that
function's docstring) — this module exists so resolver.py (and later,
template-mapping consumers) can compute the effective embedding model
without importing a route module.

Do NOT change these literal values without also updating
ai_settings.py::_default_embedding_model to match; the two are intentionally
kept independent (no shared import) per the Task 1 brief, so keep them in sync
by hand.
"""

from __future__ import annotations

from typing import Optional


def default_model_for_provider(provider: str) -> Optional[str]:
    """
    Return the default embedding model id for a provider when no per-org
    override (OrgAIConfig.model_embeddings) is configured.

    Args:
        provider: Provider name string (e.g. "openai", "ollama").

    Returns:
        The default model id for "openai", "google", "ollama".
        None for "openai_compatible" (caller must supply one — no sane
        default for an arbitrary compatible endpoint), "anthropic" (no
        embeddings API), and any unrecognized provider string.
    """
    if provider == "openai":
        from src.services.embeddings.providers.openai import OpenAIEmbeddingProvider

        return OpenAIEmbeddingProvider.DEFAULT_MODEL
    if provider == "google":
        from src.services.embeddings.providers.google import GoogleEmbeddingProvider

        return GoogleEmbeddingProvider.DEFAULT_MODEL
    if provider == "ollama":
        return "nomic-embed-text"
    if provider == "local":
        from src.services.embeddings.providers.local import LocalEmbeddingProvider

        return LocalEmbeddingProvider.DEFAULT_MODEL
    return None
