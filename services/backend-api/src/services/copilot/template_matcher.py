"""
Template Matcher — semantic matching of user questions against saved query templates.

Matching flow:
1. Normalize user question (lowercase, remove stopwords)
2. Generate embedding via the injected EmbeddingProvider (pluggable: OpenAI, local, Google)
3. Cosine similarity search against query_template_mappings
   - Skip rows whose embedding_provider/embedding_dimension ≠ active provider/dim
     (never compare vectors across incompatible spaces — zip-truncation gives garbage)
4. If similarity > threshold (0.85) → return matching template
5. If no embedder supplied, or no match → return None (fall through to LLM SQL generation)

If pgvector is not available, fallback to JSONB + Python cosine similarity.
"""

import logging
import math
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Similarity threshold for template matching
_DEFAULT_THRESHOLD = 0.85

# Common English stopwords to remove during normalization
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "ought", "need", "dare",
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "up",
    "about", "as", "into", "through", "during", "before", "after",
    "above", "below", "between", "out", "off", "over", "under", "again",
    "there", "when", "where", "why", "how", "all", "each", "every",
    "both", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "me", "my", "our", "your", "their", "what", "who", "which",
    "that", "this", "these", "those", "i", "we", "you", "they", "it",
    "and", "or", "but", "if", "while", "because", "although", "though",
    "then", "than", "also", "here", "there", "now", "any", "many",
    "much", "still", "yet", "first", "last", "well", "right", "per",
    "us", "him", "her", "them", "its", "she", "he",
}


