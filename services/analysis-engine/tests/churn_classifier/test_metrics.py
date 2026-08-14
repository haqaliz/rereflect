"""Tests for churn_classifier.metrics (M5.3 churn-classifier-core).

Hand-computed golden tests for `compute_binary_metrics` (positive-class
precision/recall/F1 at the 0.5 threshold, rank-based AUC) and `binary_macro_f1`
(the A/B's scoring metric — macro-F1 over both classes, matching sklearn's
f1_score(average="macro", zero_division=0) semantics used by the gate study),
plus degenerate-case zeros (no raise) and an sklearn cross-check.

Mirror of corrections_classifier/test_metrics_parity.py's style: the numbers
are anchored by hand computation, not by copying an implementation.
"""
from __future__ import annotations

import pytest

from src.analyzer.churn_classifier.metrics import binary_macro_f1, compute_binary_metrics


def _example():
    # probs / labels / hand-computed truth:
    # preds @ 0.5: [1, 1, 1, 0, 0, 0]
    # tp=2 (0.9, 0.8), fp=1 (0.6), fn=1 (0.4), tn=2 (0.2, 0.1)
    # P = 2/3, R = 2/3, F1 = 2/3
    # AUC (ascending ranks, lowest score -> rank 1): positives at ranks
    # 6, 5, 3 (sum 14); (14 - 3*4/2) / (3*3) = 8/9 — P(score_pos > score_neg)
    # over the 9 positive/negative pairs, 8 of which the scores order correctly.
    probs = [0.9, 0.8, 0.6, 0.4, 0.2, 0.1]
    labels = [1, 1, 0, 1, 0, 0]
    return probs, labels


def test_compute_binary_metrics_golden_example():
    probs, labels = _example()
    result = compute_binary_metrics(probs, labels)
    assert result["precision"] == pytest.approx(2 / 3)
    assert result["recall"] == pytest.approx(2 / 3)
    assert result["f1"] == pytest.approx(2 / 3)
    assert result["auc"] == pytest.approx(8 / 9)


def test_binary_macro_f1_golden_example():
    probs, labels = _example()
    # Class 1: P=2/3, R=2/3, F1=2/3. Class 0: tp0=tn=2, fp0=fn=1, fn0=fp=1
    # -> P0=2/3, R0=2/3, F1_0=2/3. macro = (2/3 + 2/3)/2.
    assert binary_macro_f1(probs, labels) == pytest.approx(2 / 3)


def test_perfect_classification():
    probs = [0.9, 0.8, 0.7, 0.3, 0.2, 0.1]
    labels = [1, 1, 1, 0, 0, 0]
    result = compute_binary_metrics(probs, labels)
    assert result == {
        "precision": pytest.approx(1.0),
        "recall": pytest.approx(1.0),
        "f1": pytest.approx(1.0),
        "auc": pytest.approx(1.0),
        "macro_f1": pytest.approx(1.0),
    }


def test_ties_get_average_rank_in_auc():
    # 0.8 appears 3 times -> averaged rank (3+4+5)/3 = 4 for each;
    # 0.2s get (1+2)/2 = 1.5. positives at rank 4, 4 -> rank_sum 8;
    # (8 - 2*3/2) / (2*3) = 5/6.
    probs = [0.8, 0.8, 0.8, 0.2, 0.2]
    labels = [1, 0, 1, 0, 0]
    result = compute_binary_metrics(probs, labels)
    assert result["precision"] == pytest.approx(2 / 3)
    assert result["recall"] == pytest.approx(1.0)
    assert result["f1"] == pytest.approx(4 / 5)
    assert result["auc"] == pytest.approx(5 / 6)


def test_threshold_boundary_inclusive_at_0_5():
    # p == 0.5 counts as the positive class (preds >= 0.5).
    probs = [0.5, 0.2]
    labels = [1, 0]
    result = compute_binary_metrics(probs, labels)
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["f1"] == 1.0
    assert result["auc"] == 1.0


# ---------------------------------------------------------------------------
# Degenerate cases — zeros, never raise
# ---------------------------------------------------------------------------

def test_all_negative_labels_returns_zeros():
    result = compute_binary_metrics([0.9, 0.8, 0.7], [0, 0, 0])
    assert result == {"precision": 0.0, "recall": 0.0, "f1": 0.0, "auc": 0.0, "macro_f1": 0.0}
    assert binary_macro_f1([0.9, 0.8, 0.7], [0, 0, 0]) == 0.0


def test_all_positive_labels_returns_zeros():
    result = compute_binary_metrics([0.9, 0.8, 0.7], [1, 1, 1])
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["f1"] == 0.0
    assert result["auc"] == 0.0
    assert binary_macro_f1([0.9, 0.8, 0.7], [1, 1, 1]) == 0.0


def test_empty_inputs_returns_zeros():
    result = compute_binary_metrics([], [])
    assert result == {"precision": 0.0, "recall": 0.0, "f1": 0.0, "auc": 0.0, "macro_f1": 0.0}


def test_no_predicted_positives_returns_zeros():
    result = compute_binary_metrics([0.1, 0.2, 0.3], [1, 0, 0])
    assert result["precision"] == 0.0
    assert result["recall"] == 0.0
    assert result["f1"] == 0.0


def test_constant_probs_auc_handles_ties():
    result = compute_binary_metrics([0.5, 0.5, 0.5], [1, 0, 1])
    # all ranks averaged to 2; rank_sum = 4; (4 - 3)/ (2*1) = 0.5
    assert result["auc"] == pytest.approx(0.5)
    assert result["precision"] == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------
# sklearn cross-check (guarded — sklearn is optional in wheels-less venvs)
# ---------------------------------------------------------------------------

def test_macro_f1_matches_sklearn_on_golden_example():
    sklearn = pytest.importorskip("sklearn")
    from sklearn.metrics import f1_score

    probs, labels = _example()
    preds = [1 if p >= 0.5 else 0 for p in probs]
    assert binary_macro_f1(probs, labels) == pytest.approx(
        f1_score(labels, preds, average="macro", zero_division=0)
    )


def test_auc_matches_sklearn_on_golden_example():
    sklearn = pytest.importorskip("sklearn")
    from sklearn.metrics import roc_auc_score

    probs, labels = _example()
    assert compute_binary_metrics(probs, labels)["auc"] == pytest.approx(
        roc_auc_score(labels, probs)
    )
