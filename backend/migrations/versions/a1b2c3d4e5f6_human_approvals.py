"""add optional human approval gates

Revision ID: a1b2c3d4e5f6
Revises: f6a8c3e2b4d7
Create Date: 2026-11-18

- ``require_approvals`` is opt-in per job, so existing jobs and automated
  pipelines are unchanged.
- ``pending_approval`` holds the currently open gate plus the storage keys
  needed to resume without re-generating (and re-paying for) assets.
- ``approval_history`` is an immutable audit trail of approve/reject decisions.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f6a8c3e2b4d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("generation_jobs") as batch:
        batch.add_column(
            sa.Column(
                "require_approvals",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch.add_column(sa.Column("pending_approval", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("approval_history", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("generation_jobs") as batch:
        batch.drop_column("approval_history")
        batch.drop_column("pending_approval")
        batch.drop_column("require_approvals")
