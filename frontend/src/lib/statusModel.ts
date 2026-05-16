/**
 * Status model + combiners — TS mirror of backend.damage helpers.
 *
 * Pure functions only. No React, no fetch. Consumed by lib/damageCalc.ts
 * and lib/matchup.ts. The combine semantics (additive for stat/power
 * boosts, multiplicative for damage modifiers) are part of the formula
 * spec — see backend/damage.py and backend/tests/test_damage_calculation.py
 * for the source of truth.
 *
 * Three Status columns are inert today and intentionally NOT touched
 * by the combiner: `hp_boost`, `spd_boost`, `combo_bonus`. They live
 * on `StatusOut` for backend symmetry / future expansion but the
 * damage formula doesn't read them.
 */

import type { StatusOut } from "@/types";

/** Combined effect of a list of active statuses on one side of a matchup. */
export interface StatusDeltas {
  // ----- Additive sums (consumed via boostMultiplier later) -----
  flat_power_total: number;
  pct_power_total: number;
  /** Sum of phy_atk_boost OR mag_atk_boost across active attacker statuses. */
  atk_boost_total: number;
  /** Sum of phy_def_boost OR mag_def_boost across active defender statuses. */
  def_boost_total: number;

  // ----- Pre-folded multiplicative factors -----
  /** ∏ (1 + dmg_bonus_pct/100) — attacker side, multiplicative. */
  attacker_dmg_factor: number;
  /** ∏ (1 - dmg_reduction_pct/100) — defender side, multiplicative. */
  defender_dmg_factor: number;
}

/**
 * Convert a percentage stat/power boost to a multiplier.
 *
 *   +b → (100 + b) / 100         e.g. +20 → ×1.20
 *   -b → 100 / (100 - b)         e.g. -20 → ×(1/1.20) ≈ ×0.833
 *
 * The asymmetry is intentional and matches backend.damage.boost_multiplier:
 * +X and -X are multiplicative inverses, so stacking +20 then -20 returns
 * to ×1.0 exactly.
 */
export function boostMultiplier(boost: number): number {
  if (boost >= 0) return (100 + boost) / 100;
  return 100 / (100 - boost);
}

/**
 * Combine a list of active statuses into a single deltas object.
 *
 * Same-kind stat/power boosts SUM (e.g. +20 + +30 → +50, then ×1.50).
 * Damage modifiers MULTIPLY across statuses ((1.10)(1.20) → ×1.32, NOT ×1.30).
 *
 * `is_magic` selects between phy_*_boost and mag_*_boost columns. Pass
 * the move's category (true for MAG_ATTACK, false for PHY_ATTACK).
 *
 * @param attackerStatuses Active statuses on the attacker side
 * @param defenderStatuses Active statuses on the defender side
 * @param is_magic         Move category — picks phy vs mag boost columns
 */
export function combineStatuses(
  attackerStatuses: readonly StatusOut[],
  defenderStatuses: readonly StatusOut[],
  is_magic: boolean,
): StatusDeltas {
  let flat_power_total = 0;
  let pct_power_total = 0;
  let atk_boost_total = 0;
  let attacker_dmg_factor = 1.0;

  for (const s of attackerStatuses) {
    flat_power_total += s.flat_power_boost;
    pct_power_total += s.pct_power_boost;
    atk_boost_total += is_magic ? s.mag_atk_boost : s.phy_atk_boost;
    if (s.dmg_bonus_pct) {
      attacker_dmg_factor *= 1 + s.dmg_bonus_pct / 100;
    }
  }

  let def_boost_total = 0;
  let defender_dmg_factor = 1.0;

  for (const s of defenderStatuses) {
    def_boost_total += is_magic ? s.mag_def_boost : s.phy_def_boost;
    if (s.dmg_reduction_pct) {
      defender_dmg_factor *= 1 - s.dmg_reduction_pct / 100;
    }
  }

  return {
    flat_power_total,
    pct_power_total,
    atk_boost_total,
    def_boost_total,
    attacker_dmg_factor,
    defender_dmg_factor,
  };
}
