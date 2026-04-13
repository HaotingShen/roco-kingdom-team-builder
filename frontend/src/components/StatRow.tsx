/**
 * Single labelled stat bar with a coloured gradient and a numeric readout.
 *
 * Used by both the team-wide AnalysisResults (final stats from the backend
 * analyzer) and the per-slot EffectiveStatsPanel (final stats computed
 * client-side from the canonical formula). Sharing the same component keeps
 * the two views visually identical so users don't see drift between them.
 *
 * Extracted from AnalysisResults.tsx (was a local function there). Behavior
 * is verbatim — same colorMap, same percentage clamping, same defaults.
 */

import { useI18n } from "@/i18n";

export type StatRowColor =
  | "red"
  | "orange"
  | "purple"
  | "blue"
  | "indigo"
  | "yellow"
  | "zinc";

export default function StatRow({
  label,
  value,
  max = 600,
  color = "zinc",
  indicator,
}: {
  label: string;
  value: number;
  max?: number;
  color?: StatRowColor;
  /**
   * Personality modifier indicator shown between the bar and the value.
   * - "up"   → green ▲ (stat boosted by personality)
   * - "down" → red ▼ (stat reduced by personality)
   * - null   → reserved empty slot (keeps rows aligned when some stats are neutral)
   * - undefined (prop omitted) → no slot rendered at all (default; preserves layout
   *   for existing usages like AnalysisResults that don't pass this prop)
   */
  indicator?: "up" | "down" | null;
}) {
  const { lang } = useI18n();
  const pct = Math.max(0, Math.min(100, Math.round((value / max) * 100)));

  const colorMap: Record<StatRowColor, { gradient: string; text: string }> = {
    red: { gradient: "from-red-400 via-red-500 to-red-600", text: "text-red-700" },
    orange: { gradient: "from-orange-400 via-orange-500 to-orange-600", text: "text-orange-700" },
    purple: { gradient: "from-purple-400 via-purple-500 to-purple-600", text: "text-purple-700" },
    blue: { gradient: "from-blue-400 via-blue-500 to-blue-600", text: "text-blue-700" },
    indigo: { gradient: "from-indigo-400 via-indigo-500 to-indigo-600", text: "text-indigo-700" },
    yellow: { gradient: "from-yellow-400 via-yellow-500 to-yellow-600", text: "text-yellow-700" },
    zinc: { gradient: "from-zinc-700 via-zinc-800 to-zinc-900", text: "text-zinc-700" },
  };

  const colors = colorMap[color];

  // When indicator slot is present: use explicit per-element margins for
  // asymmetric gaps (label→bar tight, bar→arrow normal, arrow→value tight).
  // When no indicator (AnalysisResults etc): keep the original uniform gap-2.
  const compact = indicator !== undefined;

  return (
    <div className={`flex items-center group ${compact ? "" : "gap-2"}`}>
      <span className={`shrink-0 text-xs font-semibold text-zinc-700 ${lang === "en" ? "min-w-12" : ""} ${compact ? "mr-4" : ""}`}>{label}</span>
      <div className="h-3 rounded-full bg-zinc-100 flex-1 overflow-hidden shadow-inner border border-zinc-200">
        <div
          className={`h-full bg-gradient-to-r ${colors.gradient} shadow-sm transition-all duration-300 group-hover:shadow-md`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {compact && (
        <div className="w-4 shrink-0 flex items-center justify-center ml-2">
          {indicator === "up"   && <span className="text-sm font-bold leading-none text-emerald-500">▲</span>}
          {indicator === "down" && <span className="text-sm font-bold leading-none text-rose-500">▼</span>}
        </div>
      )}
      <span className={`w-7 shrink-0 text-xs font-bold ${colors.text} tabular-nums ${compact ? "ml-2" : "text-right"}`}>
        {value}
      </span>
    </div>
  );
}
