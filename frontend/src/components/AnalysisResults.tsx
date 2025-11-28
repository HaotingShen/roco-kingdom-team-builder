import { useMemo, useState } from "react";
import type { TeamAnalysisOut, MonsterAnalysisOut, RecItem, TypeOut } from "@/types";
import { useI18n, pickName, pickFormName } from "@/i18n";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { typeIconUrl } from "@/lib/images";
import { MonsterImage } from "./MonsterImage";

/* ---------------- small UI bits ---------------- */

function Dot({ color }: { color: "zinc" | "emerald" | "amber" | "red" }) {
  const map = { zinc: "bg-zinc-300", emerald: "bg-emerald-500", amber: "bg-amber-500", red: "bg-red-500" };
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${map[color]}`} />;
}

function Chip({ children, tone = "zinc" }: { children: React.ReactNode; tone?: "zinc"|"emerald"|"amber"|"red"|"blue" }) {
  const tones: Record<string, string> = {
    zinc: "border-zinc-200 bg-zinc-50 text-zinc-700",
    emerald: "border-emerald-300 bg-emerald-50 text-emerald-700",
    amber: "border-amber-300 bg-amber-50 text-amber-800",
    red: "border-red-300 bg-red-50 text-red-700",
    blue: "border-blue-300 bg-blue-50 text-blue-700",
  };
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${tones[tone]}`}>{children}</span>;
}

function StatRow({ label, value, max=700 }: { label: string; value: number; max?: number }) {
  const pct = Math.max(0, Math.min(100, Math.round((value / max) * 100)));
  return (
    <div className="flex items-center gap-2">
      <div className="w-20 shrink-0 text-[11px] text-zinc-600">{label}</div>
      <div className="h-2 rounded bg-zinc-100 flex-1 overflow-hidden">
        <div className="h-full bg-zinc-800" style={{ width: `${pct}%` }} />
      </div>
      <div className="w-12 text-right text-[11px] text-zinc-600">{value}</div>
    </div>
  );
}

function CollapsibleSection({
  title,
  icon,
  count,
  defaultExpanded = false,
  children
}: {
  title: string;
  icon: string;
  count?: number;
  defaultExpanded?: boolean;
  children: React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className="border-b last:border-b-0 pb-4 last:pb-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between py-2 hover:opacity-70 transition-opacity"
      >
        <div className="flex items-center gap-2">
          <span>{icon}</span>
          <span className="font-medium text-sm">{title}</span>
          {count !== undefined && (
            <span className="text-xs text-zinc-500">({count})</span>
          )}
        </div>
        <span className="text-zinc-400 text-xs transition-transform duration-200"
              style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)' }}>
          ▶
        </span>
      </button>

      <div
        className="overflow-hidden transition-all duration-300 ease-in-out"
        style={{
          maxHeight: expanded ? '1000px' : '0px',
          opacity: expanded ? 1 : 0
        }}
      >
        <div className="pt-2 ml-4">
          {children}
        </div>
      </div>
    </div>
  );
}

function useTypesById() {
  const q = useQuery({
    queryKey: ["types-index"],
    queryFn: () => endpoints.types().then(r => r.data as TypeOut[]),
  });
  const byId = useMemo(() => {
    const m = new Map<number, TypeOut>();
    (q.data ?? []).forEach(t => m.set(t.id, t));
    return m;
  }, [q.data]);
  return { byId, isLoading: q.isLoading };
}

/* ---------------- helpers ---------------- */

function synergyMoveNames(ma: MonsterAnalysisOut, lang: "en"|"zh") {
  const idToName = new Map<number, string>([
    [ma.user_monster.move1.id, pickName(ma.user_monster.move1 as any, lang) || ma.user_monster.move1.name],
    [ma.user_monster.move2.id, pickName(ma.user_monster.move2 as any, lang) || ma.user_monster.move2.name],
    [ma.user_monster.move3.id, pickName(ma.user_monster.move3 as any, lang) || ma.user_monster.move3.name],
    [ma.user_monster.move4.id, pickName(ma.user_monster.move4 as any, lang) || ma.user_monster.move4.name],
  ]);
  const out: string[] = [];
  (ma.trait_synergies ?? []).forEach(s => s.synergy_moves.forEach(id => {
    const nm = idToName.get(id);
    if (nm && !out.includes(nm)) out.push(nm);
  }));
  return out;
}

/* ---------------- per-monster card ---------------- */

