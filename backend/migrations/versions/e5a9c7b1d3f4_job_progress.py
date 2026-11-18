"""job progress columns for live SSE

Revision ID: e5a9c7b1d3f4
Revises: d4f7a2b6c8e1
Create Date: 2026-11-18

- generation_jobs.progress mirrors pipeline checkpoints (0-100) so both GET
  polling and the SSE stream can show live progress without new infrastructure.
- generation_jobs.stage names the current pipeline step; terminal transitions
  set both fields in the same conditional UPDATE as the status change.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5a9c7b1d3f4"
down_revision: Union[str, Sequence[str], None] = "d4f7a2b6c8e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "generation_jobs",
        sa.Column("progress", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "generation_jobs",
        sa.Column(
            "stage",
            sa.String(length=32),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("generation_jobs", "stage")
    op.drop_column("generation_jobs", "progress")
