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
}: {
  label: string;
  value: number;
  max?: number;
  color?: StatRowColor;
}) {
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

  return (
    <div className="flex items-center gap-2 group">
      <div className="w-20 shrink-0 text-xs font-semibold text-zinc-700">{label}</div>
      <div className="h-3 rounded-full bg-zinc-100 flex-1 overflow-hidden shadow-inner border border-zinc-200">
        <div
          className={`h-full bg-gradient-to-r ${colors.gradient} shadow-sm transition-all duration-300 group-hover:shadow-md`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className={`w-14 text-right text-xs font-bold ${colors.text} tabular-nums`}>
        {value}
      </div>
    </div>
  );
}
