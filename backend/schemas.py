from pydantic import BaseModel, ConfigDict, model_validator, Field, field_serializer
from typing import Optional, List, Dict, Any, ClassVar, Literal
from backend.models import MoveCategory, AttackStyle
from datetime import datetime

class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int

class Page(BaseModel):
    meta: PageMeta
    items: List[Any]

class TypeOut(BaseModel):
    id: int
    name: str
    localized: Dict
    
    model_config = ConfigDict(from_attributes=True)

class TraitOut(BaseModel):
    id: int
    name: str
    description: str
    localized: Dict
    
    model_config = ConfigDict(from_attributes=True)

class PersonalityOut(BaseModel):
    id: int
    name: str
    hp_mod_pct: float
    phy_atk_mod_pct: float
    mag_atk_mod_pct: float
    phy_def_mod_pct: float
    mag_def_mod_pct: float
    spd_mod_pct: float
    localized: Dict

    model_config = ConfigDict(from_attributes=True)

# Simplified version of MoveOut
class MoveLiteOut(BaseModel):
    id: int
    name: str
    move_type: Optional[TypeOut] = None
    localized: Dict

    model_config = ConfigDict(from_attributes=True)

# Full version of MoveOut
class MoveOut(MoveLiteOut):
    move_category: MoveCategory
    energy_cost: int
    power: Optional[int] = None
    description: str
    is_move_stone: bool

    model_config = ConfigDict(from_attributes=True)
    
    @field_serializer("move_category")
    def _ser_move_category(self, v: MoveCategory, _info):
        return v.name

class LegacyMoveOut(BaseModel):
    monster_id: int
    type_id: int
    move_id: int

    model_config = ConfigDict(from_attributes=True)

class MonsterSpeciesOut(BaseModel):
    id: int
    name: str
    localized: Dict

    model_config = ConfigDict(from_attributes=True)

# Simplified version of MonsterOut
class MonsterLiteOut(BaseModel):
    id: int
    name: str
    form: str
    main_type: TypeOut
    sub_type: Optional[TypeOut] = None
    default_legacy_type: Optional[TypeOut] = None
    leader_potential: bool
    is_leader_form: bool
    preferred_attack_style: AttackStyle
    localized: Dict

    model_config = ConfigDict(from_attributes=True)

# Full version of MonsterOut
class MonsterOut(MonsterLiteOut):
    evolves_from_id: Optional[int] = None
    species: MonsterSpeciesOut
    trait: TraitOut
    base_hp: int
    base_phy_atk: int
    base_mag_atk: int
    base_phy_def: int
    base_mag_def: int
    base_spd: int
    move_pool: List[MoveOut]
    legacy_moves: List[LegacyMoveOut]

    model_config = ConfigDict(from_attributes=True)

class MagicItemOut(BaseModel):
    id: int
    name: str
    description: str
    localized: Dict

    model_config = ConfigDict(from_attributes=True)

class GameTermOut(BaseModel):
    id: int
    key: str
    description: str
    localized: Dict

    model_config = ConfigDict(from_attributes=True)

class TalentIn(BaseModel):
    hp_boost: int = 0
    phy_atk_boost: int = 0
    mag_atk_boost: int = 0
    phy_def_boost: int = 0
    mag_def_boost: int = 0
    spd_boost: int = 0
    
    allowed_boosts: ClassVar[set] = {0, 7, 8, 9, 10}

    @model_validator(mode="after")
    def check_boosts(self) -> "TalentIn":
        boosts = [
            self.hp_boost,
            self.phy_atk_boost,
            self.mag_atk_boost,
            self.phy_def_boost,
            self.mag_def_boost,
            self.spd_boost,
        ]
        # Check allowed values
        if not all(b in self.allowed_boosts for b in boosts):
            raise ValueError(f"Each boost must be one of {self.allowed_boosts}")
        # Check max number of boosted stats
        boosted_count = sum(1 for b in boosts if b != 0)
        if boosted_count > 3:
            raise ValueError("At most 3 stats can be boosted")
        if boosted_count < 1:
            raise ValueError("At least 1 stat must be boosted")
        return self

class TalentOut(TalentIn):
    id: int

    model_config = ConfigDict(from_attributes=True)

class UserMonsterCreate(BaseModel):
    monster_id: int
    personality_id: int
    legacy_type_id: int
    move1_id: int
    move2_id: int
    move3_id: int
    move4_id: int
    talent: TalentIn
    position: int = 0

class UserMonsterOut(BaseModel):
    id: int
    monster: MonsterLiteOut
    personality: PersonalityOut
    legacy_type: TypeOut
    move1: MoveOut
    move2: MoveOut
    move3: MoveOut
    move4: MoveOut
    talent: TalentOut
    team_id: Optional[int] = None
    position: int = 0

    model_config = ConfigDict(from_attributes=True)

