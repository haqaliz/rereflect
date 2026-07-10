"""Test-environment shim — NOT part of the corrections_classifier public surface.

`src/analyzer/__init__.py` eagerly imports `FeedbackAnalyzer` -> `core` -> `sentiment`
-> `sentiment_providers.providers.vader`, which imports the third-party `vaderSentiment`
package at module load. That import chain is unrelated to this aspect (corrections_classifier
itself never imports vaderSentiment/sklearn/numpy at module load — only `trainer.py` imports
sklearn/numpy, lazily inside `train_classifier`), but any `from src.analyzer.corrections_classifier
import ...` necessarily runs `src/analyzer/__init__.py` first (Python always initializes parent
packages of a dotted import).

Per the test-runners doc for this worktree, this suite is exercised with the backend-api venv
(AE_PY), which has numpy/sklearn/sqlalchemy but does NOT have vaderSentiment installed. Stub it
here so collection of tests/corrections_classifier/ succeeds regardless of which venv is used —
this file affects only this test package (pytest.ini `rootdir`-relative conftest scoping), and is
a no-op if vaderSentiment is actually importable (e.g. the analysis-engine's own venv).
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
