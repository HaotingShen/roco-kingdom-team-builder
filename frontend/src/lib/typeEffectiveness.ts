/**
 * Type-effectiveness primitives shared across coverage / matchup components.
 *
 * The game's effectiveness model is encoded by two relations on each defender
 * type: `vulnerable_to` (2× damage) and `resistant_to` (0.5× damage). Anything
 * not in either set is neutral (1×). On a dual-type defender (T1, T2), the
 * combined multiplier follows the convention `mult(T1) * mult(T2)`, with the
 * familiar cancellation: a vuln on one type cancels a resist on the other.
 *
 * This module exposes the minimal set of primitives needed to reason about
 * defender effectiveness without rebuilding the same Sets and predicates in
 * every consumer (currently MoveCoveragePanel; TypeDefensePanel can adopt the
 * same primitives in a follow-up).
 */

import type { TypeOut } from "@/types";
import { LEGACY_TYPES_ORDER } from "@/lib/constants";

/**
 * Normalize backend move category values to frontend enum keys.
 * Wire format: "Physical Attack" / "Magic Attack" / "Defense" / "Status"
 * Frontend enum:  "PHY_ATTACK"     / "MAG_ATTACK"   / "DEFENSE" / "STATUS"
 */
export function normalizeMoveCategory(category: string): string {
  const upper = category.toUpperCase();
  if (upper === "PHYSICAL ATTACK") return "PHY_ATTACK";
  if (upper === "MAGIC ATTACK") return "MAG_ATTACK";
  return upper;
}

/** Pre-built resist/vuln sets for one defender type. */
export type TypeSets = { resist: Set<string>; vuln: Set<string> };

/** Build the resist/vuln Sets for a single defender type once. */
export function setsFor(t: TypeOut): TypeSets {
  return {
    resist: new Set<string>(t.resistant_to ?? []),
    vuln: new Set<string>(t.vulnerable_to ?? []),
  };
}

/**
 * Net effectiveness predicates for a dual defender (T1, T2) against a single
 * attacking move type `m`. "On net" accounts for vuln-cancels-resist:
 *
 *   isResistedOnNet:  combined mult < 1  (at least one resists, neither vuln)
 *   isEffectiveOnNet: combined mult > 1  (at least one vuln,  neither resists)
 *
 * Both are false for the cancelled / neutral case (mult === 1).
 */
export function isResistedOnNet(a: TypeSets, b: TypeSets, m: string): boolean {
  return (a.resist.has(m) || b.resist.has(m)) && !(a.vuln.has(m) || b.vuln.has(m));
}

export function isEffectiveOnNet(a: TypeSets, b: TypeSets, m: string): boolean {
  return (a.vuln.has(m) || b.vuln.has(m)) && !(a.resist.has(m) || b.resist.has(m));
}

/**
 * Multiplier for an attacker's move type against a defender's types,
 * on the game's 5-step scale: 3 / 2 / 1 / 0.5 / 0.25.
 *
 * Used by the damage formula in lib/damageCalc.ts. Mirrors
 * backend.damage.type_effectiveness exactly.
 *
 *   3.0    if both halves are vulnerable
 *   2.0    if exactly one half is vulnerable AND the other doesn't resist
 *   1.0    cancelled (vuln + resist on the two halves) OR neither half cares
 *   0.5    exactly one half resists AND the other doesn't make it vulnerable
 *   0.25   if both halves resist
 *
 * Single-type defender (sub === null) is a degenerate case in {2, 1, 0.5}.
 */
export function typeEffectiveness(
  moveTypeName: string,
  main: TypeSets,
  sub: TypeSets | null,
): number {
  const mainVuln = main.vuln.has(moveTypeName);
  const mainResist = main.resist.has(moveTypeName);

  if (sub === null) {
    if (mainVuln) return 2;
    if (mainResist) return 0.5;
    return 1;
  }

  const subVuln = sub.vuln.has(moveTypeName);
  const subResist = sub.resist.has(moveTypeName);

  if (mainVuln && subVuln) return 3;
  if (mainResist && subResist) return 0.25;
  // vuln on one half + resist on the other → cancelled to neutral
  if ((mainVuln && subResist) || (mainResist && subVuln)) return 1;
  if (mainVuln || subVuln) return 2;
  if (mainResist || subResist) return 0.5;
  return 1;
}

