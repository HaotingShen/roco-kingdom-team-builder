/**
 * Client-side port of the canonical `compute_effective_stats` from
 * backend/main.py:391-426. Used by EffectiveStatsPanel to render a
 * configured slot's final six stats live (no backend round-trip) as
 * the user edits talents and personality in the inspector.
 *
 * The numbers MUST match the backend exactly so the per-slot panel and
 * the team analyzer never disagree. Test fixtures verifying this live in
 * backend/tests/test_stat_calculation.py — see hand-traces below.
 *
 * Formula (double-rounding, HP final +100):
 *
 *   hp     = round( round( (2·base + 6·talent) · 85/100 + 70 ) · (1 + mod) + 100 )
 *   others = round( round( (2·base + 6·talent) · 55/100 + 10 ) · (1 + mod) + 50  )
 *
 * Two rounding steps: an inner round on the base+talent contribution before
 * the personality multiply, then an outer round on the final value. HP's
 * final additive is +100; every other stat's is +50.
 *
 * The inner core `(2·base + 6·talent) · 0.85` is algebraically equal to
 * `170 · ((base + 3·talent) / 100) = 170·L`, so the TS code below keeps the
 * old `170·L + 70` / `110·L + 10` form to mirror the backend port exactly.
 *
 * Hand-trace against the backend test fixtures (neutral personality):
 *
 *   Flutterfly base_hp=55, talent.hp_boost=10, mod=0
 *     170·(55+30)/100 + 70 = 214.5  → round = 215
 *     215·1 + 100 = 315             → round = 315                    ✓
 *
 *   Starlion   base_hp=67, talent.hp_boost=10, mod=0
 *     170·(67+30)/100 + 70 = 234.9  → round = 235
 *     235·1 + 100 = 335             → round = 335                    ✓
 *
 *   Flutterfly mag_atk: base=55, talent=0, mag_atk_mod_pct=-0.10
 *     110·(55+0)/100 + 10 = 70.5    → round = 71  (inner round kicks in here)
 *     71·0.9 + 50 = 113.9           → round = 114                    ✓
 */

import type {
  EffectiveStats,
  MonsterOut,
  PersonalityOut,
  TalentUpsert,
} from "@/types";

// Python's Decimal ROUND_HALF_UP rounds away from zero. JavaScript's
// Math.round agrees on non-negative values, and stat values are always
// positive (the formula's +50 / +70 / +100 floor terms guarantee this for
// any valid base/talent/personality combination), so Math.round is correct.
const roundHalfUp = (n: number): number => Math.round(n);

// HP path: inner_raw = 170·L + 70 where L = (base + 3·talent)/100
//          final     = round_half_up(round_half_up(inner_raw) · (1 + mod) + 100)
function computeHp(baseHp: number, hpBoost: number, hpModPct: number): number {
  const L = (baseHp + 3 * hpBoost) / 100;
  const inner = roundHalfUp(170 * L + 70);
  return roundHalfUp(inner * (1 + hpModPct) + 100);
}

// Other-stat path: inner_raw = 110·L + 10 where L = (base + 3·talent)/100
//                  final     = round_half_up(round_half_up(inner_raw) · (1 + mod) + 50)
function computeOtherStat(base: number, boost: number, modPct: number): number {
  const L = (base + 3 * boost) / 100;
  const inner = roundHalfUp(110 * L + 10);
  return roundHalfUp(inner * (1 + modPct) + 50);
}

/**
 * Compute the six effective stats for a configured monster slot.
 *
 * Pure: same inputs always produce the same output. Safe to call from a
 * memo or render. Throws nothing — relies on the caller to ensure all three
 * arguments are populated (the caller in EffectiveStatsPanel guards on
 * monster + personality being loaded before calling).
 */
/**
 * Damage-formula constants — from the game's damage rule:
 *   damage = round(DAMAGE_COEFF_NUM * atk * power / (def * DAMAGE_COEFF_DEN))
 */
const DAMAGE_COEFF_NUM = 45;
const DAMAGE_COEFF_DEN = 50;

/**
 * "Effective HP" — the total raw-damage input `RD = atk × power` an attacker
 * must accumulate to KO this defender, given the damage formula above.
 *
 * Derivation: per-hit damage is `(45/50) · RD / def`. Cumulative RD to KO =
 *   HP / (per_hit / RD) = HP · def · (50/45).
 *
 * The result is an approximation — it ignores per-hit integer rounding, type
 * matchups (×0.5 / ×2), STAB, crit rng, magic items, trait effects, and any
 * status the move applies. It's a pure "how tanky in raw stat terms" metric,
 * useful for comparing defensive builds on the same axis. The ordering (who's
 * tankier than whom against phys vs mag) is what this number is good for; the
 * absolute value in isolation is less meaningful.
 */
export function computeEffectiveHp(hp: number, def: number): number {
  if (def <= 0) return 0;
  return Math.round((hp * def * DAMAGE_COEFF_DEN) / DAMAGE_COEFF_NUM);
}

export function computeEffectiveStats(
  monster: MonsterOut,
  talent: TalentUpsert,
  personality: PersonalityOut,
): EffectiveStats {
  return {
    hp: computeHp(monster.base_hp, talent.hp_boost, personality.hp_mod_pct),
    phy_atk: computeOtherStat(
      monster.base_phy_atk,
      talent.phy_atk_boost,
      personality.phy_atk_mod_pct,
    ),
    mag_atk: computeOtherStat(
      monster.base_mag_atk,
      talent.mag_atk_boost,
      personality.mag_atk_mod_pct,
    ),
    phy_def: computeOtherStat(
      monster.base_phy_def,
      talent.phy_def_boost,
      personality.phy_def_mod_pct,
    ),
    mag_def: computeOtherStat(
      monster.base_mag_def,
      talent.mag_def_boost,
      personality.mag_def_mod_pct,
    ),
    spd: computeOtherStat(
      monster.base_spd,
      talent.spd_boost,
      personality.spd_mod_pct,
    ),
  };
}
