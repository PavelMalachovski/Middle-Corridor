"""wind grids: снимки прогноза ветра по сетке над морями

Revision ID: 3f9a1c2b7d61
Revises: a874e74b6345
Create Date: 2026-09-05 15:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3f9a1c2b7d61"
down_revision: str | Sequence[str] | None = "a874e74b6345"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "wind_grids",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("step_deg", sa.Float(), nullable=False),
        sa.Column("hours", json_type, nullable=False),
        sa.Column("points", json_type, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="open-meteo"),
    )
    op.create_index("ix_wind_grids_fetched_at", "wind_grids", ["fetched_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_wind_grids_fetched_at", table_name="wind_grids")
    op.drop_table("wind_grids")
