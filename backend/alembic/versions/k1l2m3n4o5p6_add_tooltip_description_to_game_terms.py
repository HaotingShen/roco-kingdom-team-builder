"""add tooltip_description to game_terms

Revision ID: k1l2m3n4o5p6
Revises: j1k2l3m4n5o6
Create Date: 2026-03-29 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'k1l2m3n4o5p6'
down_revision: Union[str, None] = 'j1k2l3m4n5o6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('game_terms', sa.Column('tooltip_description', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('game_terms', 'tooltip_description')
