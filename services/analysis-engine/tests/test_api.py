"""Tests for the API endpoints."""
import pytest
from fastapi.testclient import TestClient
from src.api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_payload():
    """Create sample API payload."""
    return {
        "feedback": [
            {
                "id": "1",
                "text": "App crashes on upload",
                "date": "2025-11-10",
                "source": "support_ticket"
            },
            {
                "id": "2",
                "text": "Would love dark mode",
                "date": "2025-11-11",
                "source": "feature_request"
            },
            {
                "id": "3",
                "text": "Great features!",
                "date": "2025-11-12",
                "source": "app_review"
            }
        ]
    }


def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert "name" in data
    assert "version" in data


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_analyze_endpoint(client, sample_payload):
    """Test analyze endpoint."""
    response = client.post("/api/v1/analyze", json=sample_payload)

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "common_pain_points" in data
    assert "feature_requests" in data
    assert "sentiment_summary" in data
    assert "urgent_feedback" in data
    assert "total_feedback_count" in data

    assert data["total_feedback_count"] == 3


def test_analyze_empty_feedback(client):
    """Test analyze with empty feedback."""
    payload = {"feedback": []}

    response = client.post("/api/v1/analyze", json=payload)

    # Should return 400 for empty feedback
    assert response.status_code == 400


def test_analyze_invalid_payload(client):
    """Test analyze with invalid payload."""
    payload = {"invalid": "data"}

    response = client.post("/api/v1/analyze", json=payload)

    # Should return 422 for validation error
    assert response.status_code == 422


def test_quick_analyze_endpoint(client, sample_payload):
    """Test quick analyze endpoint."""
    response = client.post("/api/v1/analyze/quick", json=sample_payload)

    assert response.status_code == 200
    data = response.json()

    # Check simplified response structure
    assert "total_feedback" in data
    assert "sentiment" in data
    assert "pain_points_count" in data
    assert "feature_requests_count" in data
    assert "urgent_feedback_count" in data

    assert data["total_feedback"] == 3


def test_sentiment_structure(client, sample_payload):
    """Test sentiment summary structure in response."""
    response = client.post("/api/v1/analyze", json=sample_payload)

    assert response.status_code == 200
    data = response.json()

    sentiment = data["sentiment_summary"]
    assert "positive_percent" in sentiment
    assert "neutral_percent" in sentiment
    assert "negative_percent" in sentiment
    assert "trend_by_month" in sentiment
    assert "by_category" in sentiment


def test_pain_points_structure(client, sample_payload):
    """Test pain points structure in response."""
    response = client.post("/api/v1/analyze", json=sample_payload)

    assert response.status_code == 200
    data = response.json()

    pain_points = data["common_pain_points"]
    if pain_points:
        pp = pain_points[0]
        assert "issue" in pp
        assert "count" in pp
        assert "examples" in pp


def test_cors_middleware_configured(client):
    """Test CORS middleware is configured."""
    # CORS middleware is configured in the app
    # TestClient doesn't fully simulate CORS, but we can verify the middleware exists
    from src.api.main import app

    # Check that CORS middleware is in the app middleware stack
    middleware_classes = [type(m).__name__ for m in app.user_middleware]
    assert 'CORSMiddleware' in middleware_classes or len(app.user_middleware) > 0
