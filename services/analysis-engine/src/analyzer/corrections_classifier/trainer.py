"""TF-IDF + logistic-regression trainer — Phase 2 (M5.2 training-and-eval-core).

Serializes ONLY to JSON-native types (never pickle) — vocabulary/idf weights + logreg
coef_/intercept_/classes_ + vectorizer params, enough for predict.py to reconstruct the
linear model from JSON alone, no sklearn model object required at predict time.

sklearn/numpy are imported LAZILY inside `train_classifier` (mirroring
worker-service/src/services/calibration_refit.py's `_fit_isotonic`) so this module — and
the corrections_classifier package as a whole — stays importable in environments without
ML wheels (e.g. the worker-service Python 3.14 CI target). Only this function may import
sklearn/numpy; every other module in this package is pure stdlib.

Determinism contract: fixed random_state, multi_class="multinomial", solver="lbfgs", and
default-ish, pinned vectorizer params (lowercase, unigrams, l2 norm, no sublinear_tf,
smooth_idf) — never let these drift, or predict.py's pure-Python reimplementation will
stop reproducing sklearn's own predictions exactly (the sklearn<->pure-predict parity
test in test_predict.py pins this contract).

scikit-learn is pinned at 1.5.2 across analysis-engine/worker/backend — the `multi_class`
keyword is still supported (removal is post-1.5); a future sklearn bump touching this
keyword must be a conscious, tested change.
"""
from __future__ import annotations

from .labels import RANDOM_STATE

_MODEL_TYPE = "tfidf_logreg"
_CLASSIFIER_TYPE = "sentiment"


def train_classifier(dataset: list[tuple[str, str]], *, random_state: int = RANDOM_STATE) -> dict:
    """Train a TF-IDF + LogisticRegression sentiment classifier and return a JSON-only
    artifact dict. Deterministic given the same dataset + random_state."""
    from sklearn.feature_extraction.text import TfidfVectorizer  # lazy
    from sklearn.linear_model import LogisticRegression  # lazy

    texts = [t for t, _ in dataset]
    labels = [label for _, label in dataset]

    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 1),
        norm="l2",
        sublinear_tf=False,
        smooth_idf=True,
    )
    X = vectorizer.fit_transform(texts)

    clf = LogisticRegression(
        multi_class="multinomial",
        solver="lbfgs",
        random_state=random_state,
        max_iter=1000,
    )
    clf.fit(X, labels)

    return _serialize(vectorizer, clf, label_count=len(dataset))


def _serialize(vectorizer, clf, *, label_count: int) -> dict:
    vocabulary = {term: int(idx) for term, idx in vectorizer.vocabulary_.items()}
    return {
        "model_type": _MODEL_TYPE,
        "classifier_type": _CLASSIFIER_TYPE,
        "classes": clf.classes_.tolist(),
        "vectorizer": {
            "vocabulary": vocabulary,
            "idf": vectorizer.idf_.tolist(),
            "lowercase": bool(vectorizer.lowercase),
            "token_pattern": vectorizer.token_pattern,
            "ngram_range": list(vectorizer.ngram_range),
            "norm": vectorizer.norm,
            "sublinear_tf": bool(vectorizer.sublinear_tf),
            "smooth_idf": bool(vectorizer.smooth_idf),
        },
        "logreg": {
            "coef": clf.coef_.tolist(),
            "intercept": clf.intercept_.tolist(),
            "multi_class": "multinomial",
        },
        "label_count": label_count,
    }
