"""add users table and owner_id to teams

Revision ID: a1b2c3d4e5f6
Revises: 46979d812582
Create Date: 2026-01-14

This migration:
1. Creates the users table for authentication
2. Creates a system user (ID=1) to own pre-existing teams
3. Adds owner_id column to teams table
4. Migrates existing teams to be owned by system user
5. Makes owner_id NOT NULL
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '46979d812582'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create users table and add owner_id to teams."""
    # Step 1: Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=32), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=True),
        sa.Column('hashed_password', sa.String(length=255), nullable=True),
        sa.Column('is_guest', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('token_version', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('verification_token', sa.String(length=255), nullable=True),
        sa.Column('verification_token_expires', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failed_login_attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('subscription_tier', sa.String(length=32), nullable=False, server_default='free'),
        sa.Column('subscription_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_password_change', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_users_username', 'users', ['username'], unique=True)
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_is_guest', 'users', ['is_guest'], unique=False)
    op.create_index('ix_users_verification_token', 'users', ['verification_token'], unique=False)

    # Step 2: Create system user (ID=1) to own pre-existing teams
    # This user is a special system account, not a real user
    op.execute("""
        INSERT INTO users (id, username, is_guest, is_system, is_active, token_version, email_verified, failed_login_attempts, subscription_tier)
        VALUES (1, 'system', FALSE, TRUE, TRUE, 0, FALSE, 0, 'free')
        ON CONFLICT (id) DO NOTHING
    """)

    # Step 2b: Reset the sequence to avoid primary key conflicts
    # After explicitly inserting ID=1, we must update the sequence
    op.execute("SELECT setval('users_id_seq', COALESCE((SELECT MAX(id) FROM users), 1))")

    # Step 3: Add owner_id column (nullable initially for migration)
    op.add_column('teams', sa.Column('owner_id', sa.Integer(), nullable=True))

    # Step 4: Create foreign key constraint
    op.create_foreign_key(
        'fk_teams_owner_id',
        'teams',
        'users',
        ['owner_id'],
        ['id']
    )

    # Step 5: Create index on owner_id
    op.create_index('ix_teams_owner_id', 'teams', ['owner_id'])

    # Step 6: Assign all existing teams to system user
    op.execute("UPDATE teams SET owner_id = 1 WHERE owner_id IS NULL")

    # Step 7: Make owner_id NOT NULL
    op.alter_column('teams', 'owner_id', nullable=False)


def downgrade() -> None:
    """Remove owner_id from teams and drop users table."""
    # Remove in reverse order
    op.drop_index('ix_teams_owner_id', table_name='teams')
    op.drop_constraint('fk_teams_owner_id', 'teams', type_='foreignkey')
    op.drop_column('teams', 'owner_id')

    # Drop users table
    op.drop_index('ix_users_verification_token', table_name='users')
    op.drop_index('ix_users_is_guest', table_name='users')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_users_username', table_name='users')
    op.drop_table('users')
