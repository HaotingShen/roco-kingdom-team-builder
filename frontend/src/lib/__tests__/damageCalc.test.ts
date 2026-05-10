/**
 * Damage formula tests — TS mirror of backend/tests/test_damage_calculation.py.
 *
 * Every fixture here MUST produce the same integer as its Python counterpart.
 * The arithmetic is hand-traced in comments so it's auditable without
 * re-deriving the formula.
 *
 * StatusOut shape used in fixtures: only the fields the formula reads are set;
 * the rest are 0 (matching the DB defaults).
 */

import { describe, it, expect } from "vitest";
import { computeMoveDamage } from "../damageCalc";
import { boostMultiplier, combineStatuses } from "../statusModel";
import { clearTypeSetsCache } from "../typeEffectiveness";
import type { StatusOut } from "@/types";
import type { TypeSets } from "../typeEffectiveness";

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Build a minimal StatusOut with all numeric fields defaulting to 0. */
function status(overrides: Partial<StatusOut>): StatusOut {
  return {
    id: 0,
    name: "test",
    hp_boost: 0,
    phy_atk_boost: 0,
    mag_atk_boost: 0,
    phy_def_boost: 0,
    mag_def_boost: 0,
    spd_boost: 0,
    flat_power_boost: 0,
    pct_power_boost: 0,
    combo_bonus: 0,
    dmg_reduction_pct: 0,
    dmg_bonus_pct: 0,
    power_bonus: 0,
    ...overrides,
  };
}

/** Build a TypeSets directly from string arrays (bypasses the TypeOut cache). */
function sets(vuln: string[], resist: string[]): TypeSets {
  return { vuln: new Set(vuln), resist: new Set(resist) };
}

// Clear the module-level cache before each group so stubs don't bleed through.
clearTypeSetsCache();

// ─── boostMultiplier ──────────────────────────────────────────────────────────

describe("boostMultiplier", () => {
  it("0 → ×1.0", () => expect(boostMultiplier(0)).toBe(1.0));
  it("+20 → ×1.20", () => expect(boostMultiplier(20)).toBe(1.2));
  it("-20 → ×(1/1.20) — symmetric inverse of +20", () => {
    expect(boostMultiplier(-20)).toBeCloseTo(1 / 1.2, 12);
  });
  it("+X and −X are multiplicative inverses (round-trip to 1.0)", () => {
    for (const b of [20, 50, 100, 130]) {
      expect(boostMultiplier(b) * boostMultiplier(-b)).toBeCloseTo(1.0, 12);
    }
  });
});

// ─── combineStatuses ──────────────────────────────────────────────────────────

describe("combineStatuses", () => {
  it("stat boosts add, dmg_bonus_pct multiplies", () => {
    const s1 = status({ phy_atk_boost: 20, dmg_bonus_pct: 10 });
    const s2 = status({ phy_atk_boost: 30, dmg_bonus_pct: 20 });
    const d = combineStatuses([s1, s2], [], false);
    expect(d.atk_boost_total).toBe(50);
    // (1.10)(1.20) = 1.32, NOT 1.30
    expect(d.attacker_dmg_factor).toBeCloseTo(1.32, 12);
  });

  it("def boosts add, dmg_reduction_pct multiplies", () => {
    const s1 = status({ mag_def_boost: 20, dmg_reduction_pct: 10 });
    const s2 = status({ mag_def_boost: 30, dmg_reduction_pct: 20 });
    const d = combineStatuses([], [s1, s2], true);
    expect(d.def_boost_total).toBe(50);
    // (1 - 0.10)(1 - 0.20) = 0.72, NOT 0.70
    expect(d.defender_dmg_factor).toBeCloseTo(0.72, 12);
  });

  it("opponent debuff: negative def_boost lowers def_boost_total", () => {
    // Sharp Eyes: affect=opponent, phy_def_boost=-120, mag_def_boost=-120
    const sharpEyes = status({ phy_def_boost: -120, mag_def_boost: -120 });
    const d = combineStatuses([], [sharpEyes], false);
    expect(d.def_boost_total).toBe(-120);
  });
});

