"""add generation_jobs.proof_events

Revision ID: f6a8c3e2b4d7
Revises: e5a9c7b1d3f4
Create Date: 2026-11-18

- ``proof_events`` stores the append-only, hash-chained per-stage verification
  trail defined in ``app/core/job_proof.py``. It is nullable so existing rows
  migrate cleanly; the model default supplies ``[]`` for new jobs.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a8c3e2b4d7"
down_revision: Union[str, Sequence[str], None] = "e5a9c7b1d3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("generation_jobs") as batch:
        batch.add_column(sa.Column("proof_events", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("generation_jobs") as batch:
        batch.drop_column("proof_events")
