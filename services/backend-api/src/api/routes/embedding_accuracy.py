"""
GET /api/v1/settings/ai/embeddings/accuracy (retrieval-eval-card aspect,
M5.4 disclosure layer).

Reads the committed eval_retrieval.py results artifact
(services/backend-api/eval_results/retrieval_accuracy.json) and serves it as
a typed, never-raising response. Never runs the model synchronously in the
request — recomputation is `python scripts/eval_retrieval.py` + commit
(mirrors sentiment_accuracy.py's M5.1 scope decision).

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
from src.schemas.embedding_accuracy import RetrievalAccuracyResponse

router = APIRouter(prefix="/api/v1/settings/ai", tags=["embedding-accuracy"])

# Path to the artifact produced by `python scripts/eval_retrieval.py` (matches
# that script's default --output). Relative to this file so it resolves the
# same way regardless of the process's current working directory.
_ARTIFACT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "eval_results", "retrieval_accuracy.json")
)


@router.get("/embeddings/accuracy", response_model=RetrievalAccuracyResponse)
def get_embedding_accuracy(
    _current_user: User = Depends(get_current_user),
) -> RetrievalAccuracyResponse:
    """Return the committed local-vs-baseline embedding retrieval eval results.

    Never raises to the caller — an absent, unreadable, or malformed artifact
    simply yields has_results=False so the frontend can show an honest
    "eval not run yet" state instead of an error (mirrors
    get_embeddings_status's never-raises contract).
    """
    try:
        with open(_ARTIFACT_PATH) as f:
            raw = json.load(f)
        return RetrievalAccuracyResponse(has_results=True, **raw)
    except (FileNotFoundError, json.JSONDecodeError, ValidationError, TypeError):
        return RetrievalAccuracyResponse(has_results=False)
