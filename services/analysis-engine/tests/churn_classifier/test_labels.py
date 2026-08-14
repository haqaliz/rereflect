"""Tests for churn_classifier.labels (M5.3 churn-classifier-core).

Every constant here is parity-pinned to its source-of-truth definition elsewhere
in the repo (the churn calibration path that predates the ML head), so a drift
in either direction is a test failure, not a silent divergence:

- MIN_LABELS == churn_calibrator.py's MIN_LABELS (backend-api) — the per-org
  activation gate for fitting a model from non-auto-suggested labels.
- LABEL_WINDOW_DAYS == calibration_refit.py's _LABEL_WINDOW_DAYS (worker) — the
  180-day observation window that defines a churn label.
- MARGIN / RANDOM_STATE are the M5.2 A/B promotion margin and the fixed seed,
  mirroring corrections_classifier.labels.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.analyzer.churn_classifier.labels import (
    LABEL_WINDOW_DAYS,
    MARGIN,
    MIN_LABELS,
    RANDOM_STATE,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]  # services/analysis-engine -> repo root


def _parse_int_const(file_path: Path, name: str) -> int:
    """Parse `NAME = <int>` / `NAME: int = <int>` from a source file (line-based
    robustness: value pin, not line-number pin)."""
    text = file_path.read_text()
    match = re.search(rf"^{name}\s*(?::\s*int)?\s*=\s*(\d+)\s*(?:#.*)?$", text, re.MULTILINE)
    assert match is not None, f"{name} not found in {file_path}"
    return int(match.group(1))


def test_min_labels_value():
    assert MIN_LABELS == 20


def test_min_labels_parity_with_backend_churn_calibrator():
    """MIN_LABELS must stay in lockstep with
    services/backend-api/src/services/churn_calibrator.py's MIN_LABELS — the
    calibrator's fit gate (churn_calibrator.py:20)."""
    calibrator = _REPO_ROOT / "services/backend-api/src/services/churn_calibrator.py"
    assert _parse_int_const(calibrator, "MIN_LABELS") == MIN_LABELS


def test_label_window_days_value():
    assert LABEL_WINDOW_DAYS == 180


def test_label_window_days_parity_with_worker_calibration_refit():
    """LABEL_WINDOW_DAYS must stay in lockstep with
    services/worker-service/src/services/calibration_refit.py's
    _LABEL_WINDOW_DAYS (calibration_refit.py:40) — the 180-day window that
    defines the churn label semantics."""
    refit = _REPO_ROOT / "services/worker-service/src/services/calibration_refit.py"
    assert _parse_int_const(refit, "_LABEL_WINDOW_DAYS") == LABEL_WINDOW_DAYS


def test_margin_value():
    assert MARGIN == 0.02


def test_random_state_value():
    assert RANDOM_STATE == 0
