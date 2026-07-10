"""Pure-Python predict-from-JSON — Phase 3 (M5.2 training-and-eval-core).

Reconstructs the TF-IDF + logistic-regression decision from a JSON artifact (see
trainer.py's schema) WITHOUT sklearn/numpy — stdlib only (`re`, `math`). This is what
makes analyze-time (hot-path) scoring safe to call from anywhere, including envs without
ML wheels: only `train_classifier` ever needs sklearn/numpy, never `predict`.

Reproduces sklearn's own predictions exactly (pinned by test_predict.py's sklearn<->pure
parity test) BECAUSE trainer.py pins deterministic, fixed vectorizer/logreg params —
this module must never drift out of sync with that contract.
"""
from __future__ import annotations

import math
import re


def _tokenize(text: str, token_pattern: str, lowercase: bool) -> list[str]:
    haystack = text.lower() if lowercase else text
    return re.findall(token_pattern, haystack)


def _tfidf_vector(
    tokens: list[str],
    vocabulary: dict[str, int],
    idf: list[float],
    *,
    sublinear_tf: bool,
    norm: str,
) -> dict[int, float]:
    """Sparse {feature_index: tfidf_value} for in-vocab tokens only."""
    counts: dict[int, int] = {}
    for token in tokens:
        idx = vocabulary.get(token)
        if idx is None:
            continue
        counts[idx] = counts.get(idx, 0) + 1

    vec: dict[int, float] = {}
    for idx, count in counts.items():
        tf = (1.0 + math.log(count)) if sublinear_tf else float(count)
        vec[idx] = tf * idf[idx]

    if norm == "l2":
        norm_sq = sum(v * v for v in vec.values())
        if norm_sq > 0:
            denom = math.sqrt(norm_sq)
            vec = {idx: v / denom for idx, v in vec.items()}

    return vec


def _decision(vec: dict[int, float], coef: list[list[float]], intercept: list[float]) -> list[float]:
    """d[c] = intercept[c] + sum_j coef[c][j] * vec[j], iterating only sparse indices."""
    decisions: list[float] = []
    for class_coef, class_intercept in zip(coef, intercept):
        total = class_intercept
        for idx, value in vec.items():
            total += class_coef[idx] * value
        decisions.append(total)
    return decisions


def _softmax(values: list[float]) -> list[float]:
    """Numerically stable softmax (subtract max before exponentiating)."""
    m = max(values)
    exps = [math.exp(v - m) for v in values]
    total = sum(exps)
    if total == 0:
        return [1.0 / len(values)] * len(values)
    return [e / total for e in exps]


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def predict(artifact: dict, text: str) -> tuple[str, dict[str, float]]:
    """Predict (label, proba_dict) for `text` using a trainer.py JSON artifact.

    Pure Python — no sklearn/numpy required. Handles both the multinomial (3+ class)
    shape (coef.shape == (n_classes, n_features)) and the binary shape sklearn produces
    for 2-class problems (coef.shape == (1, n_features), via sigmoid).
    """
    vectorizer = artifact["vectorizer"]
    logreg = artifact["logreg"]
    classes: list[str] = artifact["classes"]

    tokens = _tokenize(text, vectorizer["token_pattern"], vectorizer["lowercase"])
    vec = _tfidf_vector(
        tokens,
        vectorizer["vocabulary"],
        vectorizer["idf"],
        sublinear_tf=vectorizer["sublinear_tf"],
        norm=vectorizer["norm"],
    )

    coef: list[list[float]] = logreg["coef"]
    intercept: list[float] = logreg["intercept"]

    if len(coef) == 1:
        # Binary shape: sklearn's convention is coef[0]/intercept[0] score
        # classes[1] (the positive class in binary LogisticRegression).
        decision = _decision(vec, coef, intercept)[0]
        p1 = _sigmoid(decision)
        proba = {classes[1]: p1, classes[0]: 1.0 - p1}
    else:
        decisions = _decision(vec, coef, intercept)
        probs = _softmax(decisions)
        proba = {cls: p for cls, p in zip(classes, probs)}

    label = max(proba, key=proba.get)
    return label, proba


def score_from_proba(proba: dict[str, float]) -> float:
    """clamp(P(positive) - P(negative), -1, 1). Missing classes treated as 0.0."""
    pos = proba.get("positive", 0.0)
    neg = proba.get("negative", 0.0)
    return max(-1.0, min(1.0, pos - neg))
