"""add_deleted_emails_table

Revision ID: d1e2f3g4h5i6
Revises: c1d2e3f4g5h6
Create Date: 2026-01-19

Anti-abuse measure: Tracks deleted emails to prevent immediate re-registration.
Users cannot re-register with the same email for 30 days after account deletion.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3g4h5i6'
down_revision: Union[str, None] = 'c1d2e3f4g5h6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'deleted_emails',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=120), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True),
                  server_default=sa.text("timezone('utc', now())"), nullable=False),
        sa.Column('cooldown_until', sa.DateTime(timezone=True), nullable=False),
        sa.Column('original_user_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_deleted_emails_email', 'deleted_emails', ['email'])
    op.create_index('ix_deleted_emails_cooldown_until', 'deleted_emails', ['cooldown_until'])


def downgrade() -> None:
    op.drop_index('ix_deleted_emails_cooldown_until', table_name='deleted_emails')
    op.drop_index('ix_deleted_emails_email', table_name='deleted_emails')
    op.drop_table('deleted_emails')
