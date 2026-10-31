"""Project API tests — now behind JWT auth (the Stage-3 owner_id param is gone)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_projects_require_auth(client: TestClient) -> None:
    assert client.get("/api/v1/projects").status_code == 401
    assert client.post("/api/v1/projects", json={"name": "x"}).status_code == 401


def test_create_project_201_with_defaults(client: TestClient, auth_headers) -> None:
    headers, data = auth_headers
    response = client.post(
        "/api/v1/projects",
        json={"name": "  My first film  ", "description": " demo "},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "My first film"
    assert body["description"] == "demo"
    assert body["status"] == "draft"
    assert body["owner_id"] == data["user"]["id"]
    assert body["job_count"] == 0


def test_create_project_rejects_unknown_and_blank_fields(client: TestClient, auth_headers) -> None:
    headers, _ = auth_headers
    assert (
        client.post(
            "/api/v1/projects",
            json={"name": "x", "owner_id": "00000000-0000-0000-0000-000000000000"},
            headers=headers,
        ).status_code
        == 422
    )  # owner_id mass-assignment is forbidden
    assert (
        client.post("/api/v1/projects", json={"name": "   "}, headers=headers).status_code
        == 422
    )


def test_listing_is_scoped_to_the_caller(client: TestClient, auth_headers) -> None:
    headers, _ = auth_headers
    client.post("/api/v1/projects", json={"name": "mine"}, headers=headers)

    # a second user sees nothing of the first user's projects
    other = register_other(client)
    response = client.get("/api/v1/projects", headers=other)
    assert response.status_code == 200
    assert response.json() == []

    mine = client.get("/api/v1/projects", headers=headers).json()
    assert [p["name"] for p in mine] == ["mine"]


def test_get_patch_and_soft_delete_flow(client: TestClient, auth_headers) -> None:
    headers, _ = auth_headers
    project = client.post(
        "/api/v1/projects", json={"name": "flow", "description": "v1"}, headers=headers
    ).json()

    # partial update keeps description when absent...
    patched = client.patch(
        f"/api/v1/projects/{project['id']}", json={"name": "flow2"}, headers=headers
    ).json()
    assert patched["name"] == "flow2"
    assert patched["description"] == "v1"

    # ...and an explicit null CLEARS it
    patched = client.patch(
        f"/api/v1/projects/{project['id']}", json={"description": None}, headers=headers
    ).json()
    assert patched["description"] is None

    # soft delete: hidden from the default list, still available explicitly
    assert (
        client.delete(f"/api/v1/projects/{project['id']}", headers=headers).status_code
        == 204
    )
    assert client.get("/api/v1/projects", headers=headers).json() == []
    archived = client.get(
        "/api/v1/projects", headers=headers, params={"include_archived": True}
    ).json()
    assert [p["status"] for p in archived] == ["archived"]


def test_other_user_gets_404_not_403(client: TestClient, auth_headers) -> None:
    headers, _ = auth_headers
    project = client.post(
        "/api/v1/projects", json={"name": "private"}, headers=headers
    ).json()

    other = register_other(client)
    for method, path, kwargs in [
        ("get", f"/api/v1/projects/{project['id']}", {}),
        ("patch", f"/api/v1/projects/{project['id']}", {"json": {"name": "stolen"}}),
        ("delete", f"/api/v1/projects/{project['id']}", {}),
    ]:
        response = getattr(client, method)(path, headers=other, **kwargs)
        assert response.status_code == 404, (method, response.text)


def test_job_count_is_enriched(client: TestClient, auth_headers, project_id: str) -> None:
    headers, _ = auth_headers
    assert client.get(f"/api/v1/projects/{project_id}", headers=headers).json()["job_count"] == 0
    client.post(
        f"/api/v1/projects/{project_id}/jobs",
        json={"prompt": "a quiet harbor at dusk", "num_scenes": 2},
        headers=headers,
    )
    # the rejected/processing/completed job exists -> count 1 (no polling needed)
    assert client.get(f"/api/v1/projects/{project_id}", headers=headers).json()["job_count"] == 1


def register_other(client: TestClient) -> dict[str, str]:
    from tests.conftest import register_and_login

    data = register_and_login(client, username="other_user")
    return {"Authorization": f"Bearer {data['access_token']}"}
