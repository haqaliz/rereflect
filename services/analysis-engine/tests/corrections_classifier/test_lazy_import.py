"""Proves sklearn/numpy are truly optional at import time for corrections_classifier
(mirror of tests/sentiment_providers/test_lazy_import.py). Only train_classifier needs
them, and it imports them lazily inside the function — the rest of the package (predict,
score_from_proba, evaluate, metrics, dataset transform) is pure stdlib.

Uses a fresh subprocess interpreter (stubbing sys.modules in-process is fragile once
another test in the same session has already imported sklearn/numpy for real).

Isolation note (deviation from a literal `import src.analyzer.corrections_classifier`):
`src/analyzer/__init__.py` (out of this aspect's file ownership; owned by the pre-existing
sentiment/pain-point analyzer stack) eagerly imports `FeedbackAnalyzer` -> `core` ->
`extractors.py`, which does `from sklearn.feature_extraction.text import TfidfVectorizer`
at MODULE scope — unrelated to this aspect, but it means a plain `sys.modules['sklearn']
= None; import src.analyzer.corrections_classifier` fails for a reason that has nothing to
do with corrections_classifier's own laziness. To isolate the claim actually under test
("this aspect's own modules never import sklearn/numpy at module load"), we pre-register
minimal stand-in `src` / `src.analyzer` package objects in `sys.modules` (a standard Python
technique — if a dotted-import's parent packages are already present in `sys.modules`,
Python uses them as-is and does NOT re-run their `__init__.py`), then import
`src.analyzer.corrections_classifier` for real through that stand-in parent's `__path__`.
This still proves what the tech-plan asks for load-bearingly: none of predict.py,
evaluate.py, metrics.py, dataset.py (or trainer.py's module scope) needs sklearn/numpy —
train_classifier's lazy imports are the ONLY place they're required, and only when called.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ANALYSIS_ENGINE_ROOT = Path(__file__).resolve().parents[2]  # services/analysis-engine

_STUB_PARENT_PACKAGES = (
    "import sys, types\n"
    "src_pkg = types.ModuleType('src'); src_pkg.__path__ = ['src']\n"
    "analyzer_pkg = types.ModuleType('src.analyzer'); analyzer_pkg.__path__ = ['src/analyzer']\n"
    "sys.modules['src'] = src_pkg\n"
    "sys.modules['src.analyzer'] = analyzer_pkg\n"
)


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ANALYSIS_ENGINE_ROOT),
        capture_output=True, text=True, timeout=30,
    )


def test_package_importable_without_sklearn_or_numpy():
    code = (
        _STUB_PARENT_PACKAGES
        + "sys.modules['sklearn'] = None\n"
        "sys.modules['numpy'] = None\n"
        "import src.analyzer.corrections_classifier as cc\n"
        "print('OK')\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_trainer_module_importable_without_sklearn_or_numpy():
    """Importing trainer.py must not require sklearn/numpy — only CALLING
    train_classifier() does (the lazy import is inside the function body)."""
    code = (
        _STUB_PARENT_PACKAGES
        + "sys.modules['sklearn'] = None\n"
        "sys.modules['numpy'] = None\n"
        "from src.analyzer.corrections_classifier.trainer import train_classifier\n"
        "print('OK')\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
