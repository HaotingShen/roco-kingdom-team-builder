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

// ─── Dynamic power formula helpers ───────────────────────────────────────────

/**
 * Step-table used by Swift Strike (speed_diff) and Sand Trap (phy_def_diff).
 * Input: attacker stat − defender stat. Returns effective move power.
 */
function getStatDiffPower(diff: number): number {
  if (diff <= 0) return 60;
  if (diff <= 30) return 80;
  if (diff <= 60) return 100;
  if (diff <= 90) return 120;
  if (diff <= 120) return 140;
  if (diff <= 150) return 150;
  if (diff <= 180) return 160;
  if (diff <= 210) return 170;
  if (diff <= 240) return 180;
  if (diff <= 270) return 190;
  return 200;
}

/** Power lookup for Mana Burst at each energy level 0–10. */
const ENERGY_POWER_TABLE = [46, 71, 91, 111, 136, 156, 166, 181, 191, 201, 211] as const;

function getEnergyPower(level: number): number {
  return ENERGY_POWER_TABLE[Math.max(0, Math.min(10, level)) as 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10];
}

// ─────────────────────────────────────────────────────────────────────────────

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
  /** Number of hits (≥2 for multi-hit moves). 1 when not a combo move. */
  baseCombo: number;
  /**
   * Conditional alt damage for move_specific statuses (always shown, no toggle).
   * Undefined when the move has no conditional power bonus.
   */
  altDamage?: number;
  altHpPercent?: number;
  /** Localized condition label, e.g. { zh: "有减益时", en: "With any Debuff" } */
  altCondition?: { zh: string; en: string };
  /**
   * Present when power_formula is set. Carries the effective power used and the
   * stat diff (for speed_diff / phy_def_diff) so the UI can render an annotation.
   */
  formulaAnnotation?: {
    formula: "speed_diff" | "phy_def_diff" | "energy";
    effectivePower: number;
    /** Attacker stat − defender stat (only set for speed_diff / phy_def_diff). */
    statDiff?: number;
  };
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
    /** Current energy level for Mana Burst (0–10). Defaults to 10. */
    magicEnergyLevel?: number;
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
        baseCombo: 1,
      };
    }

    const baseCombo = Math.max(1, move.base_combo ?? 1);

    // Dynamic power formulas — override move.power for three special moves.
    let effectivePower = move.power;
    let formulaAnnotation: MoveMatchupResult["formulaAnnotation"];
    if (move.power_formula === "speed_diff") {
      const diff = attackerStats.spd - defenderStats.spd;
      effectivePower = getStatDiffPower(diff);
      formulaAnnotation = { formula: "speed_diff", effectivePower, statDiff: diff };
    } else if (move.power_formula === "phy_def_diff") {
      const diff = attackerStats.phy_def - defenderStats.phy_def;
      effectivePower = getStatDiffPower(diff);
      formulaAnnotation = { formula: "phy_def_diff", effectivePower, statDiff: diff };
    } else if (move.power_formula === "energy") {
      const level = Math.max(0, Math.min(10, scenario.magicEnergyLevel ?? 10));
      effectivePower = getEnergyPower(level);
      formulaAnnotation = { formula: "energy", effectivePower };
    }

    const result: DamageResult = computeMoveDamage({
      movePower: effectivePower * baseCombo,
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

    // Alt damage: move_specific conditional status (power_bonus) takes priority;
    // fall back to counter_power_multiplier if set.
    const conditionalStatus = (move.statuses ?? []).find(
      (s) => s.usage === "move_specific" && s.power_bonus > 0,
    );
    let altDamage: number | undefined;
    let altHpPercent: number | undefined;
    let altCondition: { zh: string; en: string } | undefined;
    if (conditionalStatus) {
      const altResult = computeMoveDamage({
        movePower: (effectivePower + conditionalStatus.power_bonus) * baseCombo,
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
      altDamage = altResult.damage;
      altHpPercent = defenderStats.hp > 0 ? (altResult.damage / defenderStats.hp) * 100 : 0;
      altCondition = {
        zh: (conditionalStatus.localized as Record<string, { name?: string }>)?.zh?.name ?? conditionalStatus.name,
        en: (conditionalStatus.localized as Record<string, { name?: string }>)?.en?.name ?? conditionalStatus.name,
      };
    } else if (move.counter_power_multiplier) {
      const altResult = computeMoveDamage({
        movePower: effectivePower * baseCombo * move.counter_power_multiplier,
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
      altDamage = altResult.damage;
      altHpPercent = defenderStats.hp > 0 ? (altResult.damage / defenderStats.hp) * 100 : 0;
      altCondition = { zh: "应对状态", en: "Counter Status" };
    } else if (move.alt_power_total && move.alt_condition_zh && move.alt_condition_en) {
      const altResult = computeMoveDamage({
        movePower: move.alt_power_total,
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
      altDamage = altResult.damage;
      altHpPercent = defenderStats.hp > 0 ? (altResult.damage / defenderStats.hp) * 100 : 0;
      altCondition = { zh: move.alt_condition_zh, en: move.alt_condition_en };
    }

    return {
      move,
      nonAttack: false,
      damage: result.damage,
      hpPercent,
      typeMultiplier: result.typeMultiplier,
      stab: result.stab,
      baseCombo,
      altDamage,
      altHpPercent,
      altCondition,
      formulaAnnotation,
    };
  });

  return {
    moves,
    defenderEffectiveHp: defenderStats.hp,
  };
}
