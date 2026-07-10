"""Proves torch/transformers are truly optional at import time — the vader path never requires
them; requesting/constructing the transformer provider is fine, only scoring with it needs them
(AC8). Uses a fresh subprocess interpreter since in-process sys.modules manipulation is fragile
once another test in the same session has already imported torch."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ANALYSIS_ENGINE_ROOT = Path(__file__).resolve().parents[2]  # services/analysis-engine


def test_vader_path_does_not_require_torch():
    code = (
        "import sys\n"
        "sys.modules['torch'] = None\n"          # any `import torch` now raises ImportError
        "sys.modules['transformers'] = None\n"    # same for transformers
        "from src.analyzer.sentiment import SentimentAnalyzer\n"
        "from src.analyzer.sentiment_providers.factory import SentimentProviderFactory\n"
        "a = SentimentAnalyzer()\n"                       # default = vader
        "r = a.analyze('This is fine, nothing bad here.')\n"
        "assert set(r.keys()) == {'compound','pos','neu','neg','label','is_extreme','churn_risk'}\n"
        "SentimentProviderFactory.create('vader')\n"      # explicit vader also fine
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ANALYSIS_ENGINE_ROOT),
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def test_transformer_path_fails_cleanly_without_torch():
    """Documents where the import boundary actually is (OQ1): requesting the transformer
    provider is fine; SCORING with it is where the missing dep surfaces, as an ImportError
    raised from score(), which SentimentAnalyzer.analyze() catches per Phase 6's fallback."""
    code = (
        "import sys\n"
        "sys.modules['torch'] = None\n"
        "sys.modules['transformers'] = None\n"
        "from src.analyzer.sentiment_providers.factory import SentimentProviderFactory\n"
        "p = SentimentProviderFactory.create('transformer')\n"  # construction: no import yet
        "try:\n"
        "    p.score('x')\n"
        "    raise SystemExit('expected ImportError')\n"
        "except ImportError:\n"
        "    print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ANALYSIS_ENGINE_ROOT),
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
