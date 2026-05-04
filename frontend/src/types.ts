export type ID = number;

/* ---------- shared ---------- */

/** Localized content structure for different languages */
export interface LocalizedContent {
  name?: string;
  description?: string;
  form?: string;
  title?: string;
  [key: string]: string | undefined;
}

/** Localized field with language codes as keys */
export interface LocalizedField {
  zh?: LocalizedContent | string;
  en?: LocalizedContent | string;
  [languageCode: string]: LocalizedContent | string | undefined;
}

/** Base interface for entities with name and localization */
export interface Named {
  name: string;
  key?: string;
  localized?: LocalizedField;
}

/* Frontend-wide MoveCategory. */
export type MoveCategory = "ATTACK" | "DEFENSE" | "STATUS";
export type MoveCategoryWide = MoveCategory | "PHY_ATTACK" | "MAG_ATTACK";

/* Preferred attack style (backend enum). */
export type AttackStyle = "Physical" | "Magical" | "Both" | string;

/* Stats keys UI uses everywhere */
export const STAT_KEYS = ["hp","phy_atk","mag_atk","phy_def","mag_def","spd"] as const;
export type StatKey = typeof STAT_KEYS[number];

/* ---------- core domain objects (localized via Named) ---------- */

export interface TypeOut extends Named {
  id: ID;
  /** Attacking type names that deal 2× to this type. Populated by /types endpoint only. */
  vulnerable_to?: string[];
  /** Attacking type names that deal 0.5× to this type. Populated by /types endpoint only. */
  resistant_to?: string[];
}

export interface TraitOut extends Named {
  id: ID;
  description?: string;
}

export interface PersonalityOut extends Named {
  id: ID;
  hp_mod_pct: number;
  phy_atk_mod_pct: number;
  mag_atk_mod_pct: number;
  phy_def_mod_pct: number;
  mag_def_mod_pct: number;
  spd_mod_pct: number;
}

/**
 * Status — a reusable named effect a move can grant. Mirrors
 * backend.schemas.StatusOut. All boost columns are integer percentages
 * (e.g. 20 = +20%); see frontend/src/lib/statusModel.ts for the combiner
 * and frontend/src/lib/damageCalc.ts for how they feed the damage formula.
 *
 * Three columns (hp_boost, spd_boost, combo_bonus) are present for
 * symmetry with the 6-stat model and future expansion but are NOT
 * consumed by the current damage formula.
 */
export interface StatusOut extends Named {
  id: ID;
  description?: string | null;

  hp_boost: number;
  phy_atk_boost: number;
  mag_atk_boost: number;
  phy_def_boost: number;
  mag_def_boost: number;
  spd_boost: number;

  flat_power_boost: number;
  pct_power_boost: number;

  combo_bonus: number;

  dmg_reduction_pct: number;
  dmg_bonus_pct: number;

  /** When the status applies in battle. Backend serializes StatusUsage.value. */
  usage: "all" | "attack_only" | "defense_only" | "move_specific" | string;
  /** Whether the status affects the move user or the opponent. */
  affect: "self" | "opponent" | string;
}

export interface MoveOut extends Named {
  id: ID;

  /** Backend field name */
  move_type?: TypeOut | null;
  /** Back-compat with older FE code */
  type?: TypeOut | null;

  /** Backend field name */
  move_category?: MoveCategoryWide;
  /** Back-compat alias used in some older components */
  category?: MoveCategoryWide;

  has_counter?: boolean;

  /** Backend extras (optional in FE) */
  energy_cost?: number;
  power?: number | null;
  description?: string;

  /**
   * Statuses this move grants (M:N via the move_statuses join).
   * Backend always serializes this field, defaulting to `[]` when the
   * move has no statuses. Optional here to guard against stale cached
   * responses from before this field was added — always access as
   * `move.statuses ?? []`.
   */
  statuses?: StatusOut[];
}

export interface MonsterSpeciesOut extends Named {
  id: ID;
}

export interface MonsterLiteOut extends Named {
  id: ID;
  form: string;
  main_type: TypeOut;
  sub_type?: TypeOut | null;
  default_legacy_type?: TypeOut | null;
  leader_potential?: boolean;
  is_leader_form?: boolean;
  preferred_attack_style?: AttackStyle;
  // Backend declares these as Optional[int] — null is possible for monsters with missing data
  base_hp: number | null;
  base_phy_atk: number | null;
  base_mag_atk: number | null;
  base_phy_def: number | null;
  base_mag_def: number | null;
  base_spd: number | null;
  evolves_from_id?: number | null;
}

