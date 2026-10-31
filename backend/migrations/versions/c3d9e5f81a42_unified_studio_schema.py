"""unified studio schema: auth identity, job pipeline columns, credit ledger

Revision ID: c3d9e5f81a42
Revises: a347dd0c8c67
Create Date: 2026-10-31

Merge migration (VisionForge features into the Tayf data model):

- users:           + username (unique login identifier)
- generation_jobs: + pipeline columns (prompt, num_scenes, aspect, style,
                     simulated, rejection fields, storyboard JSON, thumbnail,
                     video size/duration, credits_charged)
- generation_jobs: generation_status CHECK extended with 'rejected' and
                     'cancelled'
- credit_ledger:   NEW append-only table (delta, balance_after, reason)

Portability notes:
- Written with ``op.batch_alter_table`` so it runs unchanged on SQLite
  (table-recreate batch mode) and PostgreSQL (plain ALTERs).
- Pre-launch caveat: existing dev databases may hold at most ONE user per
  database, because backfilling ``username`` with '' cannot satisfy a UNIQUE
  constraint for several rows. Production deployments (none exist yet) should
  backfill usernames before upgrading.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d9e5f81a42"
down_revision: Union[str, Sequence[str], None] = "a347dd0c8c67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_STATUS_VALUES = ("pending", "processing", "completed", "failed")
NEW_STATUS_VALUES = (
    "pending",
    "processing",
    "completed",
    "failed",
    "rejected",
    "cancelled",
)


def _status_enum(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(
        *values,
        name="generation_status",
        native_enum=False,
        create_constraint=True,
        length=24,
    )


def upgrade() -> None:
    # --- users.username -----------------------------------------------------
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("username", sa.String(length=32), nullable=False, server_default="")
        )
        batch.create_unique_constraint(op.f("uq_users_username"), ["username"])

    # --- generation_jobs: pipeline columns ----------------------------------
    with op.batch_alter_table("generation_jobs") as batch:
        batch.add_column(sa.Column("prompt", sa.Text(), nullable=False, server_default=""))
        batch.add_column(
            sa.Column("num_scenes", sa.Integer(), nullable=False, server_default="4")
        )
        batch.add_column(
            sa.Column("aspect", sa.String(length=10), nullable=False, server_default="16:9")
        )
        batch.add_column(
            sa.Column("style", sa.String(length=40), nullable=False, server_default="cinematic")
        )
        batch.add_column(
            sa.Column(
                "simulated", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
        batch.add_column(sa.Column("rejection_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("safety_category", sa.String(length=40), nullable=True))
        batch.add_column(sa.Column("storyboard", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("thumbnail_url", sa.String(length=1024), nullable=True))
        batch.add_column(sa.Column("video_size_bytes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("duration_seconds", sa.Float(), nullable=True))
        batch.add_column(
            sa.Column("credits_charged", sa.Integer(), nullable=False, server_default="0")
        )

    # --- generation_jobs: extend the status CHECK ---------------------------
    # NOTE: the bare constraint name goes through the naming convention
    # (ck_<table>_<constraint>) so this matches what the models produce.
    with op.batch_alter_table("generation_jobs") as batch:
        batch.drop_constraint("generation_status", type_="check")
        batch.create_check_constraint(
            "generation_status",
            "status IN ('pending', 'processing', 'completed', 'failed', "
            "'rejected', 'cancelled')",
        )

    # --- credit_ledger -------------------------------------------------------
    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_credit_ledger_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["generation_jobs.id"],
            name=op.f("fk_credit_ledger_job_id_generation_jobs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credit_ledger")),
    )
    op.create_index(
        op.f("ix_credit_ledger_user_id"), "credit_ledger", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_credit_ledger_user_id"), table_name="credit_ledger")
    op.drop_table("credit_ledger")

    with op.batch_alter_table("generation_jobs") as batch:
        batch.drop_constraint("generation_status", type_="check")
        batch.create_check_constraint(
            "generation_status",
            "status IN ('pending', 'processing', 'completed', 'failed')",
        )
        batch.drop_column("credits_charged")
        batch.drop_column("duration_seconds")
        batch.drop_column("video_size_bytes")
        batch.drop_column("thumbnail_url")
        batch.drop_column("storyboard")
        batch.drop_column("safety_category")
        batch.drop_column("rejection_reason")
        batch.drop_column("simulated")
        batch.drop_column("style")
        batch.drop_column("aspect")
        batch.drop_column("num_scenes")
        batch.drop_column("prompt")

    with op.batch_alter_table("users") as batch:
        batch.drop_constraint(op.f("uq_users_username"), type_="unique")
        batch.drop_column("username")
