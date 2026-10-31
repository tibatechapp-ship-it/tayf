"""Stage 3 — project API integration tests.

Every route is proven twice: the happy path AND the refusal (bad input, foreign
owner, missing row). The session is the test session, so no request reaches the
development database.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_session
from app.main import app
from app.models import Project, ProjectStatus

BASE = "/api/v1/projects"


@pytest.fixture
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create(
    client: TestClient,
    owner_id,
    *,
    name: str = "Launch video",
    description: str | None = "First cut",
) -> dict:
    body: dict = {"name": name, "owner_id": str(owner_id)}
    if description is not None:
        body["description"] = description
    response = client.post(BASE, json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --- create ----------------------------------------------------------------


def test_create_returns_201_with_the_whole_contract(client, user):
    response = client.post(
        BASE, json={"name": "Launch video", "description": "First cut", "owner_id": str(user.id)}
    )

    assert response.status_code == 201
    body = response.json()
    # Exact key set: no internal column may leak, nothing the UI needs may be missing.
    assert set(body) == {
        "id",
        "owner_id",
        "name",
        "description",
        "status",
        "created_at",
        "updated_at",
    }
    assert body["owner_id"] == str(user.id)
    assert body["status"] == ProjectStatus.DRAFT.value
    assert uuid.UUID(body["id"])


def test_create_trims_whitespace(client, user):
    body = _create(client, user.id, name="   Padded name   ", description="  padded  ")
    assert body["name"] == "Padded name"
    assert body["description"] == "padded"


def test_create_without_description_defaults_to_null(client, user):
    body = _create(client, user.id, name="No description", description=None)
    assert body["description"] is None


def test_create_with_unknown_owner_is_400(client):
    response = client.post(BASE, json={"name": "Orphan", "owner_id": str(uuid.uuid4())})

    assert response.status_code == 400
    assert response.json()["detail"] == "Owner does not exist"


@pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
def test_create_with_blank_name_is_422(client, user, blank):
    response = client.post(BASE, json={"name": blank, "owner_id": str(user.id)})
    assert response.status_code == 422


def test_create_with_101_char_name_is_422(client, user):
    response = client.post(BASE, json={"name": "x" * 101, "owner_id": str(user.id)})
    assert response.status_code == 422


def test_create_with_100_char_name_is_accepted(client, user):
    body = _create(client, user.id, name="x" * 100)
    assert len(body["name"]) == 100


def test_create_with_501_char_description_is_422(client, user):
    response = client.post(
        BASE,
        json={"name": "ok", "description": "d" * 501, "owner_id": str(user.id)},
    )
    assert response.status_code == 422


def test_create_with_unexpected_field_is_422(client, user):
    """Mass assignment guard: a client may not set status/id itself."""
    response = client.post(
        BASE,
        json={"name": "Injected", "owner_id": str(user.id), "status": "active"},
    )
    assert response.status_code == 422


# --- read ------------------------------------------------------------------


def test_get_returns_the_project(client, user):
    created = _create(client, user.id)

    response = client.get(f"{BASE}/{created['id']}", params={"owner_id": str(user.id)})

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_unknown_project_is_404(client, user):
    response = client.get(f"{BASE}/{uuid.uuid4()}", params={"owner_id": str(user.id)})
    assert response.status_code == 404


def test_list_is_owner_scoped(client, user):
    _create(client, user.id, name="Mine")

    response = client.get(BASE, params={"owner_id": str(user.id)})

    assert response.status_code == 200
    names = [p["name"] for p in response.json()]
    assert names == ["Mine"]


def test_list_requires_owner_id(client):
    assert client.get(BASE).status_code == 422


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_list_rejects_bad_pagination(client, user, params):
    """Decision: invalid pagination is refused (422), never silently clamped."""
    response = client.get(BASE, params={"owner_id": str(user.id), **params})
    assert response.status_code == 422


def test_list_defaults_to_20_rows(client, user):
    for index in range(25):
        _create(client, user.id, name=f"Project {index:02d}")

    response = client.get(BASE, params={"owner_id": str(user.id)})

    assert response.status_code == 200
    assert len(response.json()) == 20


def test_list_paginates(client, user):
    for index in range(5):
        _create(client, user.id, name=f"Project {index}")

    page = client.get(BASE, params={"owner_id": str(user.id), "limit": 2, "offset": 2})

    assert page.status_code == 200
    assert len(page.json()) == 2


# --- update ----------------------------------------------------------------


def test_patch_changes_only_the_given_field(client, user):
    created = _create(client, user.id, name="Old name", description="keep me")

    response = client.patch(
        f"{BASE}/{created['id']}",
        params={"owner_id": str(user.id)},
        json={"name": "New name"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "New name"
    assert body["description"] == "keep me"  # untouched by a partial update
    assert body["updated_at"] >= created["updated_at"]


def test_patch_null_description_clears_it(client, user):
    created = _create(client, user.id, description="remove me")

    response = client.patch(
        f"{BASE}/{created['id']}",
        params={"owner_id": str(user.id)},
        json={"description": None},
    )

    assert response.status_code == 200
    assert response.json()["description"] is None


def test_patch_with_empty_body_is_a_noop(client, user):
    created = _create(client, user.id)

    response = client.patch(
        f"{BASE}/{created['id']}", params={"owner_id": str(user.id)}, json={}
    )

    assert response.status_code == 200
    assert response.json() == created


def test_patch_blank_name_is_422(client, user):
    created = _create(client, user.id)

    response = client.patch(
        f"{BASE}/{created['id']}", params={"owner_id": str(user.id)}, json={"name": "  "}
    )

    assert response.status_code == 422


def test_patch_unknown_project_is_404(client, user):
    response = client.patch(
        f"{BASE}/{uuid.uuid4()}", params={"owner_id": str(user.id)}, json={"name": "x"}
    )
    assert response.status_code == 404


# --- delete (soft) ---------------------------------------------------------


def test_delete_archives_and_is_idempotent(client, user):
    created = _create(client, user.id)

    first = client.delete(f"{BASE}/{created['id']}", params={"owner_id": str(user.id)})
    second = client.delete(f"{BASE}/{created['id']}", params={"owner_id": str(user.id)})

    assert first.status_code == 204
    assert first.content == b""
    assert second.status_code == 204  # already archived -> still 204


def test_archived_project_leaves_the_listing_but_stays_readable(client, user):
    created = _create(client, user.id)
    client.delete(f"{BASE}/{created['id']}", params={"owner_id": str(user.id)})

    listing = client.get(BASE, params={"owner_id": str(user.id)})
    assert listing.json() == []

    with_archived = client.get(
        BASE, params={"owner_id": str(user.id), "include_archived": "true"}
    )
    assert [p["id"] for p in with_archived.json()] == [created["id"]]

    # Soft delete keeps the row: the owner can still read it (status=archived).
    detail = client.get(f"{BASE}/{created['id']}", params={"owner_id": str(user.id)})
    assert detail.status_code == 200
    assert detail.json()["status"] == ProjectStatus.ARCHIVED.value


def test_delete_unknown_project_is_404(client, user):
    response = client.delete(f"{BASE}/{uuid.uuid4()}", params={"owner_id": str(user.id)})
    assert response.status_code == 404


# --- isolation (the critical one) ------------------------------------------


@pytest.fixture
def foreign_project(client, user, other_user):
    """A project owned by ``user``, targeted by ``other_user``."""
    return _create(client, user.id, name="Private to A")


def test_isolation_get_returns_404_not_403(client, foreign_project, other_user):
    response = client.get(
        f"{BASE}/{foreign_project['id']}", params={"owner_id": str(other_user.id)}
    )

    # 404 hides existence; 403 would confirm "this id is real, just not yours".
    assert response.status_code == 404
    assert response.status_code != 403
    assert response.json()["detail"] == "Project not found"


def test_isolation_patch_returns_404_and_changes_nothing(
    client, session, foreign_project, other_user, user
):
    response = client.patch(
        f"{BASE}/{foreign_project['id']}",
        params={"owner_id": str(other_user.id)},
        json={"name": "Hijacked"},
    )

    assert response.status_code == 404
    stored = session.get(Project, uuid.UUID(foreign_project["id"]))
    assert stored is not None and stored.name == "Private to A"


def test_isolation_delete_returns_404_and_keeps_the_project(
    client, session, foreign_project, other_user
):
    response = client.delete(
        f"{BASE}/{foreign_project['id']}", params={"owner_id": str(other_user.id)}
    )

    assert response.status_code == 404
    stored = session.get(Project, uuid.UUID(foreign_project["id"]))
    assert stored is not None and stored.status == ProjectStatus.DRAFT


def test_isolation_list_never_leaks_other_projects(client, foreign_project, other_user, user):
    stranger_list = client.get(BASE, params={"owner_id": str(other_user.id)})
    owner_list = client.get(BASE, params={"owner_id": str(user.id)})

    assert stranger_list.json() == []
    assert [p["id"] for p in owner_list.json()] == [foreign_project["id"]]


# --- contract surface ------------------------------------------------------


def test_openapi_documents_every_project_route(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert sorted(paths["/api/v1/projects"]) == ["get", "post"]
    assert sorted(paths["/api/v1/projects/{project_id}"]) == ["delete", "get", "patch"]
    # The route declares its refusal codes, so Swagger shows them.
    assert "404" in paths["/api/v1/projects/{project_id}"]["get"]["responses"]
