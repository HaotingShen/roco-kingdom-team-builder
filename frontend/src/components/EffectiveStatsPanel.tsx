import { useMemo, useState } from "react";
import { useI18n } from "@/i18n";
import { computeEffectiveHp, computeEffectiveStats } from "@/lib/effectiveStats";
import StatRow from "./StatRow";
import HintPopover from "./HintPopover";
import PanelCard from "./PanelCard";
import type { MonsterOut, PersonalityOut, TalentUpsert } from "@/types";

/**
 * Reusable per-slot effective-stats panel (presentational).
 *
 * Computes the configured monster's six final stats client-side from the
 * canonical formula in `lib/effectiveStats.ts` (mirror of `compute_effective_stats`
 * in backend/main.py:391-426). Renders them as bars using the shared StatRow,
 * so the visual matches the team-analyzer view exactly.
 *
 * Data flow: this panel does NO fetching. The parent (`MonsterAnalysisPage`)
 * owns the personalities query via `usePersonalities` and resolves the
 * active personality from the builder slot, then passes it in.
 *
 * `personality === null` is interpreted as the "pick a personality" empty
 * state (slot has `personality_id === 0`, or a stale id that no longer
 * maps to any row in /personalities). Loading / error states for the
 * underlying fetch are hoisted to the parent too.
 */
interface Props {
  monster: MonsterOut | null | undefined;
  talent: TalentUpsert;
  personality: PersonalityOut | null;
  initialCalcAtk?: number;
  initialCalcPower?: number;
  onCalcChange?: (atk: number, power: number) => void;
}

export default function EffectiveStatsPanel({
  monster,
  talent,
  personality,
  initialCalcAtk,
  initialCalcPower,
  onCalcChange,
}: Props) {
  const { t } = useI18n();

  const [calcAtkInput, setCalcAtkInput] = useState(String(initialCalcAtk ?? 250));
  const [calcPowerInput, setCalcPowerInput] = useState(String(initialCalcPower ?? 100));
  const [calcAtk, setCalcAtk] = useState(initialCalcAtk ?? 250);
  const [calcPower, setCalcPower] = useState(initialCalcPower ?? 100);

  const commitAtk = (raw: string) => {
    const val = Math.max(1, parseInt(raw) || 1);
    setCalcAtk(val);
    setCalcAtkInput(String(val));
    onCalcChange?.(val, calcPower);
  };
  const commitPower = (raw: string) => {
    const val = Math.max(1, parseInt(raw) || 1);
    setCalcPower(val);
    setCalcPowerInput(String(val));
    onCalcChange?.(calcAtk, val);
  };

  const stats = useMemo(
    () =>
      monster && personality
        ? computeEffectiveStats(monster, talent, personality)
        : null,
    [monster, talent, personality],
  );

  const title = t("analysis.effectiveStats");

  // Loading: monster prop not yet provided.
  if (!monster) {
    return (
      <PanelCard title={title}>
        <div className="text-sm text-zinc-500">{t("common.loading")}</div>
      </PanelCard>
    );
  }

  // Personality unresolved (id === 0 or stale). Don't show a half-truthful
  // "neutral" set of numbers — ask the user to pick one.
  if (!personality || !stats) {
    return (
      <PanelCard title={title}>
        <div className="text-sm text-zinc-500">{t("analysis.pickPersonality")}</div>
      </PanelCard>
    );
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
  return (
    <PanelCard title={title}>
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
          <div className="flex items-center gap-1.5 mb-3">
            <span className="text-sm font-semibold text-zinc-700">{t("analysis.durabilityCalc")}</span>
            <HintPopover text={t("analysis.durabilityCalcHint") ?? ""} label="i" align="left" />
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
                  value={calcAtkInput}
                  onChange={(e) => setCalcAtkInput(e.target.value)}
                  onBlur={(e) => commitAtk(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
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
                  value={calcPowerInput}
                  onChange={(e) => setCalcPowerInput(e.target.value)}
                  onBlur={(e) => commitPower(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
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
                <div className="rounded-md bg-blue-50 border border-blue-100 px-3 py-2 space-y-1.5">
                  <div className="text-xs font-semibold text-blue-600">{t("analysis.hitsToKOPhys")}</div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs text-blue-500">{t("analysis.ehpLabel")}</span>
                    <span className="text-sm font-semibold text-blue-600 tabular-nums">{ehpPhys.toLocaleString()}</span>
                    <HintPopover text={t("analysis.ehpHintPhys") ?? ""} buttonClassName="inline-flex items-center justify-center w-3.5 h-3.5 sm:w-4 sm:h-4 rounded-full border border-blue-300 bg-blue-100 text-blue-500 text-[9px] sm:text-[10px] font-bold leading-none cursor-pointer hover:bg-blue-200 hover:border-blue-400 hover:text-blue-700 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-300" />
                  </div>
                  <div className="border-t border-blue-100 pt-1.5">
                    <div className="flex flex-wrap items-baseline gap-x-1">
                      <span className="text-sm font-bold text-blue-700 tabular-nums">
                        {(t("analysis.hitsToKOResult") ?? "KO in {n} hits").replace("{n}", String(hitsPhys))}
                      </span>
                      <span className="text-sm font-bold text-blue-700 tabular-nums">
                        {(t("analysis.hitsToKOExact") ?? "exact {x} hits").replace("{x}", rawPhys.toFixed(1))}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="rounded-md bg-purple-50 border border-purple-100 px-3 py-2 space-y-1.5">
                  <div className="text-xs font-semibold text-purple-600">{t("analysis.hitsToKOMag")}</div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs text-purple-500">{t("analysis.ehpLabel")}</span>
                    <span className="text-sm font-semibold text-purple-600 tabular-nums">{ehpMag.toLocaleString()}</span>
                    <HintPopover text={t("analysis.ehpHintMag") ?? ""} buttonClassName="inline-flex items-center justify-center w-3.5 h-3.5 sm:w-4 sm:h-4 rounded-full border border-purple-300 bg-purple-100 text-purple-500 text-[9px] sm:text-[10px] font-bold leading-none cursor-pointer hover:bg-purple-200 hover:border-purple-400 hover:text-purple-700 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-300" />
                  </div>
                  <div className="border-t border-purple-100 pt-1.5">
                    <div className="flex flex-wrap items-baseline gap-x-1">
                      <span className="text-sm font-bold text-purple-700 tabular-nums">
                        {(t("analysis.hitsToKOResult") ?? "KO in {n} hits").replace("{n}", String(hitsMag))}
                      </span>
                      <span className="text-sm font-bold text-purple-700 tabular-nums">
                        {(t("analysis.hitsToKOExact") ?? "exact {x} hits").replace("{x}", rawMag.toFixed(1))}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })()}
          </div>
        </div>
      </div>
    </PanelCard>
  );
}
