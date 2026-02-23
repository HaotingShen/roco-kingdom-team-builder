import type { PersonalityOut } from "@/types";

// Personality effect fields mapping
export const EFFECT_FIELDS = [
  ["labels.hp", "hp_mod_pct"],
  ["labels.phyAtk", "phy_atk_mod_pct"],
  ["labels.magAtk", "mag_atk_mod_pct"],
  ["labels.phyDef", "phy_def_mod_pct"],
  ["labels.magDef", "mag_def_mod_pct"],
  ["labels.spd", "spd_mod_pct"],
] as const;

/**
 * Extract stat effects from a personality with translated labels
 */
export function getEffects(p: PersonalityOut, t: (k: string) => string) {
  return EFFECT_FIELDS.map(
    ([labelKey, key]) => [t(labelKey), (p as any)[key] as number] as const
  );
}

/**
 * Format personality effects as a compact row: [HP ↑, Spd ↓]
 */
export function formatRowEffects(p: PersonalityOut, t: (k: string) => string) {
  const ups = getEffects(p, t).filter(([, v]) => v > 0).map(([n]) => `${n} ↑`);
  const downs = getEffects(p, t).filter(([, v]) => v < 0).map(([n]) => `${n} ↓`);
  const items = [...ups, ...downs];
  return items.length ? `[${items.join(", ")}]` : "";
}

/**
 * Format a percentage value with sign
 */
export function pct(v: number) {
  const raw = Math.abs(v) <= 1 ? v * 100 : v;
  const rounded = Math.round(Math.abs(raw) * 10) / 10;
  return `${v > 0 ? "+" : "-"}${rounded}%`;
}

/**
 * Format personality effects as a sentence: HP +10%, Spd -5%
 */
export function formatSentenceEffects(p: PersonalityOut, t: (k: string) => string) {
  const items = getEffects(p, t).filter(([, v]) => v !== 0);
  if (!items.length) return "";
  const ordered = [
    ...items.filter(([, v]) => v > 0),
    ...items.filter(([, v]) => v < 0),
  ];
  return ordered.map(([n, v]) => `${n} ${pct(v)}`).join(", ");
}
