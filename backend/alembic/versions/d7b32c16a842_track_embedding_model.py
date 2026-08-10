"""track embedding model provenance

Revision ID: d7b32c16a842
Revises: c9a14f02b301
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7b32c16a842"
down_revision: Union[str, Sequence[str], None] = "c9a14f02b301"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("memories", sa.Column("embedding_model", sa.String(100)))
    op.add_column("goals", sa.Column("embedding_model", sa.String(100)))


def downgrade() -> None:
    op.drop_column("goals", "embedding_model")
    op.drop_column("memories", "embedding_model")
