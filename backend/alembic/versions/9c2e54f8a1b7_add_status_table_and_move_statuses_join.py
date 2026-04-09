"""add status table and move_statuses join

Revision ID: 9c2e54f8a1b7
Revises: 44defde1d369
Create Date: 2026-04-09 00:00:00.000000

Adds the Status entity and move_statuses M:N join table backing the
upcoming damage matchup feature. Statuses model temporary buffs/debuffs
and damage modifiers attached to moves; the damage formula in
backend/damage.py consumes them via boost_multiplier and multiplicative
damage factors.

This migration only creates the schema. Seed data lives in a separate
forthcoming importer script (backend/scripts/importers/import_statuses.py).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '9c2e54f8a1b7'
down_revision: Union[str, None] = '44defde1d369'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema — create statuses + move_statuses."""
    op.create_table(
        'statuses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('localized', postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'{}'::jsonb")),

        # Stat boosts (percentages, see backend/damage.py:boost_multiplier)
        sa.Column('hp_boost',      sa.Integer(), nullable=False, server_default='0'),
        sa.Column('phy_atk_boost', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('mag_atk_boost', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('phy_def_boost', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('mag_def_boost', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('spd_boost',     sa.Integer(), nullable=False, server_default='0'),

        # Power modifiers
        sa.Column('flat_power_boost', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pct_power_boost',  sa.Integer(), nullable=False, server_default='0'),

        # Combo (inert until move.combo_count column lands)
        sa.Column('combo_bonus', sa.Integer(), nullable=False, server_default='0'),

        # Damage modifiers (multiplicative across statuses)
        sa.Column('dmg_reduction_pct', sa.Float(), nullable=False, server_default='0'),
        sa.Column('dmg_bonus_pct',     sa.Float(), nullable=False, server_default='0'),

        sa.UniqueConstraint('name', name='uq_statuses_name'),
    )
    op.create_index(
        'ix_statuses_localized_gin', 'statuses', ['localized'],
        postgresql_using='gin',
    )

    op.create_table(
        'move_statuses',
        sa.Column('move_id',   sa.Integer(), nullable=False),
        sa.Column('status_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['move_id'],   ['moves.id']),
        sa.ForeignKeyConstraint(['status_id'], ['statuses.id']),
        sa.PrimaryKeyConstraint('move_id', 'status_id'),
    )


def downgrade() -> None:
    """Downgrade schema — drop move_statuses then statuses."""
    op.drop_table('move_statuses')
    op.drop_index('ix_statuses_localized_gin', table_name='statuses')
    op.drop_table('statuses')
