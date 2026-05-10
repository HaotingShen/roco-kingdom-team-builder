"""add_alt_condition_fields_to_moves

Revision ID: 1d8defed5e2a
Revises: b039c1058c07
Create Date: 2026-05-09 23:20:00.683599

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1d8defed5e2a'
down_revision: Union[str, None] = 'b039c1058c07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('moves', sa.Column('alt_power_total', sa.Float(), nullable=True))
    op.add_column('moves', sa.Column('alt_condition_zh', sa.String(80), nullable=True))
    op.add_column('moves', sa.Column('alt_condition_en', sa.String(80), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('moves', 'alt_condition_en')
    op.drop_column('moves', 'alt_condition_zh')
    op.drop_column('moves', 'alt_power_total')
