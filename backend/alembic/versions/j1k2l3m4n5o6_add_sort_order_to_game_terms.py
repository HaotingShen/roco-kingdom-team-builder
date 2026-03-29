"""add sort_order to game_terms

Revision ID: j1k2l3m4n5o6
Revises: i1j2k3l4m5n6
Create Date: 2026-03-29 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'j1k2l3m4n5o6'
down_revision: Union[str, None] = 'i1j2k3l4m5n6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('game_terms', sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('game_terms', 'sort_order')
