"""add_device_id_and_last_active_to_users

Revision ID: c1d2e3f4g5h6
Revises: 566038d8de60
Create Date: 2026-01-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4g5h6'
down_revision: Union[str, None] = '566038d8de60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add device_id column for guest account linking
    op.add_column('users', sa.Column('device_id', sa.String(64), nullable=True))
    op.create_index('ix_users_device_id', 'users', ['device_id'])

    # Add last_active_at column for guest expiry tracking
    op.add_column('users', sa.Column('last_active_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_index('ix_users_device_id', table_name='users')
    op.drop_column('users', 'device_id')
    op.drop_column('users', 'last_active_at')