class TeamCreate(BaseModel):
    name: str
    user_monsters: List[UserMonsterCreate] = Field(..., min_length=6, max_length=6)
    magic_item_id: int

    @model_validator(mode="after")
    def validate_name(self) -> "TeamCreate":
        if self.name is not None:
            self.name = self.name.strip()
        if not self.name or not self.name.strip():
            raise ValueError("Team name cannot be empty or whitespace only")
        if len(self.name) > 16:
            raise ValueError("Team name cannot exceed 16 characters")
        return self

class TeamOut(BaseModel):
    id: int
    name: Optional[str] = None
    user_monsters: List[UserMonsterOut]
    magic_item: MagicItemOut
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class TeamAnalyzeByIdRequest(BaseModel):
    team_id: int
    language: Literal["en", "zh"] = "en"

class TeamAnalyzeInlineRequest(BaseModel):
    team: TeamCreate
    language: Literal["en", "zh"] = "en"

class EffectiveStats(BaseModel):
    hp: int
    phy_atk: int
    mag_atk: int
    phy_def: int
    mag_def: int
    spd: int
    
class EnergyProfile(BaseModel):
    avg_energy_cost: float
    has_zero_cost_move: bool
    has_energy_restore_move: bool
    zero_cost_moves: List[int] = Field(default_factory=list)
    energy_restore_moves: List[int] = Field(default_factory=list)
    
class CounterCoverage(BaseModel):
    has_attack_counter_status: bool
    has_defense_counter_attack: bool
    has_status_counter_defense: bool
    total_counter_moves: int
    counter_move_ids: List[int] = Field(default_factory=list)
    
class DefenseStatusMove(BaseModel):
    defense_status_move_count: int
    defense_status_move: List[int] = Field(default_factory=list)

class TraitSynergyFinding(BaseModel):
    monster_id: int
    trait: TraitOut
    synergy_moves: List[int] = Field(default_factory=list)
    recommendation: List[str] = Field(default_factory=list)

class TypeCoverageReport(BaseModel):
    effective_against_types: List[int] = Field(default_factory=list)
    weak_against_types: List[int] = Field(default_factory=list)
    team_weak_to: List[int] = Field(default_factory=list)

class RecItem(BaseModel):
    category: Literal["coverage", "weakness", "magic_item", "energy", "counters", "defense_status", "trait_synergy", "role_diversity", "stat_highlight", "general"] = "general"
    severity: Literal["info", "warn", "danger"] = "info"
    message: str
    type_ids: List[int] = Field(default_factory=list)
    monster_ids: List[int] = Field(default_factory=list)
    move_ids: List[int] = Field(default_factory=list)

class MagicItemEvaluation(BaseModel):
    chosen_item: MagicItemOut
    valid_targets: List[int]  # user_monster ids
    best_target_monster_id: Optional[int] = None
    reasoning: Optional[str] = None

class MonsterAnalysisOut(BaseModel):
    user_monster: UserMonsterOut
    effective_stats: EffectiveStats
    energy_profile: EnergyProfile
    counter_coverage: CounterCoverage
    defense_status_move: DefenseStatusMove
    trait_synergies: List[TraitSynergyFinding] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)

class TeamSynergyRecommendation(BaseModel):
    """Team-wide synergy analysis and playing recommendations."""
    key_combos: List[str] = Field(default_factory=list)
    turn_order_strategy: List[str] = Field(default_factory=list)
    magic_item_usage: List[str] = Field(default_factory=list)
    general_strategy: List[str] = Field(default_factory=list)

class TeamAnalysisOut(BaseModel):
    team: TeamOut
    per_monster: List[MonsterAnalysisOut]
    type_coverage: TypeCoverageReport
    magic_item_eval: MagicItemEvaluation
    recommendations: List[str] = Field(default_factory=list)
    recommendations_structured: List[RecItem] = Field(default_factory=list)
    team_synergy: Optional[TeamSynergyRecommendation] = None

    model_config = ConfigDict(from_attributes=True)
    
class TalentUpsert(BaseModel):
    hp_boost: int = 0
    phy_atk_boost: int = 0
    mag_atk_boost: int = 0
    phy_def_boost: int = 0
    mag_def_boost: int = 0
    spd_boost: int = 0

class UserMonsterUpsert(BaseModel):
    id: Optional[int] = None  # If present, means update; if missing, means create new
    monster_id: int
    personality_id: int
    legacy_type_id: int
    move1_id: int
    move2_id: int
    move3_id: int
    move4_id: int
    talent: TalentUpsert
    position: int = 0

class TeamUpdate(BaseModel):
    name: Optional[str] = None
    magic_item_id: Optional[int] = None
    user_monsters: List[UserMonsterUpsert]

    @model_validator(mode="after")
    def validate_name(self) -> "TeamUpdate":
        if self.name is not None:
            self.name = self.name.strip()
            if not self.name:
                raise ValueError("Team name cannot be empty or whitespace only")
            if len(self.name) > 16:
                raise ValueError("Team name cannot exceed 16 characters")
        return self