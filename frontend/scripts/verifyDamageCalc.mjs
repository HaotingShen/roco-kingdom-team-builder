/**
 * Cross-check the frontend damage formula against the backend fixture values.
 *
 * Mirrors all 4 numeric fixtures from backend/tests/test_damage_calculation.py.
 * Run with:  node frontend/scripts/verifyDamageCalc.mjs
 *
 * Exit 0 = all fixtures match.  Exit 1 = at least one mismatch — the frontend
 * and backend formulas have drifted and must be reconciled before merging.
 *
 * This script intentionally duplicates the fixture arithmetic inline so it
 * is self-contained and runnable without bundling (uses only Node built-ins +
 * relative imports via --input-type=module isn't needed — the .mjs extension
 * handles it).  The trade-off: if fixture values change in the Python tests,
 * this file must be updated too.
 */

// ---------------------------------------------------------------------------
// Inline port of the formula helpers (mirrors src/lib/statusModel.ts and
// src/lib/damageCalc.ts).  We duplicate them here so the script runs without
// a build step; the real source of truth remains those TS files.
// ---------------------------------------------------------------------------

function boostMultiplier(boost) {
  if (boost >= 0) return (100 + boost) / 100;
  return 100 / (100 - boost);
}

function roundHalfUp(n) {
  return Math.round(n);
}

function combineStatuses(attackerStatuses, defenderStatuses, isMagic) {
  let flat_power_total = 0, pct_power_total = 0, atk_boost_total = 0, attacker_dmg_factor = 1;
  for (const s of attackerStatuses) {
    flat_power_total += s.flat_power_boost ?? 0;
    pct_power_total  += s.pct_power_boost  ?? 0;
    atk_boost_total  += isMagic ? (s.mag_atk_boost ?? 0) : (s.phy_atk_boost ?? 0);
    if (s.dmg_bonus_pct) attacker_dmg_factor *= 1 + s.dmg_bonus_pct / 100;
  }
  let def_boost_total = 0, defender_dmg_factor = 1;
  for (const s of defenderStatuses) {
    def_boost_total    += isMagic ? (s.mag_def_boost ?? 0) : (s.phy_def_boost ?? 0);
    if (s.dmg_reduction_pct) defender_dmg_factor *= 1 - s.dmg_reduction_pct / 100;
  }
  return { flat_power_total, pct_power_total, atk_boost_total, def_boost_total, attacker_dmg_factor, defender_dmg_factor };
}

function typeEffectiveness(moveTypeName, main, sub) {
  const mainVuln = main.vuln.has(moveTypeName), mainResist = main.resist.has(moveTypeName);
  if (!sub) {
    if (mainVuln) return 2; if (mainResist) return 0.5; return 1;
  }
  const subVuln = sub.vuln.has(moveTypeName), subResist = sub.resist.has(moveTypeName);
  if (mainVuln && subVuln) return 3;
  if (mainResist && subResist) return 0.25;
  if ((mainVuln && subResist) || (mainResist && subVuln)) return 1;
  if (mainVuln || subVuln) return 2;
  if (mainResist || subResist) return 0.5;
  return 1;
}

function computeMoveDamage({ movePower, moveTypeName, isMagic, attackerAtk, attackerMainType, attackerSubType, defenderDef, defenderMainVuln, defenderMainResist, defenderSubVuln, defenderSubResist, attackerStatuses = [], defenderStatuses = [] }) {
  const d = combineStatuses(attackerStatuses, defenderStatuses, isMagic);
  const powerTerm = roundHalfUp((movePower + d.flat_power_total) * boostMultiplier(d.pct_power_total));
  const atkUsed   = roundHalfUp(attackerAtk * boostMultiplier(d.atk_boost_total));
  const defUsed   = roundHalfUp(defenderDef * boostMultiplier(d.def_boost_total));
  if (defUsed <= 0) return 0;
  const stab = (moveTypeName === attackerMainType || (attackerSubType !== null && moveTypeName === attackerSubType)) ? 1.25 : 1;
  const main = { vuln: new Set(defenderMainVuln), resist: new Set(defenderMainResist) };
  const sub  = defenderSubVuln != null ? { vuln: new Set(defenderSubVuln), resist: new Set(defenderSubResist) } : null;
  const typeEff = typeEffectiveness(moveTypeName, main, sub);
  const inner = 0.9 * powerTerm * atkUsed / defUsed * stab * typeEff * d.defender_dmg_factor * d.attacker_dmg_factor;
  return inner <= 0 ? 0 : roundHalfUp(inner);
}

