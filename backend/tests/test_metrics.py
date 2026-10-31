"""/metrics: Prometheus text exposition of aggregate counters (no user data)."""

import re


def test_metrics_endpoint_renders_prometheus_text(client):
    # generate some traffic first
    client.get("/api/v1/health")
    client.get("/api/v1/version")
    response = client.get("/api/v1/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "# TYPE tayf_http_requests_total counter" in body
    assert re.search(r'tayf_http_requests_total\{method="GET",status="200"\} \d+', body)


def test_metrics_counters_increase_with_requests(client):
    before = client.get("/api/v1/metrics").text
    client.get("/api/v1/health")
    client.get("/api/v1/health")
    after = client.get("/api/v1/metrics").text

    def count(body: str) -> int:
        match = re.search(r'tayf_http_requests_total\{method="GET",status="200"\} (\d+)', body)
        return int(match.group(1)) if match else 0

    assert count(after) >= count(before) + 2


def test_metrics_have_no_user_identifiers(client):
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "metrics-leak@example.com",
            "username": "metricsleak",
            "password": "Sup3rSecret!",
        },
    )
    body = client.get("/api/v1/metrics").text
    assert "metrics-leak@example.com" not in body
    assert "metricsleak" not in body


def test_metrics_can_be_disabled(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "METRICS_ENABLED", False)
    response = client.get("/api/v1/metrics")
    assert response.status_code == 404


def test_job_and_credit_counters_recorded(client, project_id, auth_headers):
    headers, _ = auth_headers
    created = client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": "metrics pipeline run", "num_scenes": 2},
        headers=headers,
    )
    assert created.status_code == 202
    body = client.get("/api/v1/metrics").text
    assert re.search(r'tayf_credits_total\{kind="charged"\} \d+', body)
    assert re.search(r'tayf_credits_total\{kind="granted"\} \d+', body)
    assert re.search(r'tayf_jobs_total\{status="completed"\} \d+', body)
