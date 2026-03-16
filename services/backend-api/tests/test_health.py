"""
Tests for /health/detailed endpoint.
TDD cycles for enhanced health check (Phase 5).
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.api.main import app
from src.database.session import get_db
from src.api.dependencies import get_current_user, require_system_admin
from src.models.user import User
from src.models.organization import Organization
from src.api.auth import hash_password, create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def system_admin_user(db: Session, test_organization: Organization) -> User:
    """Create a user with is_system_admin=True."""
    user = User(
        email="sysadmin@example.com",
        password_hash=hash_password("adminpass123"),
        organization_id=test_organization.id,
        role="owner",
        is_system_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def system_admin_token(system_admin_user: User) -> str:
    return create_access_token({
        "user_id": system_admin_user.id,
        "organization_id": system_admin_user.organization_id,
        "role": system_admin_user.role,
    })


@pytest.fixture
def system_admin_headers(system_admin_token: str) -> dict:
    return {"Authorization": f"Bearer {system_admin_token}"}


@pytest.fixture
def client_with_admin(db: Session, system_admin_user: User) -> TestClient:
    """TestClient whose db session is the same fixture db, authenticated as system admin."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        token = create_access_token({
            "user_id": system_admin_user.id,
            "organization_id": system_admin_user.organization_id,
            "role": system_admin_user.role,
        })
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def regular_user(db: Session, test_organization: Organization) -> User:
    """Create a regular (non-admin) user."""
    user = User(
        email="regular@example.com",
        password_hash=hash_password("pass123"),
        organization_id=test_organization.id,
        role="member",
        is_system_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def client_with_regular_user(db: Session, regular_user: User) -> TestClient:
    """TestClient authenticated as a regular (non-system-admin) user."""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        token = create_access_token({
            "user_id": regular_user.id,
            "organization_id": regular_user.organization_id,
            "role": regular_user.role,
        })
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Cycle 1: Database connectivity check
# ---------------------------------------------------------------------------

class TestDetailedHealthDatabase:
    """Cycle 1 — /health/detailed returns database status."""

    def test_detailed_health_returns_db_status(self, client_with_admin: TestClient):
        response = client_with_admin.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert "database" in data
        assert data["database"]["status"] in ("ok", "error")

    def test_detailed_health_db_status_ok_when_db_reachable(self, client_with_admin: TestClient):
        """When the database is reachable, status should be 'ok'."""
        response = client_with_admin.get("/health/detailed")
        assert response.status_code == 200
        assert response.json()["database"]["status"] == "ok"

    def test_detailed_health_db_includes_latency_ms(self, client_with_admin: TestClient):
        """Database check should include latency_ms as a non-negative number."""
        response = client_with_admin.get("/health/detailed")
        assert response.status_code == 200
        db_info = response.json()["database"]
        assert "latency_ms" in db_info
        assert isinstance(db_info["latency_ms"], (int, float))
        assert db_info["latency_ms"] >= 0

    def test_detailed_health_top_level_status_present(self, client_with_admin: TestClient):
        """Top-level status field must be present."""
        response = client_with_admin.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ("healthy", "degraded", "unhealthy")


# ---------------------------------------------------------------------------
# Cycle 2: Redis connectivity check
# ---------------------------------------------------------------------------

class TestDetailedHealthRedis:
    """Cycle 2 — /health/detailed returns redis field."""

    def test_detailed_health_returns_redis_status(self, client_with_admin: TestClient):
        response = client_with_admin.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert "redis" in data
        assert data["redis"]["status"] in ("ok", "error", "disabled")

    def test_detailed_health_redis_includes_latency_ms(self, client_with_admin: TestClient):
        """Redis check should include latency_ms when Redis is reachable."""
        response = client_with_admin.get("/health/detailed")
        assert response.status_code == 200
        redis_info = response.json()["redis"]
        assert "latency_ms" in redis_info
        # latency_ms may be None when Redis is disabled/error, otherwise non-negative
        if redis_info["latency_ms"] is not None:
            assert isinstance(redis_info["latency_ms"], (int, float))
            assert redis_info["latency_ms"] >= 0

    def test_detailed_health_redis_error_does_not_crash_endpoint(self, client_with_admin: TestClient):
        """Even when Redis is unreachable, the endpoint must return 200."""
        with patch("src.api.routes.health.redis.Redis") as mock_redis_cls:
            mock_instance = MagicMock()
            mock_instance.ping.side_effect = Exception("connection refused")
            mock_redis_cls.return_value = mock_instance

            response = client_with_admin.get("/health/detailed")
            # Endpoint must not blow up — either 200 with error status or still 200
            assert response.status_code == 200
            data = response.json()
            assert "redis" in data


# ---------------------------------------------------------------------------
# Cycle 3: System admin gating
# ---------------------------------------------------------------------------

class TestDetailedHealthAuthGating:
    """Cycle 3 — /health/detailed is system-admin only."""

    def test_detailed_health_requires_authentication(self, client: TestClient):
        """Unauthenticated request must return 401 or 403."""
        response = client.get("/health/detailed")
        assert response.status_code in (401, 403)

    def test_detailed_health_returns_403_for_non_system_admin(
        self, client_with_regular_user: TestClient
    ):
        """A regular authenticated user (is_system_admin=False) must get 403."""
        response = client_with_regular_user.get("/health/detailed")
        assert response.status_code == 403

    def test_detailed_health_returns_200_for_system_admin(
        self, client_with_admin: TestClient
    ):
        """A system admin must receive 200."""
        response = client_with_admin.get("/health/detailed")
        assert response.status_code == 200

    def test_detailed_health_403_has_meaningful_message(
        self, client_with_regular_user: TestClient
    ):
        """403 response should carry a detail message."""
        response = client_with_regular_user.get("/health/detailed")
        assert response.status_code == 403
        data = response.json()
        assert "detail" in data


# ---------------------------------------------------------------------------
# Cycle 4: Memory and uptime
# ---------------------------------------------------------------------------

class TestDetailedHealthMemoryUptime:
    """Cycle 4 — /health/detailed returns memory_mb, uptime_seconds, and version."""

    def test_detailed_health_returns_memory_mb(self, client_with_admin: TestClient):
        response = client_with_admin.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert "memory_mb" in data
        assert isinstance(data["memory_mb"], (int, float))
        assert data["memory_mb"] > 0

    def test_detailed_health_returns_uptime_seconds(self, client_with_admin: TestClient):
        response = client_with_admin.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert "uptime_seconds" in data
        assert isinstance(data["uptime_seconds"], (int, float))
        assert data["uptime_seconds"] >= 0

    def test_detailed_health_returns_version(self, client_with_admin: TestClient):
        response = client_with_admin.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0

    def test_detailed_health_version_matches_app_version(self, client_with_admin: TestClient):
        """Version in response should match the FastAPI app version."""
        from src.api.main import app as fastapi_app
        response = client_with_admin.get("/health/detailed")
        assert response.status_code == 200
        assert response.json()["version"] == fastapi_app.version

    def test_detailed_health_returns_worker_status(self, client_with_admin: TestClient):
        """Response must include a worker field."""
        response = client_with_admin.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert "worker" in data
        assert data["worker"]["status"] in ("ok", "error", "unknown")

    def test_detailed_health_full_schema(self, client_with_admin: TestClient):
        """Smoke-test: all required top-level keys are present."""
        response = client_with_admin.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()
        required_keys = {"status", "database", "redis", "worker", "memory_mb", "uptime_seconds", "version"}
        assert required_keys.issubset(data.keys())
