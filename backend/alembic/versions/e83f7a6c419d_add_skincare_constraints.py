"""add skincare safety constraints

Revision ID: e83f7a6c419d
Revises: b70a2c18f522
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e83f7a6c419d"
down_revision: Union[str, Sequence[str], None] = "b70a2c18f522"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column(
            "skincare_constraints",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )
    op.alter_column("user_profiles", "skincare_constraints", server_default=None)


def downgrade() -> None:
    op.drop_column("user_profiles", "skincare_constraints")