/**
 * The 18 base defender types. "Leader" and any future non-defender pseudo-type
 * the backend may add are excluded — only entries in LEGACY_TYPES_ORDER count.
 *
 * Filter `typesQ.data` through this set before iterating.
 */
export const DEFENDER_TYPE_NAMES: ReadonlySet<string> = new Set(LEGACY_TYPES_ORDER);

/**
 * Comparator that sorts type names by their position in LEGACY_TYPES_ORDER.
 * Names not in the list (defensive — shouldn't happen for filtered defenders)
 * fall to the end via the 999 fallback.
 *
 * Re-typing LEGACY_TYPES_ORDER as `readonly string[]` for the indexOf call
 * keeps consumers from needing the historical `as any` cast.
 */
const ORDER_LIST: readonly string[] = LEGACY_TYPES_ORDER;
export function byLegacyTypeOrder(a: string, b: string): number {
  const ia = ORDER_LIST.indexOf(a);
  const ib = ORDER_LIST.indexOf(b);
  return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
}

/**
 * Comparator for sorting unordered type-name pairs `[a, b]` by their position
 * in LEGACY_TYPES_ORDER (primary key `a`, secondary key `b`). Pure — safe to
 * hoist out of any render or memo.
 */
export function byLegacyTypePairOrder(
  [a1, b1]: readonly [string, string],
  [a2, b2]: readonly [string, string],
): number {
  return byLegacyTypeOrder(a1, a2) || byLegacyTypeOrder(b1, b2);
}

/**
 * One "anchor + partners" group, the compact form of a list of dual-type pairs
 * that share a common type. Display as: anchor icon + name, then a "+" glyph,
 * then a sequence of partner icons (no names — see groupPairsByAnchor docs).
 */
export type DualGroup = {
  anchor: string;
  partners: string[];
};

/**
 * Collapse a flat list of unordered dual-type pairs into anchor-keyed groups.
 *
 * Anchor selection per pair (T1, T2):
 *   1. If exactly one of T1/T2 is in `prioritySet`, that one becomes the anchor
 *      (the other is the partner). This is what makes "Steel + Fire/Water/Ice"
 *      work — Steel is in the single-blind-spot priority set, so it anchors
 *      every pair containing it.
 *   2. Otherwise (both or neither in `prioritySet`), tiebreak by
 *      LEGACY_TYPES_ORDER: the lower-index type wins anchor, for determinism.
 *
 * Within each group, partners are sorted by LEGACY_TYPES_ORDER. Groups
 * themselves are returned sorted by anchor's LEGACY_TYPES_ORDER index.
 *
 * Pure. Both inputs are read-only; output is freshly allocated.
 */
export function groupPairsByAnchor(
  pairs: ReadonlyArray<readonly [string, string]>,
  prioritySet: ReadonlySet<string>,
): DualGroup[] {
  const groups = new Map<string, Set<string>>();

  for (const [t1, t2] of pairs) {
    const p1 = prioritySet.has(t1);
    const p2 = prioritySet.has(t2);

    let anchor: string;
    let partner: string;
    if (p1 && !p2) {
      anchor = t1;
      partner = t2;
    } else if (p2 && !p1) {
      anchor = t2;
      partner = t1;
    } else {
      // Both or neither in the priority set — tiebreak deterministically.
      if (byLegacyTypeOrder(t1, t2) <= 0) {
        anchor = t1;
        partner = t2;
      } else {
        anchor = t2;
        partner = t1;
      }
    }

    let bucket = groups.get(anchor);
    if (bucket == null) {
      bucket = new Set<string>();
      groups.set(anchor, bucket);
    }
    bucket.add(partner);
  }

  const result: DualGroup[] = [];
  for (const [anchor, partnerSet] of groups) {
    result.push({
      anchor,
      partners: [...partnerSet].sort(byLegacyTypeOrder),
    });
  }
  result.sort((a, b) => byLegacyTypeOrder(a.anchor, b.anchor));
  return result;
}
