"""Proves sklearn/numpy are truly optional at import time for churn_classifier
(mirror of tests/corrections_classifier/test_lazy_import.py). Only
train_churn_classifier needs them, and it imports them lazily inside the
function — the rest of the package (features, dataset transform, predict,
metrics, evaluate) is pure stdlib.

Uses a fresh subprocess interpreter (stubbing sys.modules in-process is fragile
once another test in the same session has already imported sklearn/numpy).

Isolation note (deviation from a literal `import src.analyzer.churn_classifier`):
`src/analyzer/__init__.py` eagerly imports FeedbackAnalyzer -> core ->
extractors.py, which imports sklearn at MODULE scope — unrelated to this aspect.
To isolate the claim actually under test ("churn_classifier's own modules never
import sklearn/numpy at module load"), we pre-register minimal stand-in `src` /
`src.analyzer` package objects in sys.modules, then import
`src.analyzer.churn_classifier` for real through that stand-in parent's
`__path__` — the corrections_classifier test_lazy_import.py technique.
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
        "import src.analyzer.churn_classifier as cc\n"
        "print('OK')\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_trainer_module_importable_without_sklearn_or_numpy():
    """Importing trainer.py must not require sklearn/numpy — only CALLING
    train_churn_classifier() does (the lazy import is inside the function body)."""
    code = (
        _STUB_PARENT_PACKAGES
        + "sys.modules['sklearn'] = None\n"
        "sys.modules['numpy'] = None\n"
        "from src.analyzer.churn_classifier.trainer import train_churn_classifier\n"
        "print('OK')\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_public_surface_importable_without_sklearn_or_numpy():
    """The full re-export surface (including train_churn_classifier, re-exported
    at package level) is importable without sklearn/numpy actually being
    installed — the __init__'s `from .trainer import train_churn_classifier`
    doesn't defeat the laziness."""
    code = (
        _STUB_PARENT_PACKAGES
        + "sys.modules['sklearn'] = None\n"
        "sys.modules['numpy'] = None\n"
        "from src.analyzer.churn_classifier import (\n"
        "    MIN_LABELS, LABEL_WINDOW_DAYS, MARGIN, RANDOM_STATE,\n"
        "    compute_binary_metrics, binary_macro_f1,\n"
        "    FEATURE_NAMES, build_feature_vector, missing_snapshot_defaults,\n"
        "    train_churn_classifier, predict,\n"
        "    evaluate_churn, EvalResult, build_incumbent_predict,\n"
        "    fetch_churn_rows, rows_to_dataset,\n"
        ")\n"
        "from src.analyzer.churn_classifier.metrics import compute_binary_metrics\n"
        "print('OK')\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_calling_train_churn_classifier_without_sklearn_raises_importerror_not_silent():
    """Documents the boundary precisely: importing is fine; CALLING
    train_churn_classifier() without sklearn installed is where the missing dep
    surfaces, as a normal ImportError — never a silent no-op."""
    code = (
        _STUB_PARENT_PACKAGES
        + "sys.modules['sklearn'] = None\n"
        "sys.modules['numpy'] = None\n"
        "from src.analyzer.churn_classifier.trainer import train_churn_classifier\n"
        "try:\n"
        "    train_churn_classifier({'features': [], 'labels': []})\n"
        "    raise SystemExit('expected ImportError')\n"
        "except ImportError:\n"
        "    print('OK')\n"
    )
    result = _run(code)
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
