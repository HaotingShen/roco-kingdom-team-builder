from pydantic import BaseModel, ConfigDict, model_validator, Field, field_serializer, field_validator
from typing import Optional, List, Dict, Any, ClassVar, Literal, Union
from backend.models import MoveCategory, AttackStyle
from datetime import datetime


# ========== AUTH SCHEMAS ==========

class UserOut(BaseModel):
    """User profile response."""
    id: int
    username: str
    email: Optional[str] = None
    is_guest: bool
    email_verified: bool
    subscription_tier: str
    created_at: datetime
    last_login_at: Optional[datetime] = None
    is_admin: bool = False
    guest_display_id: Optional[str] = None  # Unique 4-char ID for guest display (e.g., "A2B3")
    preferred_language: str = "en"

    model_config = ConfigDict(from_attributes=True)


class UserRegister(BaseModel):
    """User registration request."""
    username: str = Field(
        ...,
        min_length=2,
        max_length=64,  # Byte limit; grapheme limit (2-16) enforced by validator
        description="Letters, numbers, Chinese characters, underscores, hyphens (2-16 characters)"
    )
    email: str = Field(..., max_length=120)
    password: str = Field(..., min_length=8, max_length=128)
    captcha_token: Optional[str] = Field(None, description="CAPTCHA response token (required if CAPTCHA enabled)")
    preferred_language: str = Field("en", description="Preferred language for transactional emails (en or zh)")

    @field_validator("preferred_language")
    @classmethod
    def validate_preferred_language(cls, v: str) -> str:
        return v if v in ("en", "zh") else "en"

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        """
        Validate username with support for Chinese characters.

        Allowed:
        - Latin letters (A-Z a-z)
        - Digits (0-9)
        - Chinese Han characters (CJK Unified Ideographs)
        - Underscore (_) and hyphen (-)

        Disallowed:
        - Spaces (including full-width)
        - Emoji and symbols
        - Punctuation (except _/-)
        - Control chars / zero-width chars

        Length: 2-16 graphemes (user-perceived characters)
        Security: Blocks confusable/look-alike characters
        """
        from backend.username_validator import validate_username
        is_valid, error = validate_username(v)
        if not is_valid:
            raise ValueError(error)
        return v

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v):
        """
        SECURITY: Enforce strong password requirements.

        Requirements:
        - At least 8 characters (enforced by min_length)
        - At least one uppercase letter
        - At least one lowercase letter
        - At least one digit

        This validator is client-side friendly - provides specific error messages.
        """
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v


class UserLogin(BaseModel):
    """User login request."""
    email: str
    password: str
    captcha_token: Optional[str] = Field(None, description="CAPTCHA response token (required if CAPTCHA enabled)")
    language: Optional[str] = Field("en", description="Language for error messages (en or zh)")


class GuestCreateRequest(BaseModel):
    """
    Guest creation request with device_id for deduplication.

    Frontend generates UUID and stores in localStorage.
    Backend checks if guest with this device_id exists.
    """
    device_id: Optional[str] = None


class AuthResponse(BaseModel):
    """
    Authentication response.

    SECURITY: refresh_token NOT in response body.
    It's set as httpOnly cookie by the server.

    Frontend receives:
    - access_token (store in memory, NOT localStorage)
    - user (store in localStorage via Zustand persist)
    - is_returning_guest (optional, for guest login flow)
    """
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    is_returning_guest: Optional[bool] = None  # True if existing guest, False if new guest, None for non-guest


class TokenResponse(BaseModel):
    """Token refresh response."""
    access_token: str
    token_type: str = "bearer"


# ========== PASSWORD RESET SCHEMAS (Phase 6) ==========

class ForgotPasswordRequest(BaseModel):
    """Request password reset email."""
    email: str = Field(..., max_length=120)
    captcha_token: Optional[str] = Field(None, description="CAPTCHA response token (required if CAPTCHA enabled)")


