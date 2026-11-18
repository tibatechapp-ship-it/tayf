"""job worker lease: durable queue ownership + recovery

Revision ID: b7e4c1d9a3f2
Revises: 9f2c4a6b1d3e
Create Date: 2026-11-18

Phase 2 hardening:

- generation_jobs: +worker_id, +lease_until, +attempts so an external worker
  can claim a job with a time-limited lease and a restart can reclaim jobs
  orphaned by a dead worker.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e4c1d9a3f2"
down_revision: Union[str, Sequence[str], None] = "9f2c4a6b1d3e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("generation_jobs") as batch:
        batch.add_column(sa.Column("worker_id", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "attempts", sa.Integer(), nullable=False, server_default="0"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("generation_jobs") as batch:
        batch.drop_column("attempts")
        batch.drop_column("lease_until")
        batch.drop_column("worker_id")