// ---------------------------------------------------------------------------
// Fixtures (mirror backend/tests/test_damage_calculation.py exactly)
// ---------------------------------------------------------------------------

const fixtures = [
  {
    name: "Fixture 1 — single-type vuln, STAB, statuses on both sides",
    expected: 309,
    input: {
      movePower: 80, moveTypeName: "Fire", isMagic: true,
      attackerAtk: 200, attackerMainType: "Fire", attackerSubType: null,
      defenderDef: 150, defenderMainVuln: ["Fire"], defenderMainResist: [],
      defenderSubVuln: null, defenderSubResist: null,
      attackerStatuses: [{ pct_power_boost: 20, mag_atk_boost: 30, dmg_bonus_pct: 10 }],
      defenderStatuses: [{ mag_def_boost: 20, dmg_reduction_pct: 10 }],
    },
  },
  {
    name: "Fixture 2 — dual-type triple weak (×3), no STAB, no statuses",
    expected: 405,
    input: {
      movePower: 100, moveTypeName: "Fighting", isMagic: false,
      attackerAtk: 180, attackerMainType: "Normal", attackerSubType: null,
      defenderDef: 120, defenderMainVuln: ["Fighting"], defenderMainResist: [],
      defenderSubVuln: ["Fighting"], defenderSubResist: [],
      attackerStatuses: [], defenderStatuses: [],
    },
  },
  {
    name: "Fixture 3 — stacked statuses (additive stats, multiplicative dmg modifiers)",
    expected: 475,
    input: {
      movePower: 70, moveTypeName: "Water", isMagic: true,
      attackerAtk: 220, attackerMainType: "Water", attackerSubType: "Ice",
      defenderDef: 130, defenderMainVuln: ["Water"], defenderMainResist: [],
      defenderSubVuln: null, defenderSubResist: null,
      attackerStatuses: [
        { pct_power_boost: 20, mag_atk_boost: 20, dmg_bonus_pct: 10 },
        { pct_power_boost: 30, mag_atk_boost: 30, dmg_bonus_pct: 20 },
      ],
      defenderStatuses: [
        { mag_def_boost: 10, dmg_reduction_pct: 10 },
        { mag_def_boost: 10, dmg_reduction_pct: 20 },
      ],
    },
  },
  {
    name: "Fixture 4 — type cancellation (×1), negative atk debuff, flat power boost, sub-type STAB",
    expected: 105,
    input: {
      movePower: 60, moveTypeName: "Fire", isMagic: false,
      attackerAtk: 250, attackerMainType: "Dragon", attackerSubType: "Fire",
      defenderDef: 200, defenderMainVuln: [], defenderMainResist: ["Fire"],
      defenderSubVuln: ["Fire"], defenderSubResist: [],
      attackerStatuses: [{ flat_power_boost: 30, phy_atk_boost: -20 }],
      defenderStatuses: [],
    },
  },
];

// ---------------------------------------------------------------------------
// Run
// ---------------------------------------------------------------------------

let passed = 0, failed = 0;
for (const { name, expected, input } of fixtures) {
  const got = computeMoveDamage(input);
  if (got === expected) {
    console.log(`  PASS  ${name}`);
    passed++;
  } else {
    console.error(`  FAIL  ${name}`);
    console.error(`        expected ${expected}, got ${got}`);
    failed++;
  }
}

console.log(`\n${passed} passed, ${failed} failed.`);
if (failed > 0) process.exit(1);
