"""add server-owned plan and idempotent Pro grants

Revision ID: a2b3c4d5e6f7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-19

- ``users.plan`` is server-owned and defaults to ``free``.
- ``pro_grants`` records the paid Stripe session that unlocked Pro so webhook
  replay cannot duplicate an entitlement.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("plan", sa.String(length=8), nullable=False, server_default="free")
        )
    op.create_table(
        "pro_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("stripe_session_id", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_pro_grants_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pro_grants")),
        sa.UniqueConstraint(
            "stripe_session_id", name=op.f("uq_pro_grants_stripe_session_id")
        ),
    )
    op.create_index(op.f("ix_pro_grants_user_id"), "pro_grants", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_pro_grants_user_id"), table_name="pro_grants")
    op.drop_table("pro_grants")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("plan")