export interface MoveLearnersOut {
  move_pool: MonsterLiteOut[];
  move_stones: MonsterLiteOut[];
  legacy: MonsterLiteOut[];
}

export interface MonsterOut {
  id: number;
  name: string;
  localized?: Record<string, unknown>;

  trait?: TraitOut | null;
  species?: MonsterSpeciesOut;
  evolves_from_id?: number | null;
  form?: string;
  main_type?: TypeOut;
  sub_type?: TypeOut | null;
  default_legacy_type?: TypeOut | null;
  leader_potential?: boolean;
  is_leader_form?: boolean;
  preferred_attack_style?: AttackStyle;

  base_hp: number;
  base_phy_atk: number;
  base_mag_atk: number;
  base_phy_def: number;
  base_mag_def: number;
  base_spd: number;

  move_pool?: Array<number | { id: number } | { move_id: number }>;
  move_stones?: Array<number | { id: number } | { move_id: number }>;
  legacy_moves?: Array<number | { id: number } | { move_id: number }>;
  evolution_tree?: EvolutionTreeData | null;
}

/* ---------- evolution tree models ---------- */

export interface EvolutionStageMonster {
  id: number;
  name: string;
  form: string;
  localized?: Record<string, unknown>;
  is_leader_form: boolean;
  is_representative?: boolean;
  representative_id?: number;
  main_type: TypeOut;
  sub_type?: TypeOut | null;
  children_ids?: number[];
  parent_ids?: number[];
  evolution_level?: number | null;
  evolution_condition?: string | null;
}

export interface EvolutionStage {
  depth: number;
  is_leader_stage?: boolean;
  monsters: EvolutionStageMonster[];
}

export interface EvolutionTreeData {
  stages: EvolutionStage[];
  max_depth: number;
  total_unique_monsters: number;
  species_id: number;
  current_monster_id: number;
}

export interface MagicItemOut extends Named {
  id: ID;
  description?: string;
  applies_to_type?: TypeOut | null;

  // Present on the SQLAlchemy model (used during analysis); optional here.
  effect_code?: string;
  effect_parameters?: any;
}

export interface GameTermOut {
  id: ID;
  key: string;
  description: string;
  localized?: {
    zh?: {
      name?: string;
      description?: string;
      tooltip_description?: string | null;
    };
    [k: string]: unknown;
  };
  sort_order: number;
  tooltip_description?: string | null;
}

/* ---------- builder models ---------- */

export interface TalentUpsert {
  hp_boost: number;
  phy_atk_boost: number;
  mag_atk_boost: number;
  phy_def_boost: number;
  mag_def_boost: number;
  spd_boost: number;
}

export interface UserMonsterCreate {
  monster_id: ID;
  personality_id: ID;
  legacy_type_id: ID;
  move1_id: ID;
  move2_id: ID;
  move3_id: ID;
  move4_id: ID;
  talent: TalentUpsert;
}

export interface TeamCreate {
  name: string;
  magic_item_id: ID;
  user_monsters: UserMonsterCreate[];
}

export interface UserMonsterUpsert {
  id?: ID | null;
  monster_id: ID;
  personality_id: ID;
  legacy_type_id: ID;
  move1_id: ID; move2_id: ID; move3_id: ID; move4_id: ID;
  talent: TalentUpsert;
}

export interface TeamUpdate {
  name?: string | null;
  magic_item_id?: ID | null;
  user_monsters: UserMonsterUpsert[];
}

/* ---------- persisted / expanded models ---------- */

export interface TalentOut extends TalentUpsert {
  id: ID;
}

export interface UserMonsterOut {
  id: ID; // index 0..5 for inline analysis
  monster: MonsterLiteOut;
  personality: PersonalityOut;
  legacy_type: TypeOut;
  move1: MoveOut;
  move2: MoveOut;
  move3: MoveOut;
  move4: MoveOut;
  talent: TalentOut;
  team_id?: ID | null;
}

export interface TeamOut {
  id: ID;
  name?: string | null;
  user_monsters: UserMonsterOut[];
  magic_item: MagicItemOut;
  is_featured?: boolean;
  created_at?: string;
  updated_at?: string;
}

/* ---------- analysis DTOs (mirror backend schemas.py) ---------- */

export interface EffectiveStats {
  hp: number;
  phy_atk: number;
  mag_atk: number;
  phy_def: number;
  mag_def: number;
  spd: number;
}

export interface EnergyProfile {
  avg_energy_cost: number;
  has_zero_cost_move: boolean;
  has_energy_restore_move: boolean;
  zero_cost_moves: ID[];
  energy_restore_moves: ID[];
}

