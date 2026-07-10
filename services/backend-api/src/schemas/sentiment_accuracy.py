"""
Pydantic schemas for GET /api/v1/settings/ai/sentiment/accuracy
(eval-harness-and-card aspect, M5.1 disclosure layer).

Mirrors the eval_sentiment.py script's committed JSON artifact
(services/backend-api/eval_results/sentiment_accuracy.json) 1:1 so the
route's parse-or-degrade handler is a thin pass-through.
"""
from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict


class ClassMetrics(BaseModel):
    """Precision/recall/F1/support for a single sentiment class."""

    precision: float
    recall: float
    f1: float
    support: int


class ProviderEvalResult(BaseModel):
    """One provider's (vader or transformer) results on one eval set."""

    provider: str
    n: int
    macro_precision: float
    macro_recall: float
    macro_f1: float
    accuracy: float
    per_class: Dict[str, ClassMetrics]
    confusion_matrix: Dict[str, Dict[str, int]]


class EvalSetResult(BaseModel):
    """Both providers' results on one eval set (public or in_domain), plus the
    transformer-vs-VADER delta and whether it meets the in-domain target."""

    set_name: str
    n: int
    vader: Optional[ProviderEvalResult] = None
    transformer: Optional[ProviderEvalResult] = None
    macro_f1_delta: Optional[float] = None
    meets_target: Optional[bool] = None


class SentimentAccuracyResponse(BaseModel):
    """Response for GET /api/v1/settings/ai/sentiment/accuracy.

    has_results=False (with every other field null/absent) is the honest
    "eval not run yet" state — never a 404/500 (mirrors get_embeddings_status's
    never-raises contract). No organization_id scoping: this is a global,
    offline, reproducible disclosure artifact, not a per-org metric.
    """

    model_config = ConfigDict(protected_namespaces=())

    has_results: bool
    generated_at: Optional[datetime] = None
    model_id: Optional[str] = None
    model_revision: Optional[str] = None
    public: Optional[EvalSetResult] = None
    in_domain: Optional[EvalSetResult] = None
