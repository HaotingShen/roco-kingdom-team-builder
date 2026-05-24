"""add dex_number to monsters

Revision ID: n4o5p6q7r8s9
Revises: m3n4o5p6q7r8
Create Date: 2026-05-24 03:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'n4o5p6q7r8s9'
down_revision: Union[str, None] = 'm3n4o5p6q7r8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Wiki canonical dex number (matches monsters_all.json t_id). NULL means
    # the monster has no wiki match; the /monsters endpoint falls back to id
    # ordering via COALESCE(dex_number, id).
    op.add_column(
        'monsters',
        sa.Column('dex_number', sa.Integer(), nullable=True),
    )
    # Index speeds up the dex sort + filter by dex_number.
    op.create_index('ix_monsters_dex_number', 'monsters', ['dex_number'])


def downgrade() -> None:
    op.drop_index('ix_monsters_dex_number', table_name='monsters')
    op.drop_column('monsters', 'dex_number')
