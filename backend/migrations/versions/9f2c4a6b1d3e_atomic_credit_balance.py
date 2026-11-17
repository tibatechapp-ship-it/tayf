"""atomic credit balance + idempotent ledger operations

Revision ID: 9f2c4a6b1d3e
Revises: c3d9e5f81a42
Create Date: 2026-11-17

Phase 1 hardening:

- users: +credit_balance (materialized, backfilled from the ledger) so a charge
  can be one conditional UPDATE instead of a racy read-then-write.
- credit_ledger: +operation_key with a UNIQUE(user_id, operation_key) constraint
  so retried grants/charges/refunds cannot be recorded twice.

The ledger stays append-only; the backfill keeps old balances intact.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9f2c4a6b1d3e"
down_revision: Union[str, Sequence[str], None] = "c3d9e5f81a42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column(
                "credit_balance",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    op.execute(
        """
        UPDATE users
        SET credit_balance = COALESCE((
            SELECT SUM(credit_ledger.delta)
            FROM credit_ledger
            WHERE credit_ledger.user_id = users.id
        ), 0)
        """
    )

    with op.batch_alter_table("credit_ledger") as batch:
        batch.add_column(sa.Column("operation_key", sa.String(length=64), nullable=True))
        batch.create_unique_constraint(
            op.f("uq_credit_ledger_user_id_operation_key"),
            ["user_id", "operation_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("credit_ledger") as batch:
        batch.drop_constraint(
            op.f("uq_credit_ledger_user_id_operation_key"), type_="unique"
        )
        batch.drop_column("operation_key")

    with op.batch_alter_table("users") as batch:
        batch.drop_column("credit_balance")
