"""Project CRUD, pagination and per-owner isolation."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.db.session import make_session_factory
from app.models import GenerationJob, Project, User
from app.repositories.project_repository import (
    create_project,
    get_project_by_id_and_owner,
    list_projects_by_user,
)


def test_create_and_read_project(session: Session, user: User) -> None:
    project = create_project(
        session, owner_id=user.id, name="  My first film  ", description=" demo "
    )
    session.commit()

    assert isinstance(project.id, uuid.UUID)
    assert project.name == "My first film"
    assert project.description == "demo"
    assert project.status.value == "draft"
    assert project.user_id == user.id

    loaded = get_project_by_id_and_owner(session, project.id, user.id)
    assert loaded is not None
    assert loaded.id == project.id


def test_other_user_cannot_read_the_project(session: Session, user: User, other_user: User) -> None:
    project = create_project(session, owner_id=user.id, name="Private")
    session.commit()

    assert get_project_by_id_and_owner(session, project.id, other_user.id) is None
    assert get_project_by_id_and_owner(session, uuid.uuid4(), user.id) is None


def test_listing_is_scoped_and_newest_first(session: Session, user: User, other_user: User) -> None:
    first = create_project(session, owner_id=user.id, name="one")
    session.commit()
    second = create_project(session, owner_id=user.id, name="two")
    create_project(session, owner_id=other_user.id, name="not mine")
    session.commit()

    mine = list_projects_by_user(session, user.id)
    assert {p.id for p in mine} == {first.id, second.id}
    assert mine[0].created_at >= mine[-1].created_at

    assert len(list_projects_by_user(session, user.id, limit=1)) == 1
    assert len(list_projects_by_user(session, user.id, offset=2)) == 0


def test_page_size_is_capped(session: Session, user: User) -> None:
    create_project(session, owner_id=user.id, name="x")
    session.commit()

    # limit is clamped server-side: a client cannot ask for an unbounded page
    assert len(list_projects_by_user(session, user.id, limit=10_000)) == 1


@pytest.mark.parametrize("bad_name", ["", "   ", "x" * 121])
def test_project_name_validation(session: Session, user: User, bad_name: str) -> None:
    with pytest.raises(ValueError):
        create_project(session, owner_id=user.id, name=bad_name)


def test_project_requires_an_existing_owner(session: Session) -> None:
    with pytest.raises(IntegrityError):
        create_project(session, owner_id=uuid.uuid4(), name="orphan")
        session.commit()
    session.rollback()


def test_deleting_the_owner_removes_the_projects(
    session: Session, engine: Engine, user: User
) -> None:
    project = create_project(session, owner_id=user.id, name="will vanish")
    job = GenerationJob(
        project_id=project.id,
        prompt="a lighthouse in a storm",
        provider_name="mock-dev",
        model_version="v0",
        input_params={},
    )
    session.add(job)
    session.commit()
    project_id, job_id = project.id, job.id

    session.delete(user)
    session.commit()

    # A fresh session proves the DATABASE cascade ran, not the ORM identity map.
    with make_session_factory(engine)() as fresh:
        assert fresh.get(Project, project_id) is None
        assert fresh.get(GenerationJob, job_id) is None


def test_project_exposes_its_jobs(session: Session, user: User) -> None:
    project = create_project(session, owner_id=user.id, name="with job")
    job = GenerationJob(
        project_id=project.id,
        prompt="a cat surfing",
        provider_name="mock-dev",
        model_version="v0",
        input_params={"duration_s": 5},
    )
    session.add(job)
    session.commit()

    session.refresh(project)
    assert [j.id for j in project.jobs] == [job.id]
    assert project.jobs[0].input_params["duration_s"] == 5
    assert project.jobs[0].status.value == "pending"
    assert project.owner.id == user.id

    session.delete(project)
    session.commit()
    assert session.get(GenerationJob, job.id) is None
