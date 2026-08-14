"""Test-environment shim — NOT part of the churn_classifier public surface.

Mirror of tests/corrections_classifier/conftest.py: `src/analyzer/__init__.py`
eagerly imports FeedbackAnalyzer -> core -> sentiment -> vader, which imports the
third-party vaderSentiment package at module load. churn_classifier itself never
imports vaderSentiment/sklearn/numpy at module load (only trainer.py imports
sklearn/numpy, lazily inside train_churn_classifier), but any
`from src.analyzer.churn_classifier import ...` necessarily runs
`src/analyzer/__init__.py` first. Stub vaderSentiment here so collection succeeds
regardless of which venv is used; a no-op if vaderSentiment is actually importable.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

try:
    import vaderSentiment  # noqa: F401
except ImportError:
    _vader_pkg = MagicMock(name="vaderSentiment")
    _vader_submodule = MagicMock(name="vaderSentiment.vaderSentiment")
    _vader_submodule.SentimentIntensityAnalyzer = MagicMock(name="SentimentIntensityAnalyzer")
    sys.modules.setdefault("vaderSentiment", _vader_pkg)
    sys.modules.setdefault("vaderSentiment.vaderSentiment", _vader_submodule)