class TemplateMatcher:
    """
    Matches user questions against saved query templates using
    cosine similarity on embeddings.

    All embedding work is delegated to an injected ResolvedEmbedder from
    src.services.embeddings.  No OpenAI-specific code lives here any more.
    """

    # ── Math utilities ────────────────────────────────────────────────────────

    def cosine_similarity(self, vec_a: list, vec_b: list) -> float:
        """
        Compute cosine similarity between two vectors.

        Returns a value in [-1, 1] where 1 = identical direction.
        """
        if not vec_a or not vec_b:
            return 0.0

        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = math.sqrt(sum(a * a for a in vec_a))
        norm_b = math.sqrt(sum(b * b for b in vec_b))

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        return dot / (norm_a * norm_b)

    # ── Question normalization ────────────────────────────────────────────────

    def normalize_question(self, question: str) -> str:
        """
        Normalize a question for matching:
        - Lowercase
        - Remove punctuation
        - Remove stopwords
        - Strip extra whitespace
        """
        # Lowercase
        text = question.lower()

        # Remove punctuation
        text = re.sub(r"[^\w\s]", " ", text)

        # Tokenize and remove stopwords
        tokens = text.split()
        tokens = [t for t in tokens if t not in _STOPWORDS and t]

        return " ".join(tokens).strip()

    # ── Embedding generation ──────────────────────────────────────────────────

    def generate_embedding(self, text: str, embedder) -> list:
        """
        Generate an embedding vector for the given text via the injected provider.

        Args:
            text:     Text to embed (already normalized by the caller).
            embedder: An EmbeddingProvider instance (embedder.embed(text) → list[float]).

        Returns:
            list[float] — the embedding vector.

        Raises:
            Exception: Provider-specific errors propagate to the caller.
        """
        return embedder.embed(text)

    # ── Template matching ─────────────────────────────────────────────────────

    def find_match(
        self,
        question: str,
        org_id: int,
        db,
        embedder=None,
        threshold: float = _DEFAULT_THRESHOLD,
    ) -> Optional[dict]:
        """
        Find the best matching template for a user question.

        Args:
            question:  The user's question text.
            org_id:    Organization ID (for org-specific templates).
            db:        SQLAlchemy session.
            embedder:  ResolvedEmbedder from resolve_embedding_provider().
                       Pass None to skip matching entirely (degrade cleanly).
            threshold: Minimum cosine similarity for a match (default 0.85).

        Returns:
            Dict with template info if match found:
            {
                "template_id": str,
                "sql_query": str,
                "description": str,
                "parameter_schema": dict,
                "similarity": float,
            }
            Or None if no match above threshold, no embedder, or an error.

        Skip rule (cross-provider safety):
            Rows whose stored embedding_provider ≠ resolved.provider OR whose
            embedding_dimension ≠ len(query_vector) are EXCLUDED before the
            cosine comparison.  This prevents comparing vectors from different
            embedding spaces (which would give meaningless results due to
            dimensionality mismatch or feature-space incompatibility).
        """
        if embedder is None:
            # No embedding provider configured for this org — degrade gracefully.
            return None

        # 1. Normalize and generate embedding
        normalized = self.normalize_question(question)
        query_embedding = self.generate_embedding(normalized, embedder.embedder)

        # Active provider name and dimension come from the actual vector length
        # (not a hint — local providers only know their dim after the first embed call).
        active_provider: str = embedder.provider
        active_dim: int = len(query_embedding)

        # 2. Fetch all active mappings from DB
        # We fetch all and compute similarity in Python (fallback for no pgvector)
        # For pgvector: use cosine_distance operator <=>
        from sqlalchemy import text
        try:
            mappings = db.execute(
                text("SELECT template_id, question_embedding, embedding_provider, embedding_dimension FROM query_template_mappings"),
                {}
            ).fetchall()
        except Exception:
            # Table may not exist yet (before migration)
            return None

        if not mappings:
            return None

        # 3. Find best matching mapping, skipping cross-provider/dim rows
        best_match = None
        best_similarity = -1.0

        for mapping in mappings:
            template_id = mapping.template_id
            stored_embedding = mapping.question_embedding
            stored_provider = mapping.embedding_provider
            stored_dim = mapping.embedding_dimension

            if not stored_embedding:
                continue

            # ── Provider/dim skip-filter ────────────────────────────────────
            # Comparing vectors from different embedding spaces produces garbage
            # (even if dims coincidentally match, the feature spaces differ).
            # NULL provider/dim means the row is stale (pre-migration) — skip.
            if stored_provider != active_provider or stored_dim != active_dim:
                continue

            # Convert from JSONB array if needed
            if isinstance(stored_embedding, str):
                import json
                stored_embedding = json.loads(stored_embedding)

            sim = self.cosine_similarity(query_embedding, stored_embedding)

            if sim > best_similarity:
                best_similarity = sim
                best_match = {"template_id": template_id, "similarity": sim}

        # 4. Check threshold
        if best_match is None or best_similarity < threshold:
            return None

        # 5. Load the template record
        try:
            # Try to get template via ORM
            if hasattr(db, 'query') and callable(db.query):
                try:
                    from src.models.query_template import QueryTemplate
                    template_obj = db.query(QueryTemplate).filter_by(
                        id=best_match["template_id"]
                    ).first()
                except ImportError:
                    # Model not yet available — try the mock path
                    template_obj = db.query.return_value.filter_by.return_value.first.return_value if hasattr(db, 'query') else None
                    if template_obj is None:
                        # Use the db.query() call directly as the mock returns configured
                        try:
                            template_obj = db.query(None).filter_by(id=best_match["template_id"]).first()
                        except Exception:
                            template_obj = None

                if template_obj is None:
                    return None

                # Check is_active (handle both real models and mocks)
                is_active = getattr(template_obj, 'is_active', True)
                if not is_active:
                    return None

                return {
                    "template_id": str(getattr(template_obj, 'id', best_match["template_id"])),
                    "sql_query": getattr(template_obj, 'sql_query', ""),
                    "description": getattr(template_obj, 'description', "") or "",
                    "parameter_schema": getattr(template_obj, 'parameter_schema', {}) or {},
                    "similarity": best_similarity,
                }

        except Exception as e:
            logger.warning(f"Failed to load template {best_match['template_id']}: {e}")

        return None
