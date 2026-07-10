"""
Phase 6: Contract-adapter test pinning aspect B's real
`predict(artifact, text) -> (label, proba)` / `score_from_proba(proba) -> float`
signature (analysis-engine's corrections_classifier package).

The tech-plan calls for this to be an xfail-until-merged test ("activates
when the module lands"). Aspect B (training-and-eval-core) is ALREADY merged
in this worktree (services/analysis-engine/src/analyzer/corrections_classifier/
exists — see git log f0d93e3..21d15ad), so this runs as a normal (non-xfail)
assertion pinning the exact contract `LoadedClassifier.predict` depends on.
"""

from __future__ import annotations

import os
import sys

# See test_feedback_sentiment_injection.py for why this sys.path insertion is
# needed locally (Docker-only layout otherwise puts analysis-engine's
# "analyzer" package on sys.path only inside the production image).
_ANALYSIS_ENGINE_SRC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../analysis-engine/src")
)
if _ANALYSIS_ENGINE_SRC not in sys.path:
    sys.path.insert(0, _ANALYSIS_ENGINE_SRC)


def test_real_predict_and_score_from_proba_signature():
    from analyzer.corrections_classifier.predict import predict, score_from_proba

    artifact = {
        "vectorizer": {
            "vocabulary": {"good": 0, "bad": 1},
            "idf": [1.0, 1.2],
            "token_pattern": r"(?u)\b\w\w+\b",
            "lowercase": True,
            "sublinear_tf": True,
            "norm": "l2",
        },
        "logreg": {"coef": [[1.5, -1.5]], "intercept": [0.0]},
        "classes": ["negative", "positive"],
    }

    label, proba = predict(artifact, "this is good")

    assert isinstance(label, str)
    assert isinstance(proba, dict)
    assert set(proba.keys()) == {"negative", "positive"}
    assert all(isinstance(v, float) for v in proba.values())

    score = score_from_proba(proba)

    assert isinstance(score, float)
    assert -1.0 <= score <= 1.0
    # "good" should push the decision toward positive.
    assert label == "positive"
    assert score > 0
