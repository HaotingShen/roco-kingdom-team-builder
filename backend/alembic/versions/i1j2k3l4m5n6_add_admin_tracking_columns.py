"""add admin tracking columns to users

Revision ID: i1j2k3l4m5n6
Revises: h1i2j3k4l5m6
Create Date: 2026-03-07 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'i1j2k3l4m5n6'
down_revision: Union[str, None] = 'h1i2j3k4l5m6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('lock_reason', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('registration_ip', sa.String(45), nullable=True))
    op.add_column('users', sa.Column('last_login_ip', sa.String(45), nullable=True))
    op.add_column('users', sa.Column('converted_from_guest', sa.Boolean(), nullable=True))
    op.execute("UPDATE users SET converted_from_guest = FALSE")
    op.alter_column('users', 'converted_from_guest', nullable=False)


def downgrade() -> None:
    op.drop_column('users', 'lock_reason')
    op.drop_column('users', 'registration_ip')
    op.drop_column('users', 'last_login_ip')
    op.drop_column('users', 'converted_from_guest')
