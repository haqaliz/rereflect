"""
Phase 3/6 RED->GREEN: Mirror-equivalence guard (worker-service side).

Diffs the normalized bodies of classifier_resolver.py and classifier_predict.py
between backend-api and worker-service: strips each file's leading module
docstring (the two services' headers legitimately differ — service name,
mirror-direction sentence, "References" section) and normalizes the one
import line each file has that legitimately differs
(`from src.models import X` vs `from src.models.org_classifier import X` /
`from src.models.org_ai_config import X`). Everything else — the actual
resolver/loader/predict/override logic — MUST be byte-identical. This is the
same technique used elsewhere in the repo to hand-mirror models without a
shared package.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKER_SRC = _REPO_ROOT / "services" / "worker-service" / "src" / "services"
_BACKEND_SRC = _REPO_ROOT / "services" / "backend-api" / "src" / "services"

_DOCSTRING_RE = re.compile(r'\A"""(?:[^"]|"(?!""))*"""\n*', re.DOTALL)
_IMPORT_RE = re.compile(
    r"from src\.models(?:\.org_classifier|\.org_ai_config)? import (\w+)"
)


def _normalize(text: str) -> str:
    """Strip the leading module docstring; normalize the one legitimately-
    differing import line to a canonical form (`from src.models import X`)."""
    text = _DOCSTRING_RE.sub("", text, count=1)
    text = _IMPORT_RE.sub(r"from src.models import \1", text)
    return text


class TestClassifierResolverMirror:
    def test_normalized_bodies_are_identical(self):
        worker_text = (_WORKER_SRC / "classifier_resolver.py").read_text()
        backend_text = (_BACKEND_SRC / "classifier_resolver.py").read_text()

        assert _normalize(worker_text) == _normalize(backend_text)


class TestClassifierPredictMirror:
    def test_normalized_bodies_are_identical(self):
        worker_text = (_WORKER_SRC / "classifier_predict.py").read_text()
        backend_text = (_BACKEND_SRC / "classifier_predict.py").read_text()

        assert _normalize(worker_text) == _normalize(backend_text)
