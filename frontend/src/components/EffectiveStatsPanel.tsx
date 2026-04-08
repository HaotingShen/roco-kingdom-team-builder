import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n } from "@/i18n";
import { QUERY_KEYS } from "@/lib/constants";
import { computeEffectiveHp, computeEffectiveStats } from "@/lib/effectiveStats";
import StatRow from "./StatRow";
import type { ID, MonsterOut, PersonalityOut, TalentUpsert } from "@/types";

/**
 * Reusable per-slot effective-stats panel.
 *
 * Computes the configured monster's six final stats client-side from the
 * canonical formula in `lib/effectiveStats.ts` (mirror of `compute_effective_stats`
 * in backend/main.py:391-426). Renders them as bars using the shared StatRow,
 * so the visual matches the team-analyzer view exactly.
 *
 * Self-contained: takes the parent's already-fetched monster + the slot's
 * talent + personality_id, then fetches /personalities itself via the shared
 * QUERY_KEYS.PERSONALITIES cache (no extra network call after first hit).
 */
export default function EffectiveStatsPanel({
  monster,
  talent,
  personalityId,
}: {
  monster: MonsterOut | null | undefined;
  talent: TalentUpsert;
  personalityId: ID;
}) {
  const { t } = useI18n();

  const personalitiesQ = useQuery({
    queryKey: QUERY_KEYS.PERSONALITIES,
    queryFn: () => endpoints.personalities().then((r) => r.data as PersonalityOut[]),
  });

  const personality = useMemo(
    () => personalitiesQ.data?.find((p) => p.id === personalityId),
    [personalitiesQ.data, personalityId],
  );

  const stats = useMemo(
    () =>
      monster && personality
        ? computeEffectiveStats(monster, talent, personality)
        : null,
    [monster, talent, personality],
  );

  // Card shell — same shape as MoveCoveragePanel / TypeDefensePanel for visual rhythm.
  const card = (body: React.ReactNode) => (
    <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg font-semibold text-zinc-800">{t("analysis.effectiveStats")}</span>
      </div>
      {body}
    </section>
  );

  // Loading: monster prop not yet provided OR personalities still in flight.
  if (!monster || personalitiesQ.isLoading) {
    return card(<div className="text-sm text-zinc-500">{t("common.loading")}</div>);
  }

  // Error: personalities fetch failed. Reusing the move-coverage hint key for
  // consistency with the other panels' error messaging.
  if (personalitiesQ.isError || personalitiesQ.data == null) {
    return card(<div className="text-sm text-rose-600">{t("analysis.coverageDataUnavailable")}</div>);
  }

  // Personality unset (id === 0) OR set to a stale id no longer in the list.
  // Either way, the user needs to pick (or re-pick) a personality. Don't show
  // a half-truthful "neutral" set of numbers.
  if (personalityId === 0 || !personality || !stats) {
    return card(<div className="text-sm text-zinc-500">{t("analysis.pickPersonality")}</div>);
  }

  // Effective HP against each attack type — derived from the damage formula:
  //   damage = round(45 · atk · power / (def · 50))
  // Total (atk × power) an attacker must accumulate to KO = hp × def × 50 / 45.
  // See computeEffectiveHp in lib/effectiveStats.ts for the full derivation.
  const ehpPhys = computeEffectiveHp(stats.hp, stats.phy_def);
  const ehpMag = computeEffectiveHp(stats.hp, stats.mag_def);

  // Same color palette and max values as the team-analyzer view in
  // AnalysisResults.tsx — keep them in sync if those values change there.
  return card(
    <div className="space-y-2">
      <StatRow label={t("labels.hp")}     value={stats.hp}      max={600} color="red" />
      <StatRow label={t("labels.phyAtk")} value={stats.phy_atk} max={350} color="orange" />
      <StatRow label={t("labels.magAtk")} value={stats.mag_atk} max={350} color="purple" />
      <StatRow label={t("labels.phyDef")} value={stats.phy_def} max={350} color="blue" />
      <StatRow label={t("labels.magDef")} value={stats.mag_def} max={350} color="indigo" />
      <StatRow label={t("labels.spd")}    value={stats.spd}     max={350} color="yellow" />

      {/* Effective HP summary — two derived numbers, no bars (no meaningful max). */}
      <div className="pt-3 mt-1 border-t border-zinc-100">
        <div className="text-xs font-semibold text-zinc-600 mb-2">
          {t("analysis.effectiveHp")}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex items-baseline gap-2">
            <span className="text-xs text-zinc-500">{t("analysis.vsPhysical")}</span>
            <span className="text-sm font-bold text-blue-700 tabular-nums">
              {ehpPhys.toLocaleString()}
            </span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-xs text-zinc-500">{t("analysis.vsMagic")}</span>
            <span className="text-sm font-bold text-indigo-700 tabular-nums">
              {ehpMag.toLocaleString()}
            </span>
          </div>
        </div>
      </div>
    </div>,
  );
}
