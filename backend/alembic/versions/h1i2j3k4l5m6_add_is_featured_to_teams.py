"""add is_featured to teams

Revision ID: h1i2j3k4l5m6
Revises: g1h2i3j4k5l6
Create Date: 2026-03-02 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'h1i2j3k4l5m6'
down_revision: Union[str, None] = 'g1h2i3j4k5l6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('teams', sa.Column('is_featured', sa.Boolean(), nullable=True))
    op.execute("UPDATE teams SET is_featured = FALSE")
    op.alter_column('teams', 'is_featured', nullable=False)
    op.create_index('ix_teams_is_featured', 'teams', ['is_featured'])


def downgrade() -> None:
    op.drop_index('ix_teams_is_featured', table_name='teams')
    op.drop_column('teams', 'is_featured')
