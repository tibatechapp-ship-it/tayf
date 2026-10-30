"""Contract tests for the health endpoint."""

from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "visionforge-backend"
    assert body["environment"] == "development"


def test_health_timestamp_is_utc_iso8601() -> None:
    body = client.get("/api/v1/health").json()

    parsed = datetime.fromisoformat(body["timestamp"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert parsed.utcoffset().total_seconds() == 0


def test_health_does_not_leak_configuration() -> None:
    body = client.get("/api/v1/health").json()

    assert set(body) == {"status", "service", "environment", "timestamp"}


def test_unknown_route_returns_404() -> None:
    assert client.get("/api/v1/does-not-exist").status_code == 404
