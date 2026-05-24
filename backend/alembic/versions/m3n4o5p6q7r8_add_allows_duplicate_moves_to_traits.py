"""add allows_duplicate_moves to traits

Revision ID: m3n4o5p6q7r8
Revises: l2m3n4o5p6q7
Create Date: 2026-05-23 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = 'm3n4o5p6q7r8'
down_revision: Union[str, None] = 'l2m3n4o5p6q7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # JSON array of English move names that this trait can carry in multiple slots.
    # NULL means "no exception — UI enforces unique moves per slot" (default behavior).
    op.add_column(
        'traits',
        sa.Column('allows_duplicate_moves', JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('traits', 'allows_duplicate_moves')