class PasswordResetRequest(BaseModel):
    """Reset password with token from email."""
    token: str = Field(..., min_length=32)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v):
        """Enforce strong password requirements."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v


class PasswordChangeRequest(BaseModel):
    """Change password (requires current password)."""
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v):
        """Enforce strong password requirements."""
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one number")
        return v


# ========== EMAIL CHANGE SCHEMAS (Phase 6) ==========

class EmailChangeRequest(BaseModel):
    """Request to change email address (requires password verification)."""
    new_email: str = Field(..., max_length=120)
    password: str = Field(..., description="Current password for verification")

    @field_validator("new_email")
    @classmethod
    def validate_email_format(cls, v):
        """Basic email format validation."""
        if "@" not in v or "." not in v:
            raise ValueError("Invalid email format")
        return v.lower()  # Normalize to lowercase


class EmailChangeConfirmRequest(BaseModel):
    """Confirm email change with token from verification email."""
    token: str = Field(..., min_length=32)


# ========== ACCOUNT DELETION SCHEMAS (Phase 6) ==========

class AccountDeleteRequest(BaseModel):
    """
    Request to permanently delete account.

    SECURITY: Requires password confirmation to prevent accidental deletion.
    """
    password: str = Field(..., description="Current password for verification")
    confirm_phrase: str = Field(
        ...,
        description="Must type 'DELETE MY ACCOUNT' to confirm"
    )

    @field_validator("confirm_phrase")
    @classmethod
    def validate_confirm_phrase(cls, v):
        """Ensure user typed the confirmation phrase exactly."""
        if v != "DELETE MY ACCOUNT":
            raise ValueError("Please type 'DELETE MY ACCOUNT' to confirm deletion")
        return v


# ========== EMAIL VERIFICATION SCHEMAS (Phase 7A) ==========

class EmailVerifyRequest(BaseModel):
    """Verify email with token from verification email."""
    token: str = Field(..., min_length=32)


class ResendVerificationRequest(BaseModel):
    """Request to resend verification email."""
    pass  # No body needed, uses current authenticated user's email


class UpdateLanguageRequest(BaseModel):
    """Update user's preferred language for transactional emails."""
    preferred_language: str = Field(..., pattern="^(en|zh)$")


# ========== PAGINATION SCHEMAS ==========

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

    model_config = ConfigDict(from_attributes=True)
    
    @field_serializer("move_category")
    def _ser_move_category(self, v: MoveCategory, _info):
        return v.value

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

    @field_serializer("preferred_attack_style")
    def _ser_attack_style(self, v: AttackStyle, _info):
        return v.value

# Full version of MonsterOut
class MonsterOut(MonsterLiteOut):
    evolves_from_id: Optional[int] = None
    species: MonsterSpeciesOut
    trait: Optional[TraitOut] = None
    base_hp: int
    base_phy_atk: int
    base_mag_atk: int
    base_phy_def: int
    base_mag_def: int
    base_spd: int
    move_pool: List[MoveOut]
    move_stones: List[MoveOut] = []
    legacy_moves: List[LegacyMoveOut]
    evolution_tree: Optional[Dict] = None

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
    owner_id: Optional[int] = None  # Optional for inline analysis (unsaved teams)
    owner: Optional[UserOut] = None  # Owner profile (optional for backward compatibility)
    user_monsters: List[UserMonsterOut]
    magic_item: MagicItemOut
    is_featured: bool = False
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

class EnhancedCoverageReport(BaseModel):
    """Enhanced coverage when using Willpower Enhancement (愿力强化) magic item"""
    super_effective_types: List[int] = Field(default_factory=list)
    neutral_types: List[int] = Field(default_factory=list)
    resisted_types: List[int] = Field(default_factory=list)

class TypeCoverageReport(BaseModel):
    # NEW primary fields (base coverage from original moves)
    super_effective_types: List[int] = Field(default_factory=list)
    neutral_types: List[int] = Field(default_factory=list)
    resisted_types: List[int] = Field(default_factory=list)
    team_weak_to: List[int] = Field(default_factory=list)

    # Enhanced coverage (only present if Willpower Enhancement is selected)
    enhanced_coverage: Optional[EnhancedCoverageReport] = None

    # DEPRECATED (backward compatibility)
    effective_against_types: List[int] = Field(default_factory=list)
    weak_against_types: List[int] = Field(default_factory=list)

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

class TeamArchetypeDetails(BaseModel):
    """Nested details for team archetype section."""
    tactical_type: str = ""
    core_loop: str = ""
    battle_rhythm: str = ""

class ActionPriorityDetails(BaseModel):
    """Nested details for action priority section."""
    role_assignment: str = ""
    counter_triangle: str = ""
    energy_economy: str = ""

