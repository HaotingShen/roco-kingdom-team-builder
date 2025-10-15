export type ID = number;

/* ---------- shared ---------- */

export interface LocalizedName { [key: string]: any } // flexible
export interface Named {
  name: string;
  localized?: LocalizedName;
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

export interface TypeOut extends Named { id: ID; }

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
  is_move_stone?: boolean;

  /** Backend extras (optional in FE) */
  energy_cost?: number;
  power?: number | null;
  description?: string;
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
}

export interface MonsterOut {
  id: number;
  name: string;
  localized?: Record<string, unknown>;

  base_hp: number;
  base_phy_atk: number;
  base_mag_atk: number;
  base_phy_def: number;
  base_mag_def: number;
  base_spd: number;

  move_pool?: Array<number | { id: number } | { move_id: number }>;
  legacy_moves?: Array<number | { id: number } | { move_id: number }>;
}

export interface MagicItemOut extends Named {
  id: ID;
  description?: string;
  applies_to_type?: TypeOut | null;

  // Present on the SQLAlchemy model (used during analysis); optional here.
  effect_code?: string;
  effect_parameters?: any;
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

export interface TypeCoverageReport {
  effective_against_types: ID[];
  weak_against_types: ID[];
  team_weak_to: ID[];
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

/** Final analysis response (matches backend) */
export interface TeamAnalysisOut {
  team: TeamOut;
  per_monster: MonsterAnalysisOut[];
  type_coverage: TypeCoverageReport;
  magic_item_eval: MagicItemEvaluation;
  recommendations: string[];
  recommendations_structured: RecItem[];
}

/* ---------- (optional) legacy shape kept for back-compat ---------- */
/** Older components referenced this; keep it to prevent breakage if any remain. */
export interface LegacyTeamAnalysisOut {
  team_weak_to?: string[];
  valid_targets?: number[];
  recommendations?: string[];
  monsters?: Array<{
    monster_id: ID;
    effective_stats?: Record<string, number>;
    energy_profile?: any;
    counter_coverage?: any;
    trait_synergies?: string[];
  }>;
}