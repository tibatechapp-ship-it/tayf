"""System-level tests: security headers, request-ID propagation, version endpoint."""

from app.main import app


def test_security_headers_on_every_response(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "camera=()" in response.headers["Permissions-Policy"]


def test_request_id_echoed_when_valid(client):
    response = client.get("/api/v1/health", headers={"X-Request-ID": "client-rid-0001"})
    assert response.headers["X-Request-ID"] == "client-rid-0001"


def test_request_id_generated_when_missing_or_unsafe(client):
    missing = client.get("/api/v1/health")
    generated = missing.headers["X-Request-ID"]
    assert 8 <= len(generated) <= 64

    unsafe = client.get("/api/v1/health", headers={"X-Request-ID": "bad rid with spaces!"})
    assert unsafe.headers["X-Request-ID"] != "bad rid with spaces!"


def test_version_endpoint_reports_build_and_runtime(client):
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == app.version == "0.5.0"
    assert body["api_prefix"] == "/api/v1"
    assert body["python_version"].startswith("3.")
    assert body["storage_backend"] == "local"
    assert body["ai_provider"] == "mock"
