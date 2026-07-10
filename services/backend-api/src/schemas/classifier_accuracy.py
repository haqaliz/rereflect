"""
Pydantic schemas for GET /api/v1/settings/ai/classifier/accuracy
(settings-api-and-accuracy-card aspect, M5.2 disclosure layer).

Mirrors src/schemas/sentiment_accuracy.py's / src/schemas/churn_accuracy.py's
shape conventions: a small "active model" summary + a bounded eval-run
history list, both org-scoped and never-raising at the route layer.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ClassifierEvalRunSummary(BaseModel):
    """One OrgClassifierEvalRun row — incumbent vs challenger shadow-mode eval."""

    incumbent_macro_f1: Optional[float] = None
    challenger_macro_f1: Optional[float] = None
    macro_f1_delta: Optional[float] = None
    decision: str
    n: Optional[int] = None
    created_at: datetime


class ClassifierAccuracyResponse(BaseModel):
    """Response for GET /api/v1/settings/ai/classifier/accuracy.

    has_model=False (with label_count=0, macro_f1=None, fit_at=None,
    is_ready=False, history=[]) is the honest "no model fit yet" state —
    never a 404/500 (mirrors get_embeddings_status / get_sentiment_accuracy's
    never-raises contract). precision/recall/accuracy are deliberately absent
    here: the worker-trainer currently persists only macro_f1 on
    OrgClassifierModel, so surfacing null precision/recall would invite the
    frontend to fabricate a dash for values that were never computed at all.
    """

    model_config = ConfigDict(protected_namespaces=())

    model_kind: str = "per-org TF-IDF + logistic regression"
    classifier_type: str
    has_model: bool
    label_count: int
    macro_f1: Optional[float] = None
    fit_at: Optional[datetime] = None
    is_ready: bool
    min_labels: int
    history: List[ClassifierEvalRunSummary] = []
