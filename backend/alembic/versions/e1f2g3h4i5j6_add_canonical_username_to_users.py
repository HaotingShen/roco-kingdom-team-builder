"""add canonical_username to users

Revision ID: e1f2g3h4i5j6
Revises: d1e2f3g4h5i6
Create Date: 2026-01-24 16:00:00.000000

This migration adds the canonical_username column for look-alike username protection.
The canonical form normalizes confusable characters (Cyrillic, Greek, full-width)
so that "аdmin" and "admin" are treated as the same username.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2g3h4i5j6'
down_revision: Union[str, None] = 'd1e2f3g4h5i6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Step 1: Add column as nullable first
    op.add_column('users', sa.Column('canonical_username', sa.String(length=64), nullable=True))

    # Step 2: Populate canonical_username for existing users
    # For existing users, we just lowercase the username as a simple canonical form
    # New registrations will use the full normalization from username_validator
    op.execute("""
        UPDATE users
        SET canonical_username = LOWER(username)
        WHERE canonical_username IS NULL
    """)

    # Step 3: Make column NOT NULL after populating
    op.alter_column('users', 'canonical_username', nullable=False)

    # Step 4: Add unique index
    op.create_index(
        op.f('ix_users_canonical_username'),
        'users',
        ['canonical_username'],
        unique=True
    )

    # Also update username column length from 32 to 64 (for Chinese characters)
    op.alter_column('users', 'username',
                    existing_type=sa.String(length=32),
                    type_=sa.String(length=64),
                    existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Revert username column length
    op.alter_column('users', 'username',
                    existing_type=sa.String(length=64),
                    type_=sa.String(length=32),
                    existing_nullable=False)

    op.drop_index(op.f('ix_users_canonical_username'), table_name='users')
    op.drop_column('users', 'canonical_username')
