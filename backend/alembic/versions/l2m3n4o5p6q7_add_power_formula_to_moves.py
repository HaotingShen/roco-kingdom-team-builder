"""Add power_formula to moves

Revision ID: l2m3n4o5p6q7
Revises: 1d8defed5e2a
Create Date: 2026-05-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'l2m3n4o5p6q7'
down_revision: Union[str, None] = '1d8defed5e2a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('moves', sa.Column('power_formula', sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column('moves', 'power_formula')
