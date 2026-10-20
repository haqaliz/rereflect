"""
Pins worker-side health recomputation through the backend internal endpoint
(GitHub #3, option 1).

The worker has no scoring implementation and must not grow one: every recompute
is one HTTP POST to ``/api/v1/internal/health/recompute`` after the caller's
transaction commits, so the backend reads committed feedback/usage/CRM rows.
"""

from __future__ import annotations

import pathlib

import httpx
import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from src.services import health_recompute

URL = "http://backend:8000/api/v1/internal/health/recompute"

_Base = declarative_base()


class _Probe(_Base):
    __tablename__ = "health_recompute_probe"
    id = Column(Integer, primary_key=True)
    name = Column(String(20))


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_URL", "http://backend:8000/")
    monkeypatch.setenv("INTERNAL_API_SECRET", "s3cret")
    monkeypatch.setattr(health_recompute, "_warned", False)


@pytest.fixture()
def posts(monkeypatch, configured):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200, json={"status": "ok", "health_score": 50})

    monkeypatch.setattr(health_recompute.httpx, "post", fake_post)
    return calls


class TestMissingConfiguration:
    def test_returns_false_and_logs_once_per_process(self, monkeypatch, caplog):
        monkeypatch.delenv("INTERNAL_API_URL", raising=False)
        monkeypatch.delenv("INTERNAL_API_SECRET", raising=False)
        monkeypatch.setattr(health_recompute, "_warned", False)

        with caplog.at_level("ERROR"):
            first = health_recompute.request_health_recompute(1, "a@example.com", None)
            second = health_recompute.request_health_recompute(2, "b@example.com", None)

        assert first is False
        assert second is False
        matching = [r for r in caplog.records if "recompute is UNAVAILABLE" in r.message]
        assert len(matching) == 1, "expected exactly one report per process"
        assert "INTERNAL_API_URL" in matching[0].message
        assert "will not refresh" in matching[0].message


class TestAfterCommitScheduling:
    def test_posts_only_after_the_caller_commits(self, session, posts):
        session.add(_Probe(name="x"))
        session.flush()

        assert health_recompute.request_health_recompute(7, "c@example.com", session) is True
        assert posts == [], "must not POST while the transaction is open"

        session.commit()

        assert len(posts) == 1
        url, kwargs = posts[0]
        assert url == URL
        assert kwargs["json"] == {"org_id": 7, "customer_email": "c@example.com"}
        assert kwargs["headers"] == {"X-Internal-Secret": "s3cret"}
        assert kwargs["timeout"] == 5.0

    def test_rollback_means_no_post(self, session, posts):
        session.add(_Probe(name="x"))
        session.flush()

        assert health_recompute.request_health_recompute(7, "c@example.com", session) is True
        session.rollback()

        assert posts == []

    def test_idle_session_posts_immediately(self, session, posts):
        assert health_recompute.request_health_recompute(7, "c@example.com", session) is True

        assert len(posts) == 1


class TestFailuresNeverReachTheTask:
    def test_connection_error_is_logged_not_raised(self, session, monkeypatch, configured, caplog):
        def boom(url, **kwargs):
            raise httpx.ConnectError("backend down")

        monkeypatch.setattr(health_recompute.httpx, "post", boom)
        session.add(_Probe(name="x"))
        session.flush()
        health_recompute.request_health_recompute(9, "d@example.com", session)

        with caplog.at_level("ERROR"):
            session.commit()  # must not raise

        matching = [r for r in caplog.records if "org=9" in r.message and "d@example.com" in r.message]
        assert matching, "failure must name the org and email"

    def test_non_2xx_is_logged_not_raised(self, session, posts, monkeypatch, caplog):
        def failing(url, **kwargs):
            return httpx.Response(500, request=httpx.Request("POST", url))

        monkeypatch.setattr(health_recompute.httpx, "post", failing)
        session.add(_Probe(name="x"))
        session.flush()
        health_recompute.request_health_recompute(9, "d@example.com", session)

        with caplog.at_level("ERROR"):
            session.commit()

        assert any("d@example.com" in r.message for r in caplog.records)


class TestNoTaskImportsTheBackendServiceDirectly:
    def test_all_recompute_call_sites_go_through_the_seam(self):
        """segments.py is exempt: it needs compute_sentiment_trend rather than
        update_customer_health and guards its own import."""
        tasks_dir = pathlib.Path(__file__).parent.parent / "src" / "tasks"
        offenders = []
        for path in sorted(tasks_dir.glob("*.py")):
            if path.name == "segments.py":
                continue
            if "from src.services.health_score_service import" in path.read_text():
                offenders.append(path.name)

        assert not offenders, (
            f"{offenders} import health_score_service directly; route them "
            f"through src.services.health_recompute.request_health_recompute."
        )
