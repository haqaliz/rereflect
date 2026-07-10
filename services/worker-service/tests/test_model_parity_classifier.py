"""
Backend <-> worker column-parity characterization tests for M5.2 classifier
models (data-layer aspect R5 mitigation).

Same sys.path/sys.modules swap technique as
test_zendesk_adapter.py::TestModelsAndMigration.
"""

import os
import sys


def _backend_columns(module_path: str, class_name: str) -> set:
    """
    Import `class_name` from `module_path` in services/backend-api, snapshot
    its column names, then restore the worker's `src.*` modules.
    """
    worktree = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    backend_src = os.path.join(worktree, "services", "backend-api")

    saved_mods = {k: v for k, v in sys.modules.items() if k == "src" or k.startswith("src.")}
    for k in saved_mods:
        del sys.modules[k]

    sys.path.insert(0, backend_src)
    try:
        module = __import__(module_path, fromlist=[class_name])
        backend_model = getattr(module, class_name)
        return {c.name for c in backend_model.__table__.columns}
    finally:
        sys.path.remove(backend_src)
        for k in list(sys.modules.keys()):
            if k == "src" or k.startswith("src."):
                del sys.modules[k]
        sys.modules.update(saved_mods)


class TestModelsAndMigration:
    def test_worker_and_backend_org_classifier_model_columns_match(self):
        from src.models import OrgClassifierModel as WorkerModel
        worker_cols = {c.name for c in WorkerModel.__table__.columns}

        backend_cols = _backend_columns("src.models.org_classifier", "OrgClassifierModel")

        assert worker_cols == backend_cols, (
            f"Column mismatch!\n"
            f"  Worker only:  {worker_cols - backend_cols}\n"
            f"  Backend only: {backend_cols - worker_cols}"
        )

    def test_worker_and_backend_org_classifier_eval_run_columns_match(self):
        from src.models import OrgClassifierEvalRun as WorkerModel
        worker_cols = {c.name for c in WorkerModel.__table__.columns}

        backend_cols = _backend_columns("src.models.org_classifier", "OrgClassifierEvalRun")

        assert worker_cols == backend_cols, (
            f"Column mismatch!\n"
            f"  Worker only:  {worker_cols - backend_cols}\n"
            f"  Backend only: {backend_cols - worker_cols}"
        )

    def test_worker_and_backend_ai_correction_columns_match(self):
        from src.models import AICorrection as WorkerModel
        worker_cols = {c.name for c in WorkerModel.__table__.columns}

        backend_cols = _backend_columns("src.models.ai_correction", "AICorrection")

        assert worker_cols == backend_cols, (
            f"Column mismatch!\n"
            f"  Worker only:  {worker_cols - backend_cols}\n"
            f"  Backend only: {backend_cols - worker_cols}"
        )

    def test_worker_and_backend_org_ai_config_columns_match(self):
        """Catches classifier_mode drift on OrgAIConfig too."""
        from src.models import OrgAIConfig as WorkerModel
        worker_cols = {c.name for c in WorkerModel.__table__.columns}

        backend_cols = _backend_columns("src.models.org_ai_config", "OrgAIConfig")

        assert worker_cols == backend_cols, (
            f"Column mismatch!\n"
            f"  Worker only:  {worker_cols - backend_cols}\n"
            f"  Backend only: {backend_cols - worker_cols}"
        )
