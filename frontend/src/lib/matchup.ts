/**
 * High-level matchup orchestrator: (attacker, defender, scenario) → per-move damage list.
 *
 * This is the ONLY function the UI layer needs to call. It composes:
 *
 *   1. computeEffectiveStats (attacker + defender)        — from lib/effectiveStats
 *   2. setsFor (defender main + sub type)                 — from lib/typeEffectiveness
 *   3. computeMoveDamage (per attack-category move)       — from lib/damageCalc
 *
 * Knows nothing about teams, featured teams, react-query, the URL, or
 * any UI state. Pure inputs, pure output. Reusable for the per-slot view
 * (current scope) and any future "vs featured team aggregation" code that
 * just needs to call this in a loop.
 *
 * Defender / attacker statuses are PASSED IN by the caller — the
 * orchestrator doesn't know which subset is "active." That's a UI
 * concern (toggle state).
 */

import { computeEffectiveStats } from "./effectiveStats";
import { computeMoveDamage, type DamageResult } from "./damageCalc";
import { setsFor } from "./typeEffectiveness";
import type {
  MonsterOut,
  MoveOut,
  PersonalityOut,
  StatusOut,
  TalentUpsert,
} from "@/types";

/** All the data needed to evaluate one side of a matchup. */
export interface MatchupSide {
  monster: MonsterOut;
  talent: TalentUpsert;
  personality: PersonalityOut;
}

/**
 * Per-move result line, ready to render in a damage list.
 *
 * `move` is preserved so the renderer can show the move name / icon
 * without a second lookup. `nonAttack` is true for non-PHY/MAG moves
 * (defense / status), where damage is not meaningful — UI should skip
 * or grey-out these rows.
 */
export interface MoveMatchupResult {
  move: MoveOut;
  /** True for moves that don't deal damage (DEFENSE / STATUS). */
  nonAttack: boolean;
  /** Computed damage; 0 for nonAttack moves. */
  damage: number;
  /** Damage as a percent of defender's effective HP. */
  hpPercent: number;
  /** Type effectiveness multiplier (3 / 2 / 1 / 0.5 / 0.25). */
  typeMultiplier: number;
  /** STAB multiplier (1 or 1.25). */
  stab: number;
}

/** The full result of one matchup evaluation. */
export interface MatchupResult {
  /** Per-move damage rows, in input order. */
  moves: MoveMatchupResult[];
  /** Defender's effective HP after stat formula. */
  defenderEffectiveHp: number;
}

/** Wire-format vs. enum-name normaliser, mirroring MoveCoveragePanel's helper. */
function normalizeMoveCategory(category?: string): string {
  if (!category) return "";
  const upper = category.toUpperCase();
  if (upper === "PHYSICAL ATTACK") return "PHY_ATTACK";
  if (upper === "MAGIC ATTACK") return "MAG_ATTACK";
  return upper;
}

/**
 * Compute the matchup of one attacker vs one defender, per the
 * attacker's chosen moves and the active status sets.
 *
 * Performance note: this iterates the attacker's moves once and calls
 * computeMoveDamage for attack-category moves only. ≤4 moves × cheap
 * arithmetic = trivially fast. Memoize at the call site if the inputs
 * are stable across renders (the React caller in MatchupPanel does this).
 */
export function computeMatchup(
  attacker: MatchupSide,
  attackerMoves: readonly MoveOut[],
  defender: MatchupSide,
  scenario: {
    attackerStatuses?: readonly StatusOut[];
    defenderStatuses?: readonly StatusOut[];
  } = {},
): MatchupResult {
  // Effective stats — shared formula with the per-slot stats panel.
  const attackerStats = computeEffectiveStats(
    attacker.monster,
    attacker.talent,
    attacker.personality,
  );
  const defenderStats = computeEffectiveStats(
    defender.monster,
    defender.talent,
    defender.personality,
  );

  // Defender type sets — built once, reused across all moves in this call.
  const defMainSets = defender.monster.main_type
    ? setsFor(defender.monster.main_type)
    : null;
  const defSubSets = defender.monster.sub_type
    ? setsFor(defender.monster.sub_type)
    : null;

  // Attacker type names — used for STAB.
  const attackerMainType = attacker.monster.main_type?.name ?? "";
  const attackerSubType = attacker.monster.sub_type?.name ?? null;

  const moves: MoveMatchupResult[] = attackerMoves.map((move) => {
    const cat = normalizeMoveCategory(move.move_category ?? move.category);
    const isPhy = cat === "PHY_ATTACK";
    const isMag = cat === "MAG_ATTACK";
    const moveTypeName = move.move_type?.name ?? move.type?.name ?? "";

    // Non-attack moves don't compute damage. Return a sentinel row so
    // the UI can render them in-line (e.g. "Defense — N/A") without
    // needing a separate filter pass.
    if ((!isPhy && !isMag) || !move.power || !moveTypeName || !defMainSets) {
      return {
        move,
        nonAttack: true,
        damage: 0,
        hpPercent: 0,
        typeMultiplier: 1,
        stab: 1,
      };
    }

    const result: DamageResult = computeMoveDamage({
      movePower: move.power,
      moveTypeName,
      isMagic: isMag,
      attackerAtk: isMag ? attackerStats.mag_atk : attackerStats.phy_atk,
      attackerMainType,
      attackerSubType,
      defenderDef: isMag ? defenderStats.mag_def : defenderStats.phy_def,
      defenderMainSets: defMainSets,
      defenderSubSets: defSubSets,
      attackerStatuses: scenario.attackerStatuses,
      defenderStatuses: scenario.defenderStatuses,
    });

    const hpPercent =
      defenderStats.hp > 0 ? (result.damage / defenderStats.hp) * 100 : 0;

    return {
      move,
      nonAttack: false,
      damage: result.damage,
      hpPercent,
      typeMultiplier: result.typeMultiplier,
      stab: result.stab,
    };
  });

  return {
    moves,
    defenderEffectiveHp: defenderStats.hp,
  };
}
