"""
GET /api/v1/settings/ai/churn/label-gate (churn-label-gate-study aspect 2,
M5.3 disclosure layer).

Reads the committed eval_churn_label_gate.py results artifact
(services/backend-api/eval_results/churn_label_gate.json) and serves it as
a typed, never-raising response. Never runs any model synchronously in the
request — recomputation is `python scripts/eval_churn_label_gate.py` + commit
(mirrors sentiment_accuracy.py's M5.1 scope decision).

No require_feature gate: this is a disclosure/self-hosting-transparency
feature, not a premium analytics feature.
No organization_id scoping: the artifact is a single, global, offline,
reproducible snapshot, not a per-org metric — org-scoping is trivially
satisfied because there is no per-org data in the response.
"""
import json
import os

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from src.api.dependencies import get_current_user
from src.models.user import User
from src.schemas.churn_label_gate import ChurnLabelGateResponse

router = APIRouter(prefix="/api/v1/settings/ai", tags=["churn-label-gate"])

# Path to the artifact produced by `python scripts/eval_churn_label_gate.py`
# (matches that script's default --output). Relative to this file so it
# resolves the same way regardless of the process's current working directory.
_ARTIFACT_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "eval_results", "churn_label_gate.json")
)


@router.get("/churn/label-gate", response_model=ChurnLabelGateResponse)
def get_churn_label_gate(
    _current_user: User = Depends(get_current_user),
) -> ChurnLabelGateResponse:
    """Return the committed churn label-gate re-derivation study results.

    Never raises to the caller — an absent, unreadable, or malformed artifact
    simply yields has_results=False so the frontend can show an honest
    "study not run yet" state instead of an error (mirrors
    get_sentiment_accuracy's never-raises contract).
    """
    try:
        with open(_ARTIFACT_PATH) as f:
            raw = json.load(f)
        return ChurnLabelGateResponse(has_results=True, **raw)
    except (FileNotFoundError, json.JSONDecodeError, ValidationError, TypeError):
        return ChurnLabelGateResponse(has_results=False)
