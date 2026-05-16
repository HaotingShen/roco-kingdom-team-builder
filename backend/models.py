import enum
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Float, Boolean, ForeignKey, Table, Column, Enum, Index, Text, UniqueConstraint, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB

class Base(DeclarativeBase):
    pass


# ========== USER MODEL (Authentication) ==========

class User(Base):
    """
    User model for authentication.

    Supports:
    - Guest accounts (auto-created, device_id deduplication)
    - Registered accounts (email/password)
    - Token revocation (via token_version)
    - Email verification (Phase 7A)
    - Account lockout protection
    - Future subscription tiers
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Canonical username for uniqueness check (blocks confusable look-alikes)
    # e.g., "аdmin" (Cyrillic) normalizes to "admin" - blocked if "admin" exists
    canonical_username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(120), unique=True, nullable=True, index=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Account type flags
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # 🔒 SECURITY: Token revocation support
    # Increment this to invalidate all user's tokens (password change, security breach)
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 🔒 SECURITY: Email verification (Phase 7A - MANDATORY)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    verification_token_expires: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # 🔒 SECURITY: Password reset (Phase 6)
    password_reset_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    password_reset_expires: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # 🔒 SECURITY: Email change (Phase 6)
    pending_email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    email_change_token: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    email_change_token_expires: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # 🔒 SECURITY: Account lockout
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Future payment fields (prepared but unused)
    subscription_tier: Mapped[str] = mapped_column(String(32), default="free", nullable=False)
    subscription_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Device tracking (for guest account linking)
    device_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    registration_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    last_login_ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    converted_from_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Guest display ID - unique 4-char alphanumeric for display (e.g., "Guest#A1B2")
    # Only set for guest accounts, nullable for registered users
    guest_display_id: Mapped[Optional[str]] = mapped_column(String(8), unique=True, nullable=True, index=True)

    # Language preference for transactional emails (verification, password reset, email change)
    preferred_language: Mapped[str] = mapped_column(String(5), default="en", nullable=False)

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("timezone('utc', now())"),
        nullable=False
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_password_change: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    teams = relationship("Team", back_populates="owner", cascade="all, delete-orphan")

# Association table for many-to-many Monster-Move relationship (including learnable moves and move stones)
monster_moves = Table(
    "monster_moves", Base.metadata,
    Column("monster_id", Integer, ForeignKey("monsters.id"), primary_key=True),
    Column("move_id", Integer, ForeignKey("moves.id"), primary_key=True),
    Column("is_move_stone", Boolean, nullable=False, default=False),
    Column("position", Integer, nullable=False, default=0)  # Preserves JSON order
)

# Many-to-many: a Move grants/applies one or more Statuses (used by the
# damage matchup feature). Statuses are reusable entities — two different
# moves can grant the same named status row.
move_statuses = Table(
    "move_statuses", Base.metadata,
    Column("move_id",   Integer, ForeignKey("moves.id"),    primary_key=True),
    Column("status_id", Integer, ForeignKey("statuses.id"), primary_key=True),
)

# Association tables for type effectiveness
type_effective_against = Table(
    "type_effective_against", Base.metadata,
    Column("type_id", Integer, ForeignKey("types.id"), primary_key=True),
    Column("target_type_id", Integer, ForeignKey("types.id"), primary_key=True)
)

type_weak_against = Table(
    "type_weak_against", Base.metadata,
    Column("type_id", Integer, ForeignKey("types.id"), primary_key=True),
    Column("target_type_id", Integer, ForeignKey("types.id"), primary_key=True)
)
    
class MoveCategory(enum.Enum):
    PHY_ATTACK = "Physical Attack"
    MAG_ATTACK = "Magic Attack"
    DEFENSE = "Defense"
    STATUS = "Status"
    
class AttackStyle(enum.Enum):
    PHYSICAL = "Physical"
    MAGIC = "Magic"
    BOTH = "Both"
    
class MagicEffectCode(enum.Enum):
    ENHANCE_SPELL = "enhance_spell"
    SUN_HEALING = "sun_healing"
    FLARE_BURST = "flare_burst"
    FLOW_SPELL = "flow_spell"
    EVOLUTION_POWER = "evolution_power"

class StatusUsage(enum.Enum):
    ALL = "all"
    ATTACK_ONLY = "attack_only"
    DEFENSE_ONLY = "defense_only"
    MOVE_SPECIFIC = "move_specific"

class StatusAffect(enum.Enum):
    SELF = "self"
    OPPONENT = "opponent"

class Type(Base):
    __tablename__ = "types"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    localized: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (
        Index("ix_types_localized_gin", "localized", postgresql_using="gin"),
    )
    
    # Relationships
    moves = relationship("Move", back_populates="move_type")
    legacy_moves = relationship("LegacyMove", back_populates="type")
    user_monsters_as_legacy = relationship("UserMonster", back_populates="legacy_type")
    # Use "foreign_keys" to handle circular references to models defined later in the file
    monsters_as_main_type = relationship("Monster", foreign_keys="Monster.main_type_id", back_populates="main_type")
    monsters_as_sub_type = relationship("Monster", foreign_keys="Monster.sub_type_id", back_populates="sub_type")
    monsters_as_legacy_type = relationship("Monster", foreign_keys="Monster.default_legacy_type_id", back_populates="default_legacy_type")
    magic_items = relationship("MagicItem", back_populates="applies_to_type")
    # Self-referential many-to-many relationship
    effective_against = relationship(
        "Type",
        secondary=type_effective_against,
        primaryjoin=id==type_effective_against.c.type_id,
        secondaryjoin=id==type_effective_against.c.target_type_id,
        backref="vulnerable_to"
    )
    weak_against = relationship(
        "Type",
        secondary=type_weak_against,
        primaryjoin=id==type_weak_against.c.type_id,
        secondaryjoin=id==type_weak_against.c.target_type_id,
        backref="resistant_to"
    )

class GameTerm(Base):
    __tablename__ = "game_terms"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    localized: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tooltip_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    __table_args__ = (
        Index("ix_game_terms_localized_gin", "localized", postgresql_using="gin"),
    )
    
class Trait(Base):
    __tablename__ = "traits"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    localized: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (
        Index("ix_traits_localized_gin", "localized", postgresql_using="gin"),
    )
    
    # Relationships
    monster = relationship("Monster", back_populates="trait") # one-to-many with Monster
    
class Personality(Base):
    __tablename__ = "personalities"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    hp_mod_pct: Mapped[float] = mapped_column(Float, default=0.0)
    phy_atk_mod_pct: Mapped[float] = mapped_column(Float, default=0.0)
    mag_atk_mod_pct: Mapped[float] = mapped_column(Float, default=0.0)
    phy_def_mod_pct: Mapped[float] = mapped_column(Float, default=0.0)
    mag_def_mod_pct: Mapped[float] = mapped_column(Float, default=0.0)
    spd_mod_pct: Mapped[float] = mapped_column(Float, default=0.0)
    localized: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (
        Index("ix_personalities_localized_gin", "localized", postgresql_using="gin"),
    )
    
    # Relationships
    user_monsters = relationship("UserMonster", back_populates="personality")
    
class Talent(Base):
    __tablename__ = "talents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monster_instance_id: Mapped[int] = mapped_column(Integer, ForeignKey("user_monsters.id", ondelete="CASCADE"))
    hp_boost: Mapped[int] = mapped_column(Integer, default=0)
    phy_atk_boost: Mapped[int] = mapped_column(Integer, default=0)
    mag_atk_boost: Mapped[int] = mapped_column(Integer, default=0)
    phy_def_boost: Mapped[int] = mapped_column(Integer, default=0)
    mag_def_boost: Mapped[int] = mapped_column(Integer, default=0)
    spd_boost: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    user_monster = relationship("UserMonster", back_populates="talent", uselist=False)
    
class MagicItem(Base):
    __tablename__ = "magic_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    effect_code: Mapped[MagicEffectCode] = mapped_column(Enum(MagicEffectCode, name="magic_effect_code_enum"), nullable=False)
    applies_to_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("types.id"), nullable=True)
    effect_parameters: Mapped[dict] = mapped_column(JSONB, nullable=True)
    localized: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (
        Index("ix_magic_items_localized_gin", "localized", postgresql_using="gin"),
    )

    # Relationships
    applies_to_type = relationship("Type", back_populates="magic_items")
    
class Move(Base):
    __tablename__ = "moves"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    move_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("types.id"), nullable=True)
    move_category: Mapped[MoveCategory] = mapped_column(Enum(MoveCategory, name="move_category_enum"), nullable=False)
    energy_cost: Mapped[int] = mapped_column(Integer, nullable=False)
    power: Mapped[int] = mapped_column(Integer, nullable=True)
    base_combo: Mapped[int] = mapped_column(Integer, nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    has_counter: Mapped[bool] = mapped_column(Boolean, default=False)
    counter_power_multiplier: Mapped[float] = mapped_column(Float, nullable=True)
    alt_power_total: Mapped[float] = mapped_column(Float, nullable=True)
    alt_condition_zh: Mapped[str] = mapped_column(String(80), nullable=True)
    alt_condition_en: Mapped[str] = mapped_column(String(80), nullable=True)
    power_formula: Mapped[str] = mapped_column(String(20), nullable=True)
    localized: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (
        Index("ix_moves_localized_gin", "localized", postgresql_using="gin"),
    )

    # Relationships
    move_type = relationship("Type", back_populates="moves")
    legacy_for = relationship("LegacyMove", back_populates="move")
    statuses = relationship(
        "Status",
        secondary=move_statuses,
        back_populates="moves",
        lazy="selectin",
    )


class Status(Base):
    """
    A reusable named effect a move can grant — buffs, debuffs, defensive
    states, etc. Linked to Move via the move_statuses join table.

    All boost columns are integers representing PERCENTAGES (e.g. 20 = +20%).
    The damage formula converts these to multipliers via boost_multiplier(b),
    which is symmetric: +20 → ×1.20, -20 → ×(1/1.20) ≈ ×0.833.

    Three columns (hp_boost, spd_boost, combo_bonus) are kept for symmetry
    with the 6-stat model and future expansion but are NOT consumed by the
    current damage formula. See backend/damage.py for the live formula.
    """
    __tablename__ = "statuses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    localized: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # ----- Stat boosts (additive across statuses, then via boost_multiplier) -----
    # hp_boost is inert in the current damage formula (kept for 6-stat symmetry).
    hp_boost:      Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    phy_atk_boost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mag_atk_boost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    phy_def_boost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mag_def_boost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # spd_boost is inert in the current damage formula (turn order isn't modelled yet).
    spd_boost:     Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ----- Power modifiers (apply to attack moves) -----
    flat_power_boost: Mapped[int]   = mapped_column(Integer, nullable=False, default=0)
    pct_power_boost:  Mapped[int]   = mapped_column(Integer, nullable=False, default=0)

    # ----- Combo (inert until move.combo_count column lands; see roadmap) -----
    combo_bonus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ----- Move-specific conditional power bonus (usage=MOVE_SPECIFIC only) -----
    # Added to move.power when the condition encoded in the status name is met.
    # Always shown as an extra damage row in the matchup panel (no toggle).
    power_bonus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ----- Damage modifiers (multiplicative across statuses) -----
    dmg_reduction_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dmg_bonus_pct:     Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # ----- Categorical metadata -----
    usage:  Mapped[StatusUsage]  = mapped_column(Enum(StatusUsage, name="status_usage_enum"), nullable=False, default=StatusUsage.ALL)
    affect: Mapped[StatusAffect] = mapped_column(Enum(StatusAffect, name="status_affect_enum"), nullable=False, default=StatusAffect.SELF)

    __table_args__ = (
        Index("ix_statuses_localized_gin", "localized", postgresql_using="gin"),
    )

    # Relationships
    moves = relationship(
        "Move",
        secondary=move_statuses,
        back_populates="statuses",
    )

class LegacyMove(Base):
    __tablename__ = "legacy_moves"
    monster_id: Mapped[int] = mapped_column(Integer, ForeignKey("monsters.id"), primary_key=True)
    type_id: Mapped[int] = mapped_column(Integer, ForeignKey("types.id"), primary_key=True)
    move_id: Mapped[int] = mapped_column(Integer, ForeignKey("moves.id"), nullable=False)
    
    # Relationships
    monster = relationship("Monster", back_populates="legacy_moves")
    type = relationship("Type", back_populates="legacy_moves")
    move = relationship("Move", back_populates="legacy_for")
    
class MonsterSpecies(Base):
    __tablename__ = "monster_species"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    localized: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (
        Index("ix_monster_species_localized_gin", "localized", postgresql_using="gin"),
    )
    
    # Relationships
    forms = relationship("Monster", back_populates="species")

class Monster(Base):
    __tablename__ = "monsters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    evolves_from_id: Mapped[int] = mapped_column(Integer, ForeignKey("monsters.id"), nullable=True)
    species_id: Mapped[int] = mapped_column(Integer, ForeignKey("monster_species.id"), nullable=False)
    form: Mapped[str] = mapped_column(String(32), nullable=False, default="default")
    
    main_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("types.id"), nullable=False)
    sub_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("types.id"), nullable=True)
    default_legacy_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("types.id"), nullable=False)
    trait_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("traits.id"), nullable=True)
    leader_potential: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # True if monster is in final evolution stage and can be a leader
    is_leader_form: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    base_hp: Mapped[int] = mapped_column(Integer, nullable=False)
    base_phy_atk: Mapped[int] = mapped_column(Integer, nullable=False)
    base_mag_atk: Mapped[int] = mapped_column(Integer, nullable=False)
    base_phy_def: Mapped[int] = mapped_column(Integer, nullable=False)
    base_mag_def: Mapped[int] = mapped_column(Integer, nullable=False)
    base_spd: Mapped[int] = mapped_column(Integer, nullable=False)
    preferred_attack_style: Mapped[AttackStyle] = mapped_column(Enum(AttackStyle, name="preferred_attack_style_enum"), default=AttackStyle.BOTH, nullable=False)
    localized: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    evolution_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evolution_condition: Mapped[str | None] = mapped_column(String(255), nullable=True)
    __table_args__ = (
        Index("ix_monsters_localized_gin", "localized", postgresql_using="gin"),
        UniqueConstraint("name", "form", name="uq_monster_name_form"),
    )
    
    # Relationships
    species = relationship("MonsterSpecies", back_populates="forms")
    evolves_from = relationship("Monster", remote_side=[id]) # self-referential FK for evolution
    trait = relationship("Trait", back_populates="monster")
    move_pool = relationship(
        "Move",
        secondary=monster_moves,
        primaryjoin="and_(Monster.id==monster_moves.c.monster_id, monster_moves.c.is_move_stone==False)",
        secondaryjoin="Move.id==monster_moves.c.move_id",
        order_by=monster_moves.c.position,
        viewonly=True
    )
    move_stones = relationship(
        "Move",
        secondary=monster_moves,
        primaryjoin="and_(Monster.id==monster_moves.c.monster_id, monster_moves.c.is_move_stone==True)",
        secondaryjoin="Move.id==monster_moves.c.move_id",
        order_by=monster_moves.c.position,
        viewonly=True
    )
    legacy_moves = relationship("LegacyMove", back_populates="monster")
    user_monsters = relationship("UserMonster", back_populates="monster")
    main_type = relationship("Type", foreign_keys=[main_type_id], back_populates="monsters_as_main_type")
    sub_type = relationship("Type", foreign_keys=[sub_type_id], back_populates="monsters_as_sub_type")
    default_legacy_type = relationship("Type", foreign_keys=[default_legacy_type_id], back_populates="monsters_as_legacy_type")
   
# Represents a user's input monster (with personality, custom legacy type, talents) 
class UserMonster(Base):
    __tablename__ = "user_monsters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monster_id: Mapped[int] = mapped_column(Integer, ForeignKey("monsters.id"), nullable=False)
    personality_id: Mapped[int] = mapped_column(Integer, ForeignKey("personalities.id"), nullable=False)
    legacy_type_id: Mapped[int] = mapped_column(Integer, ForeignKey("types.id"), nullable=False)
    move1_id: Mapped[int] = mapped_column(Integer, ForeignKey("moves.id"))
    move2_id: Mapped[int] = mapped_column(Integer, ForeignKey("moves.id"))
    move3_id: Mapped[int] = mapped_column(Integer, ForeignKey("moves.id"))
    move4_id: Mapped[int] = mapped_column(Integer, ForeignKey("moves.id"))
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Relationships
    monster = relationship("Monster", back_populates="user_monsters")
    personality = relationship("Personality", back_populates="user_monsters")
    legacy_type = relationship("Type", back_populates="user_monsters_as_legacy")
    talent = relationship("Talent", back_populates="user_monster", cascade="all, delete-orphan", uselist=False)
    move1 = relationship("Move", foreign_keys=[move1_id])
    move2 = relationship("Move", foreign_keys=[move2_id])
    move3 = relationship("Move", foreign_keys=[move3_id])
    move4 = relationship("Move", foreign_keys=[move4_id])
    team = relationship("Team", back_populates="user_monsters")
    
class Team(Base):
    __tablename__ = "teams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), nullable=True)
    magic_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("magic_items.id"), nullable=True)

    # ✅ Owner foreign key (added for authentication)
    owner_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    created_at = Column(DateTime(timezone=True),
                        server_default=text("timezone('utc', now())"),
                        nullable=False)
    updated_at = Column(DateTime(timezone=True),
                        server_default=text("timezone('utc', now())"),
                        onupdate=text("timezone('utc', now())"),
                        nullable=False)

    # Relationships
    owner = relationship("User", back_populates="teams")
    user_monsters = relationship("UserMonster", back_populates="team", cascade="all, delete-orphan", order_by="UserMonster.position")
    magic_item = relationship("MagicItem")
    analyses = relationship("TeamAnalysis", back_populates="team", cascade="all, delete-orphan")

class TeamAnalysis(Base):
    __tablename__ = "team_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    language: Mapped[str] = mapped_column(String(2), nullable=False)
    analysis_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_from_cache: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=text("timezone('utc', now())"), nullable=False)

    __table_args__ = (
        UniqueConstraint("team_id", "language", name="uq_team_analysis_team_language"),
        Index("ix_team_analyses_team_id", "team_id"),
        Index("ix_team_analyses_created_at", "created_at"),
    )

    team = relationship("Team", back_populates="analyses")


# ========== DELETED EMAIL TRACKING (Anti-Abuse) ==========

class DeletedEmail(Base):
    """
    Tracks deleted emails to prevent immediate re-registration.

    Anti-abuse measure: Users cannot re-register with the same email
    for COOLDOWN_DAYS after account deletion. This prevents:
    - Resetting analysis quotas by delete/re-register
    - Evading bans/locks
    - Abuse of new-user promotions

    Records are automatically cleaned up after cooldown period expires.
    """
    __tablename__ = "deleted_emails"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("timezone('utc', now())"),
        nullable=False
    )
    cooldown_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    original_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Reason values: 'user_requested', 'admin_deleted', 'abuse'

    __table_args__ = (
        Index("ix_deleted_emails_cooldown_until", "cooldown_until"),
    )