"""bridge legacy local database revision

Revision ID: 31cf1d26508c
Revises: a402e1ce0ee5

Some existing development databases were stamped with this revision while
their schema matched a402e1ce0ee5. Keeping the no-op bridge lets those
databases continue forward without clearing user data.
"""

from typing import Sequence, Union


revision: str = "31cf1d26508c"
down_revision: Union[str, Sequence[str], None] = "a402e1ce0ee5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

