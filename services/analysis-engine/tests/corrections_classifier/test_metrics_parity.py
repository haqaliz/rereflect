"""Parity anchor for corrections_classifier.metrics — Phase 4a (M5.2 training-and-eval-core).

metrics.py is a VERBATIM port of `_safe_precision_recall_f1_accuracy` /
`confusion_to_binary_counts` / `compute_multiclass_metrics` from
`services/backend-api/scripts/eval_sentiment.py` (per the tech-plan's resolved
ambiguity #1: copy-not-share is this codebase's own stated precedent —
eval_sentiment.py:44-50 documents copying from admin_backtest.py, backtest_churn.py
keeps its own copy too). This test pins identical outputs on an identical
confusion[true][pred] matrix, hand-computed, to prove the port is faithful.
"""
from __future__ import annotations

import pytest

from src.analyzer.corrections_classifier.labels import SENTIMENT_LABELS
from src.analyzer.corrections_classifier.metrics import (
    compute_multiclass_metrics,
    confusion_to_binary_counts,
)

# eval_sentiment.py's SENTIMENT_LABELS order is ["positive", "neutral", "negative"];
# corrections_classifier's SENTIMENT_LABELS is sorted ("negative", "neutral", "positive").
# The confusion shape (confusion[true][pred] = count) and the metrics math are label-
# order-independent (macro-averages sum over `labels` either way), so we anchor with
# corrections_classifier's own label order here.
LABELS = list(SENTIMENT_LABELS)  # ("negative", "neutral", "positive")


def _confusion(negative=None, neutral=None, positive=None):
    return {
        "negative": dict(negative or {"negative": 0, "neutral": 0, "positive": 0}),
        "neutral": dict(neutral or {"negative": 0, "neutral": 0, "positive": 0}),
        "positive": dict(positive or {"negative": 0, "neutral": 0, "positive": 0}),
    }


def test_compute_multiclass_metrics_matches_eval_sentiment_numbers():
    # Hand-built confusion matrix (true rows, predicted cols):
    #            pred_neg  pred_neu  pred_pos
    # true_neg       8         1         1     (support=10)
    # true_neu       2         6         2     (support=10)
    # true_pos       0         1         9     (support=10)
    confusion = _confusion(
        negative={"negative": 8, "neutral": 1, "positive": 1},
        neutral={"negative": 2, "neutral": 6, "positive": 2},
        positive={"negative": 0, "neutral": 1, "positive": 9},
    )

    # Hand-computed (anchor) numbers, using eval_sentiment.py's exact math:
    # negative: tp=8, fp=(2+0)=2, fn=(1+1)=2 -> P=8/10=0.8, R=8/10=0.8, F1=0.8
    # neutral:  tp=6, fp=(1+1)=2, fn=(2+2)=4 -> P=6/8=0.75, R=6/10=0.6, F1=2*.75*.6/(.75+.6)=0.6667
    # positive: tp=9, fp=(1+2)=3, fn=(0+1)=1 -> P=9/12=0.75, R=9/10=0.9, F1=2*.75*.9/(.75+.9)=0.8182
    result = compute_multiclass_metrics(confusion, LABELS)

    assert result["per_class"]["negative"]["precision"] == pytest.approx(0.8)
    assert result["per_class"]["negative"]["recall"] == pytest.approx(0.8)
    assert result["per_class"]["negative"]["f1"] == pytest.approx(0.8)
    assert result["per_class"]["negative"]["support"] == 10

    assert result["per_class"]["neutral"]["precision"] == pytest.approx(0.75)
    assert result["per_class"]["neutral"]["recall"] == pytest.approx(0.6)
    assert result["per_class"]["neutral"]["f1"] == pytest.approx(2 * 0.75 * 0.6 / (0.75 + 0.6))
    assert result["per_class"]["neutral"]["support"] == 10

    assert result["per_class"]["positive"]["precision"] == pytest.approx(0.75)
    assert result["per_class"]["positive"]["recall"] == pytest.approx(0.9)
    assert result["per_class"]["positive"]["f1"] == pytest.approx(2 * 0.75 * 0.9 / (0.75 + 0.9))
    assert result["per_class"]["positive"]["support"] == 10

    expected_macro_p = (0.8 + 0.75 + 0.75) / 3
    expected_macro_r = (0.8 + 0.6 + 0.9) / 3
    expected_macro_f1 = (
        0.8 + (2 * 0.75 * 0.6 / (0.75 + 0.6)) + (2 * 0.75 * 0.9 / (0.75 + 0.9))
    ) / 3
    assert result["macro_precision"] == pytest.approx(expected_macro_p)
    assert result["macro_recall"] == pytest.approx(expected_macro_r)
    assert result["macro_f1"] == pytest.approx(expected_macro_f1)

    # accuracy = trace / total = (8+6+9) / 30
    assert result["accuracy"] == pytest.approx((8 + 6 + 9) / 30)


def test_confusion_to_binary_counts_matches_eval_sentiment_numbers():
    confusion = _confusion(
        negative={"negative": 8, "neutral": 1, "positive": 1},
        neutral={"negative": 2, "neutral": 6, "positive": 2},
        positive={"negative": 0, "neutral": 1, "positive": 9},
    )
    tp, fp, fn, tn = confusion_to_binary_counts(confusion, "negative", LABELS)
    assert (tp, fp, fn) == (8, 2, 2)
    assert tn == 30 - tp - fp - fn


def test_degenerate_all_zero_confusion_no_raise():
    confusion = _confusion()
    result = compute_multiclass_metrics(confusion, LABELS)
    for label in LABELS:
        assert result["per_class"][label]["precision"] == 0.0
        assert result["per_class"][label]["recall"] == 0.0
        assert result["per_class"][label]["f1"] == 0.0
        assert result["per_class"][label]["support"] == 0
    assert result["macro_precision"] == 0.0
    assert result["macro_recall"] == 0.0
    assert result["macro_f1"] == 0.0
    assert result["accuracy"] == 0.0


def test_single_class_confusion_no_raise():
    # Every row lands on "positive" -> perfect for positive, zero (never raise) elsewhere.
    confusion = _confusion(
        negative={"negative": 0, "neutral": 0, "positive": 5},
        neutral={"negative": 0, "neutral": 0, "positive": 5},
        positive={"negative": 0, "neutral": 0, "positive": 5},
    )
    result = compute_multiclass_metrics(confusion, LABELS)
    assert result["per_class"]["positive"]["recall"] == pytest.approx(1.0)
    assert result["per_class"]["negative"]["support"] == 5
    assert result["per_class"]["negative"]["precision"] == 0.0
    assert result["per_class"]["negative"]["recall"] == 0.0
