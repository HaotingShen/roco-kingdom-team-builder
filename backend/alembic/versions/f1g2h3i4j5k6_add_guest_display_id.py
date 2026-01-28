"""add guest_display_id to users

Revision ID: f1g2h3i4j5k6
Revises: e1f2g3h4i5j6
Create Date: 2026-01-25 10:00:00.000000

Adds a unique 4-character alphanumeric display ID for guest accounts.
This ensures "Guest#XXXX" display names are guaranteed unique.
"""
from typing import Sequence, Union
import secrets
import string

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision: str = 'f1g2h3i4j5k6'
down_revision: Union[str, None] = 'e1f2g3h4i5j6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Characters for display ID (excluding confusables: 0/O, 1/I/L)
DISPLAY_ID_CHARS = '23456789ABCDEFGHJKMNPQRSTUVWXYZ'


def generate_display_id() -> str:
    """Generate a random 4-character display ID."""
    return ''.join(secrets.choice(DISPLAY_ID_CHARS) for _ in range(4))


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Add column as nullable
    op.add_column('users', sa.Column('guest_display_id', sa.String(length=8), nullable=True))

    # Step 2: Generate unique display IDs for existing guests
    bind = op.get_bind()
    session = Session(bind=bind)

    # Get all guest users
    result = session.execute(
        sa.text("SELECT id FROM users WHERE is_guest = true AND guest_display_id IS NULL")
    )
    guest_ids = [row[0] for row in result]

    # Track used IDs to avoid collisions during migration
    used_ids = set()

    for guest_id in guest_ids:
        # Generate unique ID
        while True:
            display_id = generate_display_id()
            if display_id not in used_ids:
                used_ids.add(display_id)
                break

        session.execute(
            sa.text("UPDATE users SET guest_display_id = :display_id WHERE id = :id"),
            {"display_id": display_id, "id": guest_id}
        )

    session.commit()

    # Step 3: Add unique index (only for non-null values)
    op.create_index(
        op.f('ix_users_guest_display_id'),
        'users',
        ['guest_display_id'],
        unique=True,
        postgresql_where=sa.text('guest_display_id IS NOT NULL')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_users_guest_display_id'), table_name='users')
    op.drop_column('users', 'guest_display_id')
