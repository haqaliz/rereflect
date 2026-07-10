"""Multiclass confusion-matrix metrics — Phase 4a (M5.2 training-and-eval-core).

VERBATIM port of `_safe_precision_recall_f1_accuracy` / `confusion_to_binary_counts` /
`compute_multiclass_metrics` from `services/backend-api/scripts/eval_sentiment.py`
(source of truth; confusion shape `confusion[true_label][predicted_label] = count`).

This is a deliberate copy, not a cross-service import — analysis-engine cannot (and
shouldn't) import a backend-api script. This follows the codebase's own stated
precedent that this metrics math is independently defined per script/module rather than
shared via a common library: `eval_sentiment.py:44-50` documents copying it from
`admin_backtest.py`'s `_safe_precision_recall_f1_accuracy`, and `backtest_churn.py`
keeps its own copy too. `test_metrics_parity.py` pins this port's outputs to
hand-computed numbers to prove the copy is faithful.

Pure stdlib — no sklearn/numpy/sqlalchemy needed.
"""
from __future__ import annotations


def _safe_precision_recall_f1_accuracy(
    tp: int, fp: int, fn: int, tn: int
) -> tuple[float, float, float, float]:
    """Compute precision, recall, F1, and accuracy from confusion matrix counts."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    total = tp + fp + fn + tn
    accuracy = (tp + tn) / total if total > 0 else 0.0
    return precision, recall, f1, accuracy


def confusion_to_binary_counts(
    confusion: dict[str, dict[str, int]], label: str, labels: list[str]
) -> tuple[int, int, int, int]:
    """One-vs-rest slice of a multiclass confusion matrix for a single label.

    confusion[true_label][predicted_label] = count.
    """
    tp = confusion[label][label]
    fp = sum(confusion[other][label] for other in labels if other != label)
    fn = sum(confusion[label][other] for other in labels if other != label)
    total = sum(confusion[t][p] for t in labels for p in labels)
    tn = total - tp - fp - fn
    return tp, fp, fn, tn


def compute_multiclass_metrics(confusion: dict[str, dict[str, int]], labels: list[str]) -> dict:
    """Per-class precision/recall/F1/support + macro-averages + overall accuracy.

    Never raises on empty/degenerate confusion matrices (all-zero, single-class-only) —
    _safe_precision_recall_f1_accuracy already guards every division.
    """
    per_class = {}
    for label in labels:
        tp, fp, fn, tn = confusion_to_binary_counts(confusion, label, labels)
        precision, recall, f1, _ = _safe_precision_recall_f1_accuracy(tp, fp, fn, tn)
        support = tp + fn  # true count for this label (row sum)
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }

    macro_precision = sum(per_class[l]["precision"] for l in labels) / len(labels)
    macro_recall = sum(per_class[l]["recall"] for l in labels) / len(labels)
    macro_f1 = sum(per_class[l]["f1"] for l in labels) / len(labels)

    total = sum(confusion[t][p] for t in labels for p in labels)
    trace = sum(confusion[l][l] for l in labels)
    accuracy = trace / total if total > 0 else 0.0

    return {
        "per_class": per_class,
        "macro_precision": macro_precision,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
        "accuracy": accuracy,
    }
