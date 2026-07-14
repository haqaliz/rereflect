"""Tests for corrections_classifier.labels — urgency-core (M urgency-classifier-head).

`URGENCY_LABELS` is a fixed, lexicographically-sorted binary vocab — mirrors
`SENTIMENT_LABELS`'s fixed-vocab contract, NOT category's dynamic vocab. The sort order
matters: `predict()`'s binary sigmoid branch (`len(coef) == 1`) treats `classes[1]` as the
positive class, so "urgent" must land at index 1.
"""
from __future__ import annotations

from src.analyzer.corrections_classifier.labels import URGENCY_LABELS


def test_urgency_labels_value():
    assert URGENCY_LABELS == ("not_urgent", "urgent")


def test_urgency_labels_sorted_positive_is_index_1():
    assert tuple(sorted(URGENCY_LABELS)) == URGENCY_LABELS
    assert URGENCY_LABELS[1] == "urgent"