class SwitchingStrategyDetails(BaseModel):
    """Nested details for switching strategy section."""
    pivot_points: str = ""
    active_switch_scenarios: str = ""
    quick_entry_synergy: str = ""

class MagicItemUsageDetails(BaseModel):
    """Nested details for magic item usage section."""
    best_targets: str = ""
    timing: str = ""
    mismatch_analysis: str = ""

class OverallStrategyDetails(BaseModel):
    """Nested details for overall strategy section."""
    win_conditions: str = ""
    vulnerable_points: str = ""
    adjustments: str = ""

class TeamSynergyRecommendation(BaseModel):
    """Team-wide synergy analysis and playing recommendations.

    Supports both formats:
    - Legacy: each field is List[str] (for cached analyses)
    - New: each field is nested object with sub-fields
    """
    team_archetype: Union[List[str], TeamArchetypeDetails] = Field(default_factory=list)
    action_priority: Union[List[str], ActionPriorityDetails] = Field(default_factory=list)
    switching_strategy: Union[List[str], SwitchingStrategyDetails] = Field(default_factory=list)
    magic_item_usage: Union[List[str], MagicItemUsageDetails] = Field(default_factory=list)
    overall_strategy: Union[List[str], OverallStrategyDetails] = Field(default_factory=list)

class TeamAnalysisOut(BaseModel):
    team: TeamOut
    per_monster: List[MonsterAnalysisOut]
    type_coverage: TypeCoverageReport
    magic_item_eval: MagicItemEvaluation
    recommendations: List[str] = Field(default_factory=list)
    recommendations_structured: List[RecItem] = Field(default_factory=list)
    team_synergy: Optional[TeamSynergyRecommendation] = None
    has_partial_errors: bool = False

    model_config = ConfigDict(from_attributes=True)

class SavedAnalysisOut(BaseModel):
    id: int
    team_id: int
    language: Literal["en", "zh"]
    is_from_cache: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class FullSavedAnalysisOut(SavedAnalysisOut):
    analysis_data: TeamAnalysisOut
    model_config = ConfigDict(from_attributes=True)

class SaveAnalysisRequest(BaseModel):
    team_id: int
    language: Literal["en", "zh"] = "en"
    analysis_data: TeamAnalysisOut
    is_from_cache: bool = False

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


# ========== ADMIN SCHEMAS (Phase B) ==========

class AdminUserOut(BaseModel):
    """
    Extended user information for admin view.
    Includes all fields that admins need to manage users.
    """
    id: int
    username: str
    email: Optional[str] = None
    is_guest: bool
    is_system: bool
    is_active: bool
    email_verified: bool
    subscription_tier: str
    subscription_expires_at: Optional[datetime] = None
    created_at: datetime
    last_login_at: Optional[datetime] = None
    last_active_at: Optional[datetime] = None
    failed_login_attempts: int
    locked_until: Optional[datetime] = None
    device_id: Optional[str] = None
    guest_display_id: Optional[str] = None  # Unique 4-char ID for guest display
    teams_count: int = 0
    is_admin: bool = False

    model_config = ConfigDict(from_attributes=True)


class AdminUserListOut(BaseModel):
    """Paginated list of users for admin."""
    users: List[AdminUserOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class AdminChangeTierRequest(BaseModel):
    """Request to change a user's subscription tier."""
    tier: str = Field(..., pattern="^(anonymous|guest|free|premium|unlimited)$")


class AdminLockUserRequest(BaseModel):
    """Request to lock a user account."""
    reason: Optional[str] = Field(None, max_length=255)
    duration_hours: Optional[int] = Field(None, ge=1, le=8760)  # Max 1 year


class AdminDeleteUserRequest(BaseModel):
    """Request to delete a user (admin action)."""
    reason: Optional[str] = Field(None, max_length=255)
    add_to_cooldown: bool = Field(
        default=True,
        description="Add email to deletion cooldown (prevent re-registration)"
    )


class AdminStatsOut(BaseModel):
    """System-wide statistics for admin dashboard."""
    total_users: int
    total_guests: int
    total_registered: int
    total_active: int  # Active in last 30 days
    total_locked: int
    total_teams: int
    total_featured_teams: int
    total_analyses: int
    users_by_tier: dict
    registrations_today: int
    registrations_this_week: int
    registrations_this_month: int