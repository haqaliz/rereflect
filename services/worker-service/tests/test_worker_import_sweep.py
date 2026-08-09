"""R8 sweep-guard: worker source must never import backend-only modules.

The worker image copies only ``worker-service/src`` and ``analysis-engine/src/analyzer``
under ``PYTHONPATH=/app``. Any import of a backend-api-only module from worker source
is the "wired at one end, dead at the other" family (DEV-TRACKING P0/P0b +
docs/planning/automations-delivery-integrity/): unguarded it crashes every task that
imports it (ModuleNotFoundError); guarded by a bare ``except`` it silently disables
the feature while the UI still shows it enabled. This file scans every ``*.py`` under
``src/`` and fails on any import of a known backend-only path.

Careful: ``src.services`` and ``src.models`` alone must NOT be banned — the worker has
its own legit ``src/services/`` (automation_feedback_trigger.py, automation_churn_trigger.py,
health_recompute.py, ...) and ``src/models/`` packages. Only the enumerated backend-only
module paths are banned.

Deliberate exemption: imports that sit inside a ``try`` with an ``except ImportError``
handler are the documented, LOUD degradation seams (health_recompute.py:68,
segments.py:115 — both log or comment their unavailability and treat a missing service
as an optional signal, per GitHub issue #3). They are asserted here rather than assumed:
the AST check proves they are guarded, so the sweep only fails on the harmful cases —
an unguarded import (crashes the task) or one guarded by a bare/other ``except``
(swallows the failure silently).
"""
import ast
from pathlib import Path

# Backend-only module paths that worker source must never import.
# - src.api                            — backend-api's FastAPI routes; the worker has no src/api.
# - src.utils                          — backend-api's src/utils/encryption.py; the worker has
#                                        no src/utils package at all (intercom_sync.py used to
#                                        import it — the dead import this guard pins).
# - src.services.automation_engine     — the backend's full automations engine; the worker
#                                        carries its own mirror (automation_feedback_trigger.py)
#                                        precisely because this one cannot be imported.
# - src.services.health_score_service  — backend-only; the worker's documented seams
#                                        (health_recompute.py, segments.py) degrade instead.
# - src.models.feedback_workflow_event — submodule that exists in backend-api's src.models
#                                        but not in the worker's.
BACKEND_ONLY_IMPORT_PATHS = [
    "src.api",
    "src.utils",
    "src.services.automation_engine",
    "src.services.health_score_service",
    "src.models.feedback_workflow_event",
]

SRC_DIR = Path(__file__).resolve().parents[1] / "src"


def _is_guarded_import(node: ast.AST) -> bool:
    """True if the import node sits inside a try whose except handles ImportError.

    This is the documented degradation-seam exemption (health_recompute.py,
    segments.py). A bare `except Exception` is NOT a guard — it is the silent
    swallow this sweep exists to catch.
    """
    parent = node
    while parent is not None:
        parent = getattr(parent, "_parent", None)
        if parent is None:
            break
        if isinstance(parent, ast.Try):
            if any(
                isinstance(handler.type, ast.Name) and handler.type.id == "ImportError"
                for handler in parent.handlers
            ):
                return True
    return False


def _link_parents(tree: ast.AST) -> None:
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child._parent = node


def _violations(path: Path):
    tree = ast.parse(path.read_text())
    _link_parents(tree)
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            targets = [node.module] if node.module else []
        for target in targets:
            for banned in BACKEND_ONLY_IMPORT_PATHS:
                if target == banned or target.startswith(banned + "."):
                    if not _is_guarded_import(node):
                        yield banned, node.lineno, node.col_offset


def test_worker_source_never_imports_backend_only_modules():
    violations = []
    for py in sorted(SRC_DIR.rglob("*.py")):
        for banned, lineno, col in _violations(py):
            rel = py.relative_to(SRC_DIR)
            violations.append(f"{rel}:{lineno}:{col}: imports {banned!r}")

    assert not violations, (
        "worker source imports a backend-only module (unguarded):\n"
        + "\n".join(violations)
    )