export interface CounterCoverage {
  has_attack_counter_status: boolean;
  has_defense_counter_attack: boolean;
  has_status_counter_defense: boolean;
  total_counter_moves: number;
  counter_move_ids: ID[];
}

export interface DefenseStatusMove {
  defense_status_move_count: number;
  defense_status_move: ID[];
}

export interface TraitSynergyFinding {
  monster_id: ID;
  trait: TraitOut;
  synergy_moves: ID[];
  recommendation: string[];
}

export interface MonsterAnalysisOut {
  user_monster: UserMonsterOut;
  effective_stats: EffectiveStats;
  energy_profile: EnergyProfile;
  counter_coverage: CounterCoverage;
  defense_status_move: DefenseStatusMove;
  trait_synergies: TraitSynergyFinding[];
}

export interface EnhancedCoverageReport {
  super_effective_types: ID[];
  neutral_types: ID[];
  resisted_types: ID[];
}

export interface TypeCoverageReport {
  // NEW primary fields (base coverage from original moves)
  super_effective_types?: ID[];
  neutral_types?: ID[];
  resisted_types?: ID[];
  team_weak_to: ID[];

  // Enhanced coverage (only present if Willpower Enhancement is selected)
  enhanced_coverage?: EnhancedCoverageReport;

  // DEPRECATED (backward compatibility)
  effective_against_types: ID[];
  weak_against_types: ID[];
}

export type Severity = "info" | "warn" | "danger";
export type RecCategory =
  | "coverage"
  | "weakness"
  | "magic_item"
  | "energy"
  | "counters"
  | "defense_status"
  | "trait_synergy"
  | "role_diversity"
  | "stat_highlight"
  | "general";

export interface RecItem {
  category: RecCategory;
  severity: Severity;
  message: string;
  type_ids: ID[];
  monster_ids: ID[]; // user_monster ids
  move_ids: ID[];
}

export interface MagicItemEvaluation {
  chosen_item: MagicItemOut;
  valid_targets: ID[]; // user_monster ids
  best_target_monster_id?: ID | null;
  reasoning?: string | null;
}

// Detail types for structured synergy recommendations
export interface TeamArchetypeDetails {
  tactical_type: string;
  core_loop: string;
  battle_rhythm: string;
}

export interface ActionPriorityDetails {
  role_assignment: string;
  counter_triangle: string;
  energy_economy: string;
}

export interface SwitchingStrategyDetails {
  pivot_points: string;
  active_switch_scenarios: string;
  quick_entry_synergy: string;
}

export interface MagicItemUsageDetails {
  best_targets: string;
  timing: string;
  mismatch_analysis: string;
}

export interface OverallStrategyDetails {
  win_conditions: string;
  vulnerable_points: string;
  adjustments: string;
}

export interface TeamSynergyRecommendation {
  team_archetype: string[] | TeamArchetypeDetails;
  action_priority: string[] | ActionPriorityDetails;
  switching_strategy: string[] | SwitchingStrategyDetails;
  magic_item_usage: string[] | MagicItemUsageDetails;
  overall_strategy: string[] | OverallStrategyDetails;
}

/** Final analysis response (matches backend) */
export interface TeamAnalysisOut {
  team: TeamOut;
  per_monster: MonsterAnalysisOut[];
  type_coverage: TypeCoverageReport;
  magic_item_eval: MagicItemEvaluation;
  recommendations: string[];
  recommendations_structured: RecItem[];
  team_synergy?: TeamSynergyRecommendation | null;
  has_partial_errors?: boolean;
}
/** Saved analysis types */
export interface SavedAnalysisOut {
  id: number;
  team_id: number;
  language: "en" | "zh";
  is_from_cache: boolean;
  created_at: string;
}

export interface FullSavedAnalysisOut extends SavedAnalysisOut {
  analysis_data: TeamAnalysisOut;
}

export interface SaveAnalysisRequest {
  team_id: number;
  language?: "en" | "zh";
  analysis_data: TeamAnalysisOut;
  is_from_cache?: boolean;
}

/* ---------- share / import models ---------- */

export interface SharedMonsterData {
  monster: MonsterLiteOut;
  personality: PersonalityOut;
  legacy_type: TypeOut;
  moves: (MoveOut | null)[];   // null if move deleted from DB
  talent: TalentOut;
  move_valid: boolean[];       // length 4
}

export interface ShareDecodeResponse {
  team_name: string;
  shared_by: string | null;
  note: string | null;
  magic_item: MagicItemOut;
  monsters: SharedMonsterData[];
}
