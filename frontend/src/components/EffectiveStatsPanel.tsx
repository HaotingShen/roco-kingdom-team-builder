import { useMemo, useState } from "react";
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

  const [calcAtk, setCalcAtk] = useState(250);
  const [calcPower, setCalcPower] = useState(100);

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

  // Derive per-stat personality indicators from the mod_pct fields.
  const ind = (pct: number): "up" | "down" | null =>
    pct > 0 ? "up" : pct < 0 ? "down" : null;

  // Same color palette and max values as the team-analyzer view in
  // AnalysisResults.tsx — keep them in sync if those values change there.
  return card(
    <div className="space-y-2">
      <div className="w-full sm:w-4/5 mx-auto space-y-2">
        <StatRow label={t("labels.hp")}     value={stats.hp}      max={600} color="red"    indicator={ind(personality.hp_mod_pct)} />
        <StatRow label={t("labels.phyAtk")} value={stats.phy_atk} max={350} color="orange" indicator={ind(personality.phy_atk_mod_pct)} />
        <StatRow label={t("labels.magAtk")} value={stats.mag_atk} max={350} color="purple" indicator={ind(personality.mag_atk_mod_pct)} />
        <StatRow label={t("labels.phyDef")} value={stats.phy_def} max={350} color="blue"   indicator={ind(personality.phy_def_mod_pct)} />
        <StatRow label={t("labels.magDef")} value={stats.mag_def} max={350} color="indigo" indicator={ind(personality.mag_def_mod_pct)} />
        <StatRow label={t("labels.spd")}    value={stats.spd}     max={350} color="yellow" indicator={ind(personality.spd_mod_pct)} />
      </div>

      {/* Durability calculator — shows raw EHP and derives hits-to-KO from user-supplied attacker params. */}
      <div className="pt-3 mt-1 border-t border-zinc-100">
        <div className="text-sm font-semibold text-zinc-700 mb-3">
          {t("analysis.durabilityCalc")}
        </div>
        <div className="w-full sm:w-4/5 mx-auto">

        {/* Attacker parameter inputs */}
        <div className="flex items-start gap-2 mb-3">
          <div className="flex flex-col gap-1 flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-zinc-700 shrink-0">{t("analysis.atkStatLabel")}</label>
              <input
                type="number"
                min={1}
                max={9999}
                value={calcAtk}
                onChange={(e) => setCalcAtk(Math.max(1, parseInt(e.target.value) || 1))}
                className="flex-1 min-w-0 h-8 px-2 text-sm text-center font-semibold border border-zinc-300 rounded-md focus:outline-none focus:ring-1 focus:ring-zinc-400 tabular-nums"
              />
            </div>
            <span className="text-xs text-zinc-500 leading-tight">{t("analysis.atkStatNote")}</span>
          </div>

          <div className="flex-none h-8 flex items-center px-1 text-zinc-400 font-medium text-base select-none">×</div>

          <div className="flex flex-col gap-1 flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-zinc-700 shrink-0">{t("analysis.movePowerLabel")}</label>
              <input
                type="number"
                min={1}
                max={9999}
                value={calcPower}
                onChange={(e) => setCalcPower(Math.max(1, parseInt(e.target.value) || 1))}
                className="flex-1 min-w-0 h-8 px-2 text-sm text-center font-semibold border border-zinc-300 rounded-md focus:outline-none focus:ring-1 focus:ring-zinc-400 tabular-nums"
              />
            </div>
            <span className="text-xs text-zinc-500 leading-tight">{t("analysis.movePowerNote")}</span>
          </div>
        </div>

        {/* Output cards — EHP shown as base, hits-to-KO derived from inputs above */}
        {(() => {
          const product = calcAtk * calcPower;
          const rawPhys = ehpPhys / product;
          const rawMag = ehpMag / product;
          const hitsPhys = Math.floor(rawPhys);
          const hitsMag = Math.floor(rawMag);
          return (
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-md bg-blue-50 border border-blue-100 px-3 py-2 space-y-1">
                <div className="text-xs text-blue-500 font-medium">{t("analysis.hitsToKOPhys")}</div>
                <div className="flex items-baseline gap-1.5 flex-wrap">
                  <span className="text-xs text-blue-400">{t("analysis.ehpLabel")}</span>
                  <span className="text-xs font-semibold text-blue-600 tabular-nums">{ehpPhys.toLocaleString()}</span>
                </div>
                <div className="text-sm font-bold text-blue-700 tabular-nums">
                  {(t("analysis.hitsToKOResult") ?? "KO in {n} hits").replace("{n}", String(hitsPhys))}
                </div>
                <div className="text-xs text-blue-400 tabular-nums">
                  {(t("analysis.hitsToKOExact") ?? "exact {x} hits").replace("{x}", rawPhys.toFixed(1))}
                </div>
              </div>
              <div className="rounded-md bg-indigo-50 border border-indigo-100 px-3 py-2 space-y-1">
                <div className="text-xs text-indigo-500 font-medium">{t("analysis.hitsToKOMag")}</div>
                <div className="flex items-baseline gap-1.5 flex-wrap">
                  <span className="text-xs text-indigo-400">{t("analysis.ehpLabel")}</span>
                  <span className="text-xs font-semibold text-indigo-600 tabular-nums">{ehpMag.toLocaleString()}</span>
                </div>
                <div className="text-sm font-bold text-indigo-700 tabular-nums">
                  {(t("analysis.hitsToKOResult") ?? "KO in {n} hits").replace("{n}", String(hitsMag))}
                </div>
                <div className="text-xs text-indigo-400 tabular-nums">
                  {(t("analysis.hitsToKOExact") ?? "exact {x} hits").replace("{x}", rawMag.toFixed(1))}
                </div>
              </div>
            </div>
          );
        })()}
        </div>
      </div>
    </div>,
  );
}