// ─── Fixture 1 — mirror of Python test_damage_fixture_1 ──────────────────────

describe("computeMoveDamage — base formula fixtures (mirror Python)", () => {
  it("Fixture 1: single-type vuln ×2, STAB, one status each side", () => {
    // Attacker: Fire (single), mag_atk=200, status: pct_power=+20 atk=+30 dmg_bonus=+10
    // Defender: Grass (single, vuln Fire), mag_def=150, status: def=+20 reduction=+10
    // Move: Fire / MAG / power 80
    //
    // power_term = round((80 + 0) × bm(+20))  = round(80 × 1.20) = round(96) = 96
    // atk_term   = round(200 × bm(+30))       = round(200 × 1.30) = round(260) = 260
    // def_term   = round(150 × bm(+20))       = round(150 × 1.20) = round(180) = 180
    // STAB       = 1.25   (Fire move, Fire attacker)
    // type_eff   = 2.0    (Grass single-type, vuln Fire)
    // inner      = 0.9 × 96 × 260 / 180 × 1.25 × 2.0 × 0.90 × 1.10
    //            = 86.4 × 260 = 22464 / 180 = 124.8 × 1.25 = 156.0 × 2.0 = 312.0
    //            × 0.90 = 280.8 × 1.10 = 308.88
    // damage     = round(308.88) = 309
    const { damage } = computeMoveDamage({
      movePower: 80,
      moveTypeName: "Fire",
      isMagic: true,
      attackerAtk: 200,
      attackerMainType: "Fire",
      attackerSubType: null,
      defenderDef: 150,
      defenderMainSets: sets(["Fire"], []),
      defenderSubSets: null,
      attackerStatuses: [status({ pct_power_boost: 20, mag_atk_boost: 30, dmg_bonus_pct: 10 })],
      defenderStatuses: [status({ mag_def_boost: 20, dmg_reduction_pct: 10 })],
    });
    expect(damage).toBe(309);
  });

  it("Fixture 2: dual-type ×3 (both vuln), no STAB, no statuses", () => {
    // Attacker: Normal (single), phy_atk=180, no statuses
    // Defender: Grass / Bug (both vuln to Fighting), phy_def=120
    // Move: Fighting / PHY / power 100
    //
    // power_term = 100, atk_term = 180, def_term = 120
    // STAB = 1.0 (Normal attacker, Fighting move)
    // type_eff = 3.0
    // inner = 0.9 × 100 × 180 / 120 × 1.0 × 3.0 = 90 × 180 / 120 × 3 = 405
    const { damage } = computeMoveDamage({
      movePower: 100,
      moveTypeName: "Fighting",
      isMagic: false,
      attackerAtk: 180,
      attackerMainType: "Normal",
      attackerSubType: null,
      defenderDef: 120,
      defenderMainSets: sets(["Fighting"], []),
      defenderSubSets: sets(["Fighting"], []),
    });
    expect(damage).toBe(405);
  });

  it("Fixture 3: stacked statuses — add stats, multiply dmg factors", () => {
    // Attacker: Water / Ice, mag_atk=220, two statuses:
    //   s1: pct=+20 atk=+20 dmg_bonus=+10 | s2: pct=+30 atk=+30 dmg_bonus=+20
    // Defender: Fire (single, vuln Water), mag_def=130, two statuses:
    //   d1: def=+10 reduction=+10 | d2: def=+10 reduction=+20
    // Move: Water / MAG / power 70
    //
    // pct_total=+50 → bm(+50)=1.50; atk_total=+50; atk_dmg=(1.10)(1.20)=1.32
    // def_total=+20 → bm(+20)=1.20; def_dmg=(0.90)(0.80)=0.72
    // power_term = round(70 × 1.50) = round(105) = 105
    // atk_term   = round(220 × 1.50) = round(330) = 330
    // def_term   = round(130 × 1.20) = round(156) = 156
    // STAB=1.25 (Water attacker / Water move)
    // type_eff=2.0 (Fire single vuln Water)
    // inner = 0.9 × 105 × 330 / 156 × 1.25 × 2.0 × 0.72 × 1.32
    //       = 94.5 × 330 = 31185 / 156 = 199.903… × 1.25 = 249.879… × 2.0 = 499.759…
    //       × 0.72 = 359.826… × 1.32 = 474.971… → round = 475
    const { damage } = computeMoveDamage({
      movePower: 70,
      moveTypeName: "Water",
      isMagic: true,
      attackerAtk: 220,
      attackerMainType: "Water",
      attackerSubType: "Ice",
      defenderDef: 130,
      defenderMainSets: sets(["Water"], []),
      defenderSubSets: null,
      attackerStatuses: [
        status({ pct_power_boost: 20, mag_atk_boost: 20, dmg_bonus_pct: 10 }),
        status({ pct_power_boost: 30, mag_atk_boost: 30, dmg_bonus_pct: 20 }),
      ],
      defenderStatuses: [
        status({ mag_def_boost: 10, dmg_reduction_pct: 10 }),
        status({ mag_def_boost: 10, dmg_reduction_pct: 20 }),
      ],
    });
    expect(damage).toBe(475);
  });

  it("Fixture 4: type cancellation ×1, flat_power, negative atk debuff, sub-type STAB", () => {
    // Attacker: Dragon / Fire, phy_atk=250, status: flat_power=+30 phy_atk_boost=-20
    // Defender: Water / Fire (cancel — resist Fire on Water, vuln Fire on Fire), phy_def=200
    // Move: Fire / PHY / power 60
    //
    // power_term = round((60+30) × bm(0)) = round(90) = 90
    // atk_term   = round(250 × bm(-20))  = round(250 × 100/120) = round(208.333…) = 208
    // def_term   = round(200 × bm(0))    = 200
    // STAB       = 1.25 (sub-type Fire matches move Fire)
    // type_eff   = 1.0  (vuln on one half, resist on other — cancelled)
    // inner      = 0.9 × 90 × 208 / 200 × 1.25 = 81 × 208 / 200 × 1.25
    //            = 16848 / 200 = 84.24 × 1.25 = 105.30 → round = 105
    const { damage } = computeMoveDamage({
      movePower: 60,
      moveTypeName: "Fire",
      isMagic: false,
      attackerAtk: 250,
      attackerMainType: "Dragon",
      attackerSubType: "Fire",
      defenderDef: 200,
      defenderMainSets: sets([], ["Fire"]),
      defenderSubSets: sets(["Fire"], []),
      attackerStatuses: [status({ flat_power_boost: 30, phy_atk_boost: -20 })],
    });
    expect(damage).toBe(105);
  });

  it("Defend status (dmg_reduction_pct=70) reduces damage by 70%", () => {
    // Baseline: Normal/PHY power=100 atk=200 def=100 no STAB no type advantage
    // inner = 0.9 × 100 × 200 / 100 × 1.25 × 1.0 = 225 → round = 225
    // Defended: × (1 - 0.70) = × 0.30 → 225 × 0.30 = 67.5 → round = 68
    const base = computeMoveDamage({
      movePower: 100, moveTypeName: "Normal", isMagic: false,
      attackerAtk: 200, attackerMainType: "Normal", attackerSubType: null,
      defenderDef: 100, defenderMainSets: sets([], []), defenderSubSets: null,
    });
    const defended = computeMoveDamage({
      movePower: 100, moveTypeName: "Normal", isMagic: false,
      attackerAtk: 200, attackerMainType: "Normal", attackerSubType: null,
      defenderDef: 100, defenderMainSets: sets([], []), defenderSubSets: null,
      defenderStatuses: [status({ dmg_reduction_pct: 70 })],
    });
    expect(base.damage).toBe(225);
    expect(defended.damage).toBe(68);
  });
});

