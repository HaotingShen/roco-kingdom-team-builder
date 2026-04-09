/**
 * TS mirror of backend/damage.py:compute_move_damage.
 *
 * The numbers MUST match the backend exactly so the per-slot live
 * matchup view and any future server-side computation never disagree.
 * Test fixtures are the shared source of truth in
 * backend/tests/test_damage_calculation.py — see scripts/verifyDamageCalc.mjs
 * for the Node hand-verification of this port against those fixtures.
 *
 * Pure functions only. No React, no fetch. The caller (matchup
 * orchestrator in lib/matchup.ts) is responsible for resolving stats
 * via lib/effectiveStats.ts, picking the right atk/def stat for the
 * move category, looking up the type vulnerable/resistant lists, and
 * passing only the active subset of statuses (the user's toggle).
 *
 * Formula (verbatim from the spec):
 *
 *   boost_multiplier(b):
 *     +b → (100 + b) / 100        # symmetric
 *     -b → 100 / (100 - b)        # multiplicative inverse
 *
 *   For each attack-category move:
 *     atk_term   = round((power + flat_power_total) × bm(pct_power_total))
 *     atk_used   = round(atk × bm(atk_boost_total))
 *     def_used   = round(def × bm(def_boost_total))
 *
 *     STAB     = 1.25 if move.type ∈ {main_type, sub_type} else 1
 *     type_eff = 3 / 2 / 1 / 0.5 / 0.25 lookup
 *
 *     damage = round(
 *       0.9 × atk_term × atk_used / def_used
 *       × STAB × type_eff
 *       × defender_dmg_factor    (∏ (1 - red/100))
 *       × attacker_dmg_factor    (∏ (1 + bonus/100))
 *     )
 *
 * Four `Math.round` calls — three sub-terms + one outer.
 */

import {
  combineStatuses,
  boostMultiplier,
  type StatusDeltas,
} from "./statusModel";
import { setsFor, typeEffectiveness, type TypeSets } from "./typeEffectiveness";
import type { StatusOut, TypeOut } from "@/types";

/**
 * Math.round in JavaScript rounds half to +∞ for positive values
 * (Math.round(0.5) === 1), which agrees with Python's Decimal
 * ROUND_HALF_UP for non-negative inputs. All damage values are
 * non-negative in practice — same precondition as compute_effective_stats.
 */
const roundHalfUp = (n: number): number => Math.round(n);

/** Inputs to one matchup damage call. */
export interface ComputeMoveDamageInput {
  /** Move base power (the move's `power` field). */
  movePower: number;
  /** Move's type name (e.g. "Fire"). */
  moveTypeName: string;
  /** True for MAG_ATTACK, false for PHY_ATTACK. */
  isMagic: boolean;

  /** Attacker's effective atk (mag_atk if isMagic else phy_atk), pre-status. */
  attackerAtk: number;
  /** Attacker's main type name. */
  attackerMainType: string;
  /** Attacker's sub type name, or null if single-typed. */
  attackerSubType: string | null;

  /** Defender's effective def (mag_def if isMagic else phy_def), pre-status. */
  defenderDef: number;
  /** Defender main type sets (vuln/resist). */
  defenderMainSets: TypeSets;
  /** Defender sub type sets, or null if single-typed. */
  defenderSubSets: TypeSets | null;

  /** Active attacker statuses (the user's selection). */
  attackerStatuses?: readonly StatusOut[];
  /** Active defender statuses (the user's selection). */
  defenderStatuses?: readonly StatusOut[];
}

/** Result of one matchup damage call. */
export interface DamageResult {
  damage: number;
  /** Pre-status atk used in the formula (after rounding the boost multiplier). */
  atkUsed: number;
  /** Pre-status def used in the formula (after rounding the boost multiplier). */
  defUsed: number;
  /** Type effectiveness multiplier (one of 3 / 2 / 1 / 0.5 / 0.25). */
  typeMultiplier: number;
  /** STAB factor (1 or 1.25). */
  stab: number;
}

/**
 * Compute the damage one attack-category move deals against a defender.
 *
 * Returns 0 for degenerate / zero-or-less inner expressions (defensive —
 * the spec doesn't define negative damage).
 */
export function computeMoveDamage(input: ComputeMoveDamageInput): DamageResult {
  const deltas: StatusDeltas = combineStatuses(
    input.attackerStatuses ?? [],
    input.defenderStatuses ?? [],
    input.isMagic,
  );

  const powerTerm = roundHalfUp(
    (input.movePower + deltas.flat_power_total) * boostMultiplier(deltas.pct_power_total),
  );
  const atkUsed = roundHalfUp(input.attackerAtk * boostMultiplier(deltas.atk_boost_total));
  const defUsed = roundHalfUp(input.defenderDef * boostMultiplier(deltas.def_boost_total));

  // Defensive: stat formula keeps def > 0 in practice.
  if (defUsed <= 0) {
    return { damage: 0, atkUsed, defUsed, typeMultiplier: 1, stab: 1 };
  }

  const stab =
    input.moveTypeName === input.attackerMainType ||
    (input.attackerSubType !== null && input.moveTypeName === input.attackerSubType)
      ? 1.25
      : 1;

  const typeMultiplier = typeEffectiveness(
    input.moveTypeName,
    input.defenderMainSets,
    input.defenderSubSets,
  );

  const inner =
    0.9 *
    powerTerm *
    atkUsed /
    defUsed *
    stab *
    typeMultiplier *
    deltas.defender_dmg_factor *
    deltas.attacker_dmg_factor;

  const damage = inner <= 0 ? 0 : roundHalfUp(inner);

  return { damage, atkUsed, defUsed, typeMultiplier, stab };
}

/**
 * Convenience: build TypeSets from a TypeOut (or null for single-type).
 * Re-exported from typeEffectiveness so callers don't need a second import.
 */
export function setsFromType(t: TypeOut | null | undefined): TypeSets | null {
  if (!t) return null;
  return setsFor(t);
}