function MonsterAnalysisCard({ data }: { data: MonsterAnalysisOut }) {
  const { lang, t } = useI18n();
  const m = data.user_monster.monster;
  const formLabel = pickFormName(m as any, lang);
  const tips = (data.trait_synergies?.flatMap(s => s.recommendation) ?? []);
  const [expanded, setExpanded] = useState(false);
  const shownTips = expanded ? tips : tips.slice(0, 2);

  const synergyNames = synergyMoveNames(data, lang);

  return (
    <div className="rounded border bg-white p-3">
      <div className="flex gap-3">
        {/* avatar */}
        <div className="shrink-0">
          <MonsterImage
            monster={m}
            size={180}
            alt=""
            width={80}
            height={80}
            className="rounded-md object-contain"
          />
        </div>

        <div className="min-w-0 flex-1">
          <div className="font-medium truncate" title={pickName(m as any, lang)}>
            {pickName(m as any, lang)}
          </div>
          {formLabel ? <div className="text-xs text-zinc-500 truncate">{formLabel}</div> : null}

          {/* types */}
          <div className="mt-1 flex flex-wrap gap-1">
            {[m.main_type, m.sub_type].filter(Boolean).map((tObj) => {
              const nm = pickName(tObj as any, lang);
              const icon = typeIconUrl((tObj as any)?.name);
              return (
                <span key={nm} className="inline-flex items-center gap-1 rounded bg-zinc-100 px-2 py-0.5 text-xs">
                  {icon ? <img src={icon} alt="" width={15} height={15} /> : null}
                  {nm}
                </span>
              );
            })}
            {/* personality & legacy */}
            <Chip tone="blue">{t("builder.personality")}: {pickName(data.user_monster.personality as any, lang)}</Chip>
            <Chip tone="blue">{t("labels.legacy")}: {pickName(data.user_monster.legacy_type as any, lang)}</Chip>
          </div>

          {/* energy & counters quick badges */}
          <div className="mt-2 flex flex-wrap gap-1">
            <Chip tone="zinc">
              {t("analysis.avgEnergy")}: {data.energy_profile.avg_energy_cost.toFixed(2)}
            </Chip>
            {data.energy_profile.has_zero_cost_move ? <Chip tone="emerald">{t("analysis.hasZeroCost")}</Chip> : null}
            {data.energy_profile.has_energy_restore_move ? <Chip tone="emerald">{t("analysis.hasRestore")}</Chip> : null}
            {data.counter_coverage.total_counter_moves > 0
              ? <Chip tone="emerald">{t("analysis.counters")}: {data.counter_coverage.total_counter_moves}</Chip>
              : <Chip tone="amber">{t("analysis.noCounters")}</Chip>}
            <Chip tone="zinc">{t("analysis.defStatusCount")}: {data.defense_status_move.defense_status_move_count}</Chip>
          </div>
        </div>
      </div>

      {/* stats */}
      <div className="mt-3 space-y-1">
        <StatRow label={t("labels.hp")} value={data.effective_stats.hp} />
        <StatRow label={t("labels.phyAtk")} value={data.effective_stats.phy_atk} />
        <StatRow label={t("labels.magAtk")} value={data.effective_stats.mag_atk} />
        <StatRow label={t("labels.phyDef")} value={data.effective_stats.phy_def} />
        <StatRow label={t("labels.magDef")} value={data.effective_stats.mag_def} />
        <StatRow label={t("labels.spd")} value={data.effective_stats.spd} />
      </div>

      {/* synergy */}
      {synergyNames.length > 0 || tips.length > 0 ? (
        <div className="mt-3 border-t pt-3 space-y-2">
          {synergyNames.length ? (
            <div className="flex flex-wrap gap-1">
              <span className="text-xs text-zinc-600">{t("analysis.synergyWith")}:</span>
              {synergyNames.map(n => <Chip key={n} tone="emerald">{n}</Chip>)}
            </div>
          ) : null}

          {tips.length ? (
            <div>
              <div className="text-xs font-medium mb-1">{t("analysis.playTips")}</div>
              <ul className="text-sm space-y-1.5">
                {shownTips.map((line, i) => (
                  <li key={i} className="leading-relaxed text-zinc-800">
                    • {line}
                  </li>
                ))}
              </ul>
              {tips.length > 2 ? (
                <button
                  onClick={() => setExpanded(e => !e)}
                  className="mt-2 text-xs text-blue-600 hover:text-blue-700 underline underline-offset-2"
                >
                  {expanded ? t("common.showLess") : t("common.showMore")}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/* ---------------- recommendations ---------------- */

function severityTone(sev: RecItem["severity"]) {
  if (sev === "danger") return "red";
  if (sev === "warn") return "amber";
  return "zinc";
}

function byCategory(items: RecItem[]) {
  const map = new Map<string, RecItem[]>();
  items.forEach(r => {
    const key = r.category;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(r);
  });
  return map;
}

/* ---------------- main panel ---------------- */

export default function AnalysisResults({ analysis }: { analysis: TeamAnalysisOut }) {
  const { lang, t } = useI18n();
  const { byId } = useTypesById();

  // map valid target ids (these are user_monster ids in your response)
  const vtNames = (analysis.magic_item_eval?.valid_targets ?? [])
    .map(uid => {
      const um = analysis.team.user_monsters.find(x => x.id === uid);
      return um ? pickName(um.monster as any, lang) : `#${uid}`;
    });

  // Build readable type lists
  const typeNameList = (ids: number[]) =>
    ids.map(id => byId.get(id))
       .filter(Boolean)
       .map(t => pickName(t as any, lang) || (t as TypeOut).name);

  const recGroups = useMemo(() => byCategory(analysis.recommendations_structured ?? []), [analysis]);

  return (
    <div className="space-y-6">
      {/* 1) Team overview */}
      <section className="rounded border bg-white p-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="font-medium">{t("analysis.teamOverview")}</h2>
          <Chip tone="blue">{t("analysis.magicItem")}: {pickName(analysis.team.magic_item as any, lang)}</Chip>
        </div>

        <div className="grid md:grid-cols-3 gap-3">
          <div className="rounded border bg-white p-3">
            <div className="text-sm font-medium mb-1">{t("analysis.offensiveGaps")}</div>
            <div className="text-sm text-zinc-700">
              {analysis.type_coverage.weak_against_types?.length
                ? typeNameList(analysis.type_coverage.weak_against_types).join(", ")
                : "—"}
            </div>
          </div>

          <div className="rounded border bg-white p-3">
            <div className="text-sm font-medium mb-1">{t("analysis.teamWeakTo")}</div>
            <div className="text-sm text-zinc-700">
              {analysis.type_coverage.team_weak_to?.length
                ? typeNameList(analysis.type_coverage.team_weak_to).join(", ")
                : "—"}
            </div>
          </div>

          <div className="rounded border bg-white p-3">
            <div className="text-sm font-medium mb-1">{t("analysis.magicItemTargets")}</div>
            <div className="flex flex-wrap gap-1">
              {vtNames.length ? vtNames.map(n => <Chip key={n} tone="emerald">{n}</Chip>) : <span className="text-sm text-zinc-700">—</span>}
            </div>
          </div>
        </div>
      </section>

      {/* 2) Per-monster grid */}
      <section className="rounded border bg-white p-4">
        <h2 className="font-medium mb-3">{t("analysis.perMonster")}</h2>
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-3">
          {analysis.per_monster.map(pm => <MonsterAnalysisCard key={pm.user_monster.id} data={pm} />)}
        </div>
      </section>

      {/* 3) Recommendations */}
      <section className="rounded border bg-white p-4">
        <h2 className="font-medium mb-3">{t("analysis.recommendations")}</h2>

        {Array.from(recGroups.entries()).map(([cat, items]) => (
          <div key={cat} className="mb-3">
            <div className="text-sm font-medium mb-1">{t(`recommendationCategories.${cat}`)}</div>
            <ul className="space-y-1">
              {items.map((r, i) => (
                <li key={i} className="text-sm">
                  <Chip tone={severityTone(r.severity) as any}><Dot color={severityTone(r.severity) as any} /> {t(`severity.${r.severity}`)}</Chip>
                  <span className="ml-2">{r.message}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      {/* 4) Team Synergy */}
      {analysis.team_synergy && (
        <section className="rounded border bg-white p-4">
          <h2 className="font-medium mb-3">{t("analysis.teamSynergy")}</h2>

          <div className="space-y-0">
            {analysis.team_synergy.key_combos.length > 0 && (
              <CollapsibleSection
                title={t("analysis.keyCombos")}
                icon="⚡"
                count={analysis.team_synergy.key_combos.length}
                defaultExpanded={true}
              >
                <ul className="text-sm space-y-2">
                  {analysis.team_synergy.key_combos.map((combo, i) => (
                    <li key={i} className="leading-relaxed text-zinc-800">
                      • {combo}
                    </li>
                  ))}
                </ul>
              </CollapsibleSection>
            )}

            {analysis.team_synergy.turn_order_strategy.length > 0 && (
              <CollapsibleSection
                title={t("analysis.turnOrderStrategy")}
                icon="🔄"
                count={analysis.team_synergy.turn_order_strategy.length}
                defaultExpanded={false}
              >
                <ul className="text-sm space-y-2">
                  {analysis.team_synergy.turn_order_strategy.map((strategy, i) => (
                    <li key={i} className="leading-relaxed text-zinc-800">
                      • {strategy}
                    </li>
                  ))}
                </ul>
              </CollapsibleSection>
            )}

            {analysis.team_synergy.magic_item_usage.length > 0 && (
              <CollapsibleSection
                title={t("analysis.magicItemUsage")}
                icon="✨"
                count={analysis.team_synergy.magic_item_usage.length}
                defaultExpanded={false}
              >
                <ul className="text-sm space-y-2">
                  {analysis.team_synergy.magic_item_usage.map((usage, i) => (
                    <li key={i} className="leading-relaxed text-zinc-800">
                      • {usage}
                    </li>
                  ))}
                </ul>
              </CollapsibleSection>
            )}

            {analysis.team_synergy.general_strategy.length > 0 && (
              <CollapsibleSection
                title={t("analysis.generalStrategy")}
                icon="🎯"
                count={analysis.team_synergy.general_strategy.length}
                defaultExpanded={false}
              >
                <ul className="text-sm space-y-2">
                  {analysis.team_synergy.general_strategy.map((general, i) => (
                    <li key={i} className="leading-relaxed text-zinc-800">
                      • {general}
                    </li>
                  ))}
                </ul>
              </CollapsibleSection>
            )}
          </div>
        </section>
      )}
    </div>
  );
}