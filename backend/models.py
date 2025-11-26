import enum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Float, Boolean, ForeignKey, Table, Column, Enum, Index, Text, UniqueConstraint, DateTime, text
from sqlalchemy.dialects.postgresql import JSONB

class Base(DeclarativeBase):
    pass

# Association table for many-to-many Monster-Move relationship
monster_moves = Table(
    "monster_moves", Base.metadata,
    Column("monster_id", Integer, ForeignKey("monsters.id"), primary_key=True),
    Column("move_id", Integer, ForeignKey("moves.id"), primary_key=True)
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
    description: Mapped[str] = mapped_column(Text, nullable=False)
    has_counter: Mapped[bool] = mapped_column(Boolean, default=False)
    is_move_stone: Mapped[bool] = mapped_column(Boolean, default=False)
    localized: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    __table_args__ = (
        Index("ix_moves_localized_gin", "localized", postgresql_using="gin"),
    )
    
    # Relationships
    move_type = relationship("Type", back_populates="moves")
    legacy_for = relationship("LegacyMove", back_populates="move")
    monsters = relationship("Monster", secondary=monster_moves, back_populates="move_pool")

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
    trait_id: Mapped[int] = mapped_column(Integer, ForeignKey("traits.id"), nullable=False)
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
    __table_args__ = (
        Index("ix_monsters_localized_gin", "localized", postgresql_using="gin"),
        UniqueConstraint("name", "form", name="uq_monster_name_form"),
    )
    
    # Relationships
    species = relationship("MonsterSpecies", back_populates="forms")
    evolves_from = relationship("Monster", remote_side=[id]) # self-referential FK for evolution
    trait = relationship("Trait", back_populates="monster")
    move_pool = relationship("Move", secondary=monster_moves, back_populates="monsters")
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
    created_at = Column(DateTime(timezone=True),
                        server_default=text("timezone('utc', now())"),
                        nullable=False)
    updated_at = Column(DateTime(timezone=True),
                        server_default=text("timezone('utc', now())"),
                        onupdate=text("timezone('utc', now())"),
                        nullable=False)

    # Relationships
    user_monsters = relationship("UserMonster", back_populates="team", cascade="all, delete-orphan", order_by="UserMonster.position")
    magic_item = relationship("MagicItem")