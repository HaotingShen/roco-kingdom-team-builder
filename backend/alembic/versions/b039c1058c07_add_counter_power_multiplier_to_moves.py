"""add_counter_power_multiplier_to_moves

Revision ID: b039c1058c07
Revises: 073dad551dec
Create Date: 2026-05-09 23:10:43.775479

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b039c1058c07'
down_revision: Union[str, None] = '073dad551dec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('moves', sa.Column('counter_power_multiplier', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('moves', 'counter_power_multiplier')
