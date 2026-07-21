"""
AC 15 (trend-detection-and-health): usage_score_service.py must stay
byte-identical between backend-api and worker-service — both files carry the
"DUPLICATED: keep in sync" header at the top (see TRACKING.md). Unlike
classifier_predict.py / classifier_resolver.py (which legitimately differ in
docstring + one import line — see test_classifier_predict_mirror.py), this
module has no legitimate per-service differences: same import path
(src.services.usage_score_service) in both trees, no models, no I/O. The
comparison is a plain byte-for-byte diff, no normalization.
"""
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_FILE = (
    _REPO_ROOT / "services" / "backend-api" / "src" / "services" / "usage_score_service.py"
)
_WORKER_FILE = (
    _REPO_ROOT / "services" / "worker-service" / "src" / "services" / "usage_score_service.py"
)


def test_usage_score_service_byte_identical_across_services():
    backend_text = _BACKEND_FILE.read_text()
    worker_text = _WORKER_FILE.read_text()

    assert backend_text == worker_text, (
        "usage_score_service.py has drifted between backend-api and "
        "worker-service — both copies must be byte-identical (AC 15)."
    )
