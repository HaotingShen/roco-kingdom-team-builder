"""add preferred_language to users

Revision ID: g1h2i3j4k5l6
Revises: f1g2h3i4j5k6
Create Date: 2026-02-27 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'g1h2i3j4k5l6'
down_revision: Union[str, None] = 'f1g2h3i4j5k6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('preferred_language', sa.String(5), nullable=True))
    op.execute("UPDATE users SET preferred_language = 'en'")
    op.alter_column('users', 'preferred_language', nullable=False)


def downgrade() -> None:
    op.drop_column('users', 'preferred_language')
