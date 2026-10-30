"""initial schema: users, projects, generation_jobs

Revision ID: a347dd0c8c67
Revises:
Create Date: 2026-10-31

Portability notes (this file must stay engine-neutral):
- ``sa.Uuid()`` → native UUID on PostgreSQL, CHAR(32) on SQLite.
- ``sa.Enum(..., native_enum=False, create_constraint=True)`` → VARCHAR + CHECK
  on both engines (no native enum type to migrate later).
- ``sa.JSON()`` → JSONB-compatible JSON on PostgreSQL, TEXT-backed JSON on SQLite.
- No ALTERs here, so the migration is identical on both engines.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a347dd0c8c67"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "active",
                "archived",
                name="project_status",
                native_enum=False,
                create_constraint=True,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_projects_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(
        "ix_projects_user_id_created_at",
        "projects",
        ["user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("input_params", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "completed",
                "failed",
                name="generation_status",
                native_enum=False,
                create_constraint=True,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_url", sa.String(length=1024), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_generation_jobs_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_generation_jobs")),
    )
    op.create_index(
        "ix_generation_jobs_project_id_created_at",
        "generation_jobs",
        ["project_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_generation_jobs_project_id_created_at", table_name="generation_jobs"
    )
    op.drop_table("generation_jobs")
    op.drop_index("ix_projects_user_id_created_at", table_name="projects")
    op.drop_table("projects")
    op.drop_table("users")
