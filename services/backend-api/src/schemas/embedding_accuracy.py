"""
Pydantic schemas for GET /api/v1/settings/ai/embeddings/accuracy
(retrieval-eval-card aspect, M5.4 disclosure layer).

Mirrors the eval_retrieval.py script's committed JSON artifact
(services/backend-api/eval_results/retrieval_accuracy.json) 1:1 so the
route's parse-or-degrade handler is a thin pass-through.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ProviderRetrievalResult(BaseModel):
    """One provider's (baseline or candidate) retrieval-eval results."""

    model_config = ConfigDict(protected_namespaces=())

    provider: str
    model: Optional[str] = None
    n: int
    n_pos: int
    n_neg: int
    recall_at_1: float
    mrr: float
    false_match_rate: float


class RetrievalAccuracyResponse(BaseModel):
    """Response for GET /api/v1/settings/ai/embeddings/accuracy.

    has_results=False (with every other field null/absent) is the honest
    "eval not run yet" state — never a 404/500 (mirrors get_embeddings_status's
    never-raises contract). No organization_id scoping: this is a global,
    offline, reproducible disclosure artifact, not a per-org metric.
    """

    model_config = ConfigDict(protected_namespaces=())

    has_results: bool
    generated_at: Optional[datetime] = None
    threshold: Optional[float] = None
    n: Optional[int] = None
    n_positives: Optional[int] = None
    n_negatives: Optional[int] = None
    baseline: Optional[ProviderRetrievalResult] = None
    candidate: Optional[ProviderRetrievalResult] = None
    recall_at_1_delta: Optional[float] = None
    meets_target: Optional[bool] = None
