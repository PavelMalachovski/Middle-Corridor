"""port closures: журнал фактических остановок портов

Revision ID: aaf5e0667f9e
Revises: 3f9a1c2b7d61
Create Date: 2026-09-27 18:08:04.702513

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aaf5e0667f9e"
down_revision: str | Sequence[str] | None = "3f9a1c2b7d61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "port_closures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("port_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cause",
            sa.Enum("wind", "other", name="closurecause", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reported_by", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["port_id"], ["ports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_port_closures_port_started", "port_closures", ["port_id", "started_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_port_closures_port_started", table_name="port_closures")
    op.drop_table("port_closures")