// ─── New fixtures: conditional alt-damage flows ───────────────────────────────

describe("computeMoveDamage — conditional alt-damage flows", () => {
  it("counter_power_multiplier: total power = base × combo × multiplier", () => {
    // Multi-Claw Strike: power=30, base_combo=2, counter_power_multiplier=2
    // Orchestrator passes movePower = 30 × 2 × 2 = 120 for the counter alt row.
    // Attacker: Normal (single), phy_atk=200, def=100, no statuses.
    //
    // power_term = round(120 × bm(0)) = 120
    // atk_term   = round(200 × bm(0)) = 200
    // def_term   = round(100 × bm(0)) = 100
    // STAB = 1.25 (Normal attacker, Normal move)
    // type_eff = 1.0
    // inner = 0.9 × 120 × 200 / 100 × 1.25 = 108 × 200 / 100 × 1.25
    //       = 21600 / 100 × 1.25 = 216 × 1.25 = 270
    const base = computeMoveDamage({
      movePower: 60, // 30 × combo 2
      moveTypeName: "Normal", isMagic: false,
      attackerAtk: 200, attackerMainType: "Normal", attackerSubType: null,
      defenderDef: 100, defenderMainSets: sets([], []), defenderSubSets: null,
    });
    const counter = computeMoveDamage({
      movePower: 120, // 30 × combo 2 × multiplier 2
      moveTypeName: "Normal", isMagic: false,
      attackerAtk: 200, attackerMainType: "Normal", attackerSubType: null,
      defenderDef: 100, defenderMainSets: sets([], []), defenderSubSets: null,
    });
    // inner_base   = 0.9 × 60 × 200 / 100 × 1.25 = 54 × 200 / 100 × 1.25 = 135
    // inner_counter = 270 (as traced above)
    expect(base.damage).toBe(135);
    expect(counter.damage).toBe(270);
    expect(counter.damage).toBe(base.damage * 2);
  });

  it("alt_power_total: pre-computed conditional power replaces base power", () => {
    // Extreme Cold Zone: power=105, alt_power_total=165 (if opponent has Freeze).
    // Orchestrator passes movePower=165 for the alt row.
    // Attacker: Ice (single), mag_atk=180, def=150, no statuses, dual-type defender (Ice vuln both).
    //
    // Base (power=105):
    //   power_term = 105, atk_term = 180, def_term = 150
    //   STAB = 1.25 (Ice attacker, Ice move)
    //   type_eff = 3.0 (both halves vuln Ice)
    //   inner = 0.9 × 105 × 180 / 150 × 1.25 × 3.0
    //         = 94.5 × 180 = 17010 / 150 = 113.4 × 1.25 = 141.75 × 3.0 = 425.25 → 425
    //
    // Alt (power=165):
    //   power_term = 165
    //   inner = 0.9 × 165 × 180 / 150 × 1.25 × 3.0
    //         = 148.5 × 180 = 26730 / 150 = 178.2 × 1.25 = 222.75 × 3.0 = 668.25 → 668
    const base = computeMoveDamage({
      movePower: 105, moveTypeName: "Ice", isMagic: true,
      attackerAtk: 180, attackerMainType: "Ice", attackerSubType: null,
      defenderDef: 150,
      defenderMainSets: sets(["Ice"], []),
      defenderSubSets: sets(["Ice"], []),
    });
    const alt = computeMoveDamage({
      movePower: 165, moveTypeName: "Ice", isMagic: true,
      attackerAtk: 180, attackerMainType: "Ice", attackerSubType: null,
      defenderDef: 150,
      defenderMainSets: sets(["Ice"], []),
      defenderSubSets: sets(["Ice"], []),
    });
    expect(base.damage).toBe(425);
    expect(alt.damage).toBe(668);
  });

  it("move_specific power_bonus: conditional power = base + bonus", () => {
    // All or Nothing: power=80, power_bonus=60 → conditional movePower=140.
    // Orchestrator passes movePower=140 for the alt row.
    // Attacker: Cute (single), mag_atk=160, def=100, no statuses, neutral type.
    //
    // Base (power=80):
    //   power_term = 80, atk_term = 160, def_term = 100
    //   STAB = 1.25 (Cute attacker, Cute move)
    //   type_eff = 1.0
    //   inner = 0.9 × 80 × 160 / 100 × 1.25 = 72 × 160 / 100 × 1.25 = 11520 / 100 × 1.25 = 144
    //
    // Alt (power=140):
    //   power_term = 140
    //   inner = 0.9 × 140 × 160 / 100 × 1.25 = 126 × 160 / 100 × 1.25 = 20160 / 100 × 1.25 = 252
    const base = computeMoveDamage({
      movePower: 80, moveTypeName: "Cute", isMagic: true,
      attackerAtk: 160, attackerMainType: "Cute", attackerSubType: null,
      defenderDef: 100, defenderMainSets: sets([], []), defenderSubSets: null,
    });
    const alt = computeMoveDamage({
      movePower: 140, moveTypeName: "Cute", isMagic: true,
      attackerAtk: 160, attackerMainType: "Cute", attackerSubType: null,
      defenderDef: 100, defenderMainSets: sets([], []), defenderSubSets: null,
    });
    expect(base.damage).toBe(144);
    expect(alt.damage).toBe(252);
  });

  it("opponent debuff (affect=opponent, negative def_boost) raises damage dealt", () => {
    // Sharp Eyes: phy_def_boost=-120 passed as a defenderStatus.
    // Attacker: Normal (single), phy_atk=200, move power=100, def=200.
    //
    // Baseline (no debuff):
    //   def_term = round(200 × bm(0)) = 200
    //   inner = 0.9 × 100 × 200 / 200 × 1.25 × 1.0 = 90 × 1.25 = 112.5 → 113
    //
    // With Sharp Eyes (phy_def_boost=-120):
    //   bm(-120) = 100 / (100 + 120) = 100 / 220 = 0.4545…
    //   def_term = round(200 × 0.4545…) = round(90.90…) = 91
    //   inner = 0.9 × 100 × 200 / 91 × 1.25 × 1.0
    //         = 90 × 200 / 91 × 1.25 = 18000 / 91 × 1.25 = 197.8… × 1.25 = 247.25… → 247
    const sharpEyes = status({ phy_def_boost: -120 });
    const baseline = computeMoveDamage({
      movePower: 100, moveTypeName: "Normal", isMagic: false,
      attackerAtk: 200, attackerMainType: "Normal", attackerSubType: null,
      defenderDef: 200, defenderMainSets: sets([], []), defenderSubSets: null,
    });
    const debuffed = computeMoveDamage({
      movePower: 100, moveTypeName: "Normal", isMagic: false,
      attackerAtk: 200, attackerMainType: "Normal", attackerSubType: null,
      defenderDef: 200, defenderMainSets: sets([], []), defenderSubSets: null,
      defenderStatuses: [sharpEyes],
    });
    expect(baseline.damage).toBe(113);
    expect(debuffed.damage).toBe(247);
    expect(debuffed.damage).toBeGreaterThan(baseline.damage);
  });

  it("flat + pct power stack: flat added first, then pct multiplied", () => {
    // move.power=60, flat_power_boost=40, pct_power_boost=50
    // power_term = round((60 + 40) × bm(+50)) = round(100 × 1.50) = 150
    // NOT round(60 × 1.50) + 40 = 90 + 40 = 130  ← wrong order
    // Attacker: Normal, phy_atk=200, def=100, no type advantage.
    //
    // Correct: power_term = 150
    //   inner = 0.9 × 150 × 200 / 100 × 1.25 = 135 × 200 / 100 × 1.25 = 337.5 → 338
    //
    // Wrong order would give power_term=130:
    //   inner = 0.9 × 130 × 200 / 100 × 1.25 = 117 × 200 / 100 × 1.25 = 292.5 → 293
    const { damage } = computeMoveDamage({
      movePower: 60, moveTypeName: "Normal", isMagic: false,
      attackerAtk: 200, attackerMainType: "Normal", attackerSubType: null,
      defenderDef: 100, defenderMainSets: sets([], []), defenderSubSets: null,
      attackerStatuses: [status({ flat_power_boost: 40, pct_power_boost: 50 })],
    });
    expect(damage).toBe(338);
    expect(damage).not.toBe(293); // guard against wrong order
  });
});
