"""Binary churn metrics — pure stdlib (M5.3 churn-classifier-core).

`compute_binary_metrics` mirrors the corrections_classifier/metrics.py style
(threshold-derived counts, every division guarded, degenerate cases return
zeros, never raise) but for the churn binary problem: predicted churn
PROBABILITIES (0-1) are thresholded at 0.5 into class predictions, and the
rank-based AUC is computed in pure Python (average ranks for ties).

`binary_macro_f1` is the A/B's scoring metric: the mean of the two classes'
F1 scores, exactly sklearn's f1_score(average="macro", zero_division=0) —
the semantics the gate study (aspect 2) used for its challenger-vs-incumbent
delta, and therefore the metric the promotion decision must be computed with.

No sklearn/numpy — importable in wheels-less venvs; only trainer.py (lazily)
needs ML wheels.
"""
from __future__ import annotations

from typing import List, Union

Prob = Union[float, int]


def _count_confusion(predicted_probs: List[Prob], labels: List[int]) -> tuple[int, int, int, int]:
    """tp, fp, fn, tn at the 0.5 threshold (p >= 0.5 predicts the positive class)."""
    tp = fp = fn = tn = 0
    for p, y in zip(predicted_probs, labels):
        pred = 1 if p >= 0.5 else 0
        if y == 1:
            if pred == 1:
                tp += 1
            else:
                fn += 1
        else:
            if pred == 1:
                fp += 1
            else:
                tn += 1
    return tp, fp, fn, tn


def _precision_recall_f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def _auc(predicted_probs: List[Prob], labels: List[int]) -> float:
    """Rank-based (Mann-Whitney U) ROC AUC with averaged ranks for ties.

    0.0 when either class is absent from `labels` — an AUC is undefined without
    both classes, and the churn core's degenerate-case convention is zeros.
    """
    n_pos = sum(1 for y in labels if y == 1)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.0

    # Ascending rank order (lowest score -> rank 1), the standard convention
    # that makes the formula yield P(score_pos > score_neg) + 0.5*P(tie) —
    # i.e. sklearn's roc_auc_score. Ties get the averaged rank.
    ordered = sorted(range(len(predicted_probs)), key=lambda i: predicted_probs[i])
    ranks: list[float] = [0.0] * len(predicted_probs)
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and predicted_probs[ordered[j + 1]] == predicted_probs[ordered[i]]:
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[ordered[k]] = avg_rank
        i = j + 1

    rank_sum = sum(ranks[i] for i in range(len(labels)) if labels[i] == 1)
    return (rank_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def compute_binary_metrics(predicted_probs: List[Prob], labels: List[int]) -> dict:
    """Positive-class precision/recall/F1 (0.5 threshold), rank AUC, and the
    macro-F1 over both classes. Degenerate inputs (empty, single-class, no
    predicted positives) return zeros — never raise.

    Single-class label sets return ALL zeros, mirroring the calibrator's own
    degenerate-case convention (calibration_refit._compute_metrics: "all same
    label" -> zeros) — an A/B that cannot score both classes must not look
    like a win.
    """
    if len(labels) == 0 or len(set(labels)) < 2:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "auc": 0.0, "macro_f1": 0.0}
    tp, fp, fn, tn = _count_confusion(predicted_probs, labels)
    precision, recall, f1 = _precision_recall_f1(tp, fp, fn)
    # Negative class (for macro-F1): its tp=tn, fp=fn, fn=fp.
    neg_precision, neg_recall, neg_f1 = _precision_recall_f1(tn, fn, fp)
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "auc": _auc(predicted_probs, labels),
        "macro_f1": (f1 + neg_f1) / 2.0,
    }


def binary_macro_f1(predicted_probs: List[Prob], labels: List[int]) -> float:
    """Macro-F1 over the two churn classes — the A/B promotion metric.

    Identical semantics to sklearn's f1_score(y_true, y_pred, average="macro",
    zero_division=0) at the 0.5 threshold (see test_metrics.py's sklearn
    cross-check). Degenerate single-class inputs score 0.0 (never raise).
    """
    if len(labels) == 0 or len(set(labels)) < 2:
        return 0.0
    tp, fp, fn, tn = _count_confusion(predicted_probs, labels)
    _, _, f1_pos = _precision_recall_f1(tp, fp, fn)
    _, _, f1_neg = _precision_recall_f1(tn, fn, fp)
    return (f1_pos + f1_neg) / 2.0
