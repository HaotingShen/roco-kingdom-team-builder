"""add position column to monster_moves

Revision ID: add_position_mm
Revises: 5f8f2b906a70
Create Date: 2025-12-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_position_mm'
down_revision: Union[str, None] = '5f8f2b906a70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add position column with default value of 0
    op.add_column('monster_moves', sa.Column('position', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove position column
    op.drop_column('monster_moves', 'position')
