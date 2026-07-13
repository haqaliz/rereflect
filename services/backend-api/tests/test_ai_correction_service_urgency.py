"""
TDD tests for the shared urgency corrected-value constant/helper
(capture-seam Phase 1) — `services/ai_correction_service.py`.

Goal: a single backend source of truth for "urgent"/"not_urgent" so the two
capture sites (internal PATCH .../urgent and public PATCH .../feedback/{id})
can't drift from each other, or from analysis-engine's
`analyzer.corrections_classifier.labels.URGENCY_LABELS`.
"""

import os
import sys

import pytest

from src.services.ai_correction_service import (
    URGENCY_CORRECTED_VALUES,
    urgency_label,
)


class TestUrgencyCorrectedValuesVocab:
    def test_vocab_is_exactly_not_urgent_urgent(self):
        assert URGENCY_CORRECTED_VALUES == ("not_urgent", "urgent")


class TestUrgencyLabelHelper:
    def test_true_maps_to_urgent(self):
        assert urgency_label(True) == "urgent"

    def test_false_maps_to_not_urgent(self):
        assert urgency_label(False) == "not_urgent"

    def test_return_value_always_in_vocab(self):
        assert urgency_label(True) in URGENCY_CORRECTED_VALUES
        assert urgency_label(False) in URGENCY_CORRECTED_VALUES


class TestUrgencyVocabMatchesAnalysisEngine:
    """Cross-service guard: a mismatch here silently drops all rows in
    build_urgency_dataset (analysis-engine). Keep the two vocabularies
    identical."""

    def test_matches_analysis_engine_urgency_labels(self):
        analysis_engine_src = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../analysis-engine/src")
        )
        if analysis_engine_src not in sys.path:
            sys.path.insert(0, analysis_engine_src)

        from analyzer.corrections_classifier.labels import URGENCY_LABELS

        assert URGENCY_CORRECTED_VALUES == URGENCY_LABELS
