"""
Pins the real, unmocked state of worker-side health recomputation (GitHub #3).

Every other worker test that touches this path injects a fake
``src.services.health_score_service`` into ``sys.modules`` before importing the
task under test. That makes the lazy import succeed, so those tests assert the
recompute is *called* while production cannot call it at all — which is why the
gap survived so long. These tests deliberately do not mock, so they describe
what actually happens when the worker runs.
"""

from __future__ import annotations

import importlib
import sys

import pytest


def _purge_health_score_service():
    """Drop any mock a previously-imported test module left in sys.modules."""
    sys.modules.pop("src.services.health_score_service", None)


class TestHealthScoreServiceIsAbsentFromTheWorker:
    def test_import_fails_in_the_worker_package(self):
        """The backend module is not shipped in the worker image.

        This is the root cause of #3. It is asserted rather than xfailed so the
        assertion inverts loudly the moment someone makes the module available:
        this test then fails and must be updated together with the seam.
        """
        _purge_health_score_service()
        with pytest.raises(ImportError):
            importlib.import_module("src.services.health_score_service")


class TestSeamDegradesInsteadOfRaising:
    def test_request_health_recompute_returns_false_when_unavailable(self):
        _purge_health_score_service()
        from src.services import health_recompute

        health_recompute._warned = False  # reset the once-per-process latch
        assert health_recompute.request_health_recompute(1, "a@example.com", None) is False

    def test_it_logs_once_per_process_at_error_level(self, caplog):
        _purge_health_score_service()
        from src.services import health_recompute

        health_recompute._warned = False
        with caplog.at_level("ERROR"):
            health_recompute.request_health_recompute(1, "a@example.com", None)
            health_recompute.request_health_recompute(1, "b@example.com", None)

        matching = [r for r in caplog.records if "recompute is UNAVAILABLE" in r.message]
        assert len(matching) == 1, "expected exactly one report per process"
        assert "issue #3" in matching[0].message

    def test_it_runs_the_recompute_when_the_service_is_available(self, monkeypatch):
        """The seam is a pass-through, not a permanent stub.

        Proves the fix path works end to end: once the module exists, the seam
        calls it with the caller's arguments and reports True.
        """
        import types

        _purge_health_score_service()
        calls = []
        fake = types.ModuleType("src.services.health_score_service")
        fake.update_customer_health = lambda org_id, email, db: calls.append((org_id, email, db))
        monkeypatch.setitem(sys.modules, "src.services.health_score_service", fake)

        from src.services import health_recompute

        sentinel = object()
        assert health_recompute.request_health_recompute(7, "c@example.com", sentinel) is True
        assert calls == [(7, "c@example.com", sentinel)]

    def test_recompute_errors_still_propagate(self, monkeypatch):
        """Only the unavailable case is swallowed — real failures reach the task."""
        import types

        _purge_health_score_service()
        fake = types.ModuleType("src.services.health_score_service")

        def _boom(org_id, email, db):
            raise RuntimeError("db exploded")

        fake.update_customer_health = _boom
        monkeypatch.setitem(sys.modules, "src.services.health_score_service", fake)

        from src.services import health_recompute

        with pytest.raises(RuntimeError, match="db exploded"):
            health_recompute.request_health_recompute(1, "d@example.com", None)


class TestNoTaskImportsTheBackendServiceDirectly:
    def test_all_recompute_call_sites_go_through_the_seam(self):
        """Keeps the fix to a single place.

        segments.py is exempt: it needs compute_sentiment_trend rather than
        update_customer_health and guards its own import, degrading to
        direction=None so the daily segment recompute still runs.
        """
        import pathlib

        tasks_dir = pathlib.Path(__file__).parent.parent / "src" / "tasks"
        offenders = []
        for path in sorted(tasks_dir.glob("*.py")):
            if path.name == "segments.py":
                continue
            if "from src.services.health_score_service import" in path.read_text():
                offenders.append(path.name)

        assert not offenders, (
            f"{offenders} import health_score_service directly; route them "
            f"through src.services.health_recompute.request_health_recompute "
            f"so GitHub #3 has one fix site."
        )
