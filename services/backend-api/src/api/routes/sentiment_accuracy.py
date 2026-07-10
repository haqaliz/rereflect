"""
GET /api/v1/settings/ai/sentiment/accuracy (eval-harness-and-card aspect,
M5.1 disclosure layer).

Reads the committed eval_sentiment.py results artifact
(services/backend-api/eval_results/sentiment_accuracy.json) and serves it as
a typed, never-raising response. Never runs the model synchronously in the
request — recomputation is `python scripts/eval_sentiment.py` + commit
(see spec.md's "Live vs committed accuracy endpoint" scope decision).

No require_feature gate: this is a disclosure/self-hosting-transparency
feature, not a premium analytics feature (see spec.md Phase 6 rationale).
No organization_id scoping: the eval artifact is a single, global, offline,
reproducible snapshot, not a per-org metric.
"""
import json
import os

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from src.api.dependencies import get_current_user
from src.models.user import User
from src.schemas.sentiment_accuracy import SentimentAccuracyResponse

router = APIRouter(prefix="/api/v1/settings/ai", tags=["sentiment-accuracy"])

# Path to the artifact produced by `python scripts/eval_sentiment.py` (matches
# that script's default --output). Relative to this file so it resolves the
# same way regardless of the process's current working directory.
_ARTIFACT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "eval_results", "sentiment_accuracy.json")
)


@router.get("/sentiment/accuracy", response_model=SentimentAccuracyResponse)
def get_sentiment_accuracy(
    _current_user: User = Depends(get_current_user),
) -> SentimentAccuracyResponse:
    """Return the committed transformer-vs-VADER eval results.

    Never raises to the caller — an absent, unreadable, or malformed artifact
    simply yields has_results=False so the frontend can show an honest
    "eval not run yet" state instead of an error (mirrors
    get_embeddings_status's never-raises contract).
    """
    try:
        with open(_ARTIFACT_PATH) as f:
            raw = json.load(f)
        return SentimentAccuracyResponse(has_results=True, **raw)
    except (FileNotFoundError, json.JSONDecodeError, ValidationError, TypeError):
        return SentimentAccuracyResponse(has_results=False)
