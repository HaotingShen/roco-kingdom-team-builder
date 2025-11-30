import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { TeamAnalysisOut, MonsterAnalysisOut, RecItem, TypeOut } from "@/types";
import { useI18n, pickName, pickFormName } from "@/i18n";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { typeIconUrl, magicItemImageUrl } from "@/lib/images";
import { MonsterImage } from "./MonsterImage";
import { formatRowEffects } from "@/lib/personality";

/* ---------------- small UI bits ---------------- */

function Dot({ color }: { color: "zinc" | "emerald" | "amber" | "red" }) {
  const map = { zinc: "bg-zinc-300", emerald: "bg-emerald-500", amber: "bg-amber-500", red: "bg-red-500" };
  return <span className={`inline-block h-2.5 w-2.5 rounded-full ${map[color]}`} />;
}

function Chip({ children, tone = "zinc" }: { children: React.ReactNode; tone?: "zinc"|"emerald"|"amber"|"red"|"blue" }) {
  const tones: Record<string, string> = {
    zinc: "border-zinc-300 bg-zinc-50 text-zinc-700",
    emerald: "border-emerald-300 bg-emerald-50 text-emerald-700",
    amber: "border-amber-300 bg-amber-50 text-amber-800",
    red: "border-red-300 bg-red-50 text-red-700",
    blue: "border-blue-300 bg-blue-50 text-blue-700",
  };
  return <span className={`inline-flex items-center gap-1 rounded-full border-2 px-2.5 py-1 text-xs font-medium shadow-sm ${tones[tone]}`}>{children}</span>;
}

function StatRow({
  label,
  value,
  max = 600,
  color = "zinc"
}: {
  label: string;
  value: number;
  max?: number;
  color?: "red" | "orange" | "purple" | "blue" | "indigo" | "yellow" | "zinc";
}) {
  const pct = Math.max(0, Math.min(100, Math.round((value / max) * 100)));

  const colorMap: Record<"red" | "orange" | "purple" | "blue" | "indigo" | "yellow" | "zinc", { gradient: string; text: string }> = {
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

  const iconColorMap: Record<string, { bg: string; border: string }> = {
    "💥": { bg: "bg-yellow-100", border: "border-yellow-400" },
    "🎲": { bg: "bg-blue-100", border: "border-blue-400" },
    "💎": { bg: "bg-purple-100", border: "border-purple-400" },
    "📋": { bg: "bg-emerald-100", border: "border-emerald-400" },
  };

  const colors = iconColorMap[icon] || { bg: "bg-zinc-100", border: "border-zinc-400" };

  return (
    <div className="rounded-lg border-2 border-zinc-200 bg-white shadow-sm overflow-hidden transition-all duration-200 hover:shadow-md">
      <button
        onClick={() => setExpanded(!expanded)}
        className={`
          w-full flex items-center justify-between px-4 py-3
          transition-all duration-200
          ${expanded ? "border-b-2 border-zinc-100" : "hover:bg-zinc-50"}
        `}
      >
        <div className="flex items-center gap-2">
          <span className="text-base">
            {icon}
          </span>

          <span className="font-semibold text-sm text-zinc-800">{title}</span>
        </div>

        <div className={`transition-all duration-200 ${expanded ? "-rotate-180" : ""}`}>
          <span className="text-base text-zinc-700">
            ▼
          </span>
        </div>
      </button>

      <div
        className="overflow-hidden transition-all duration-300 ease-in-out"
        style={{
          maxHeight: expanded ? '2000px' : '0px',
        }}
      >
        <div className="px-4 py-4 bg-gradient-to-br from-zinc-50/50 to-white border-t border-zinc-100">
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
  const [showPersonalityTooltip, setShowPersonalityTooltip] = useState(false);
  const shownTips = expanded ? tips : tips.slice(0, 1);

  const synergyNames = synergyMoveNames(data, lang);
  const personalityEffects = formatRowEffects(data.user_monster.personality, t);

  return (
    <div className="group rounded-lg border-2 border-zinc-200 bg-gradient-to-br from-white via-zinc-50/30 to-white shadow-md p-4 transition-all duration-200 hover:shadow-xl hover:-translate-y-1 hover:border-zinc-300">
      <div className="flex gap-3">
        {/* avatar */}
        <Link
          to={`/dex/monsters/${m.id}?from=builder`}
          className="shrink-0 cursor-pointer transition-transform hover:scale-105"
        >
          <MonsterImage
            monster={m}
            size={180}
            alt=""
            width={80}
            height={80}
            className="rounded-lg object-contain bg-gradient-to-r from-zinc-80 to-zinc-50 border-2 border-zinc-100 shadow-sm"
          />
        </Link>

        <div className="min-w-0 flex-1">
          <div className="font-semibold text-base truncate text-zinc-900" title={pickName(m as any, lang)}>
            {pickName(m as any, lang)}
          </div>
          {formLabel ? <div className="text-xs text-zinc-500 truncate font-medium">{formLabel}</div> : null}

          {/* types */}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {[m.main_type, m.sub_type].filter(Boolean).map((tObj) => {
              const nm = pickName(tObj as any, lang);
              const icon = typeIconUrl((tObj as any)?.name);
              return (
                <span key={nm} className="inline-flex items-center gap-1 rounded-lg bg-gradient-to-r from-zinc-100 to-zinc-50 border border-zinc-300 px-2.5 py-1 text-xs font-medium shadow-sm">
                  {icon ? <img src={icon} alt="" width={20} height={20} /> : null}
                  {nm}
                </span>
              );
            })}
          </div>

          {/* personality & legacy */}
          <div className="mt-2 flex flex-wrap gap-2">
            <span
              className="relative inline-flex items-center gap-1 rounded-lg border-2 border-blue-300 bg-gradient-to-r from-blue-50 to-blue-100 px-2.5 py-1 text-xs font-semibold text-blue-800 shadow-sm cursor-help"
              onMouseEnter={() => setShowPersonalityTooltip(true)}
              onMouseLeave={() => setShowPersonalityTooltip(false)}
              onClick={() => setShowPersonalityTooltip(!showPersonalityTooltip)}
              title={personalityEffects}
            >
              <span className="text-blue-600">{t("labels.personality")}:</span>
              {pickName(data.user_monster.personality as any, lang)}
              {showPersonalityTooltip && personalityEffects && (
                <span className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 px-2 py-1 bg-zinc-800 text-white text-xs rounded whitespace-nowrap z-10 pointer-events-none">
                  {personalityEffects}
                  <span className="absolute left-1/2 -translate-x-1/2 top-full w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-zinc-800"></span>
                </span>
              )}
            </span>
            <span className="inline-flex items-center gap-1 rounded-lg border-2 border-purple-300 bg-gradient-to-r from-purple-50 to-purple-100 px-2.5 py-1 text-xs font-semibold text-purple-800 shadow-sm">
              <span className="text-purple-600">{t("labels.legacy")}:</span>
              {(() => {
                const legacyType = data.user_monster.legacy_type;
                const typeIcon = typeIconUrl((legacyType as any)?.name, 45);
                return typeIcon ? (
                  <img src={typeIcon} alt={pickName(legacyType as any, lang)} width={20} height={20} />
                ) : (
                  pickName(legacyType as any, lang)
                );
              })()}
            </span>
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
      <div className="mt-4 pt-3 border-t-2 border-zinc-100 space-y-2">
        <div className="text-xs font-semibold text-zinc-600 mb-2">
          {t("analysis.finalStats")}
        </div>
        <StatRow label={t("labels.hp")} value={data.effective_stats.hp} max={600} color="red" />
        <StatRow label={t("labels.phyAtk")} value={data.effective_stats.phy_atk} max={400} color="orange" />
        <StatRow label={t("labels.magAtk")} value={data.effective_stats.mag_atk} max={400} color="purple" />
        <StatRow label={t("labels.phyDef")} value={data.effective_stats.phy_def} max={400} color="blue" />
        <StatRow label={t("labels.magDef")} value={data.effective_stats.mag_def} max={400} color="indigo" />
        <StatRow label={t("labels.spd")} value={data.effective_stats.spd} max={400} color="yellow" />
      </div>

      {/* synergy */}
      {synergyNames.length > 0 || tips.length > 0 ? (
        <div className="mt-4 pt-3 border-t-2 border-zinc-100 space-y-3 bg-gradient-to-br from-emerald-50/50 via-white to-emerald-50/30 -mx-4 -mb-4 px-4 py-3 rounded-b-lg">
          {synergyNames.length ? (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-emerald-500 text-white text-xs">✓</span>
                <span className="text-xs font-semibold text-emerald-800">{t("analysis.synergyWith")}:</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {synergyNames.map(n => <Chip key={n} tone="emerald">{n}</Chip>)}
              </div>
            </div>
          ) : null}

          {tips.length ? (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-blue-500 text-white text-xs">💡</span>
                <div className="text-xs font-semibold text-blue-800">{t("analysis.playTips")}</div>
              </div>
              <ul className="text-sm space-y-2">
                {shownTips.map((line, i) => (
                  <li key={i} className="leading-relaxed text-zinc-800 pl-3 border-l-2 border-blue-200">
                    {line}
                  </li>
                ))}
              </ul>
              {tips.length > 1 && (
                <button
                  onClick={() => setExpanded(e => !e)}
                  className="mt-2 text-xs text-blue-600 hover:text-blue-700 font-medium underline underline-offset-2 transition-colors"
                >
                  {expanded ? t("common.showLess") : t("common.showMore")}
                </button>
              )}
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

  // Collapsible section states
  const [teamOverviewExpanded, setTeamOverviewExpanded] = useState(true);
  const [perMonsterExpanded, setPerMonsterExpanded] = useState(true);
  const [recommendationsExpanded, setRecommendationsExpanded] = useState(true);
  const [teamSynergyExpanded, setTeamSynergyExpanded] = useState(true);

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
    <div className="space-y-6 mt-8">
      {/* Divider Header */}
      <div id="analysis-results" className="relative py-2">
        <div className="absolute inset-0 flex items-center">
          <div className="w-full border-t-4 border-emerald-600"></div>
        </div>
        <div className="relative flex justify-center">
          <span className="bg-gradient-to-r from-emerald-50 via-emerald-100 to-emerald-50 border-2 border-emerald-600 px-6 py-2.5 text-base font-bold text-emerald-800 uppercase tracking-wider shadow-md rounded-md">
            {t("analysis.title")}
          </span>
        </div>
      </div>

      {/* 1) Team overview */}
      <section className="rounded-lg border-2 border-zinc-200 bg-gradient-to-br from-white via-zinc-50 to-white shadow-lg overflow-hidden">
        {/* Header with Team Name */}
        <button
          onClick={() => setTeamOverviewExpanded(!teamOverviewExpanded)}
          className="w-full flex items-center gap-2 px-5 py-4 hover:bg-zinc-50 transition-colors border-b-2 border-zinc-100"
        >
          <div className="h-5 w-1 bg-gradient-to-b from-zinc-800 to-zinc-600 rounded-full" />
          <h2 className="text-lg font-semibold text-zinc-800">{t("analysis.teamOverview")}</h2>
          <span className="text-zinc-300 font-bold">|</span>
          <span className="text-base font-bold text-zinc-800">{analysis.team.name}</span>
          <span className={`ml-auto text-lg text-zinc-600 transition-transform ${teamOverviewExpanded ? "rotate-180" : ""}`}>▼</span>
        </button>

        {teamOverviewExpanded && (
        <div className="p-5">

        {/* Magic Item + Valid Targets */}
        <div className="mb-5 p-4 rounded-lg border-2 border-purple-200 bg-gradient-to-br from-purple-50/50 via-white to-purple-50/30 shadow-sm">
          <div className="flex items-start gap-4">
            {/* Magic Item Image */}
            <div className="shrink-0">
              <img
                src={magicItemImageUrl(analysis.team.magic_item) || ""}
                alt=""
                width={56}
                height={56}
                className="rounded-lg border-2 border-purple-200 shadow-sm bg-white"
              />
            </div>

            {/* Magic Item Info */}
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium text-purple-600 mb-1">{t("analysis.magicItem")}</div>
              <div className="text-base font-semibold text-zinc-800 mb-2">
                {pickName(analysis.team.magic_item as any, lang)}
              </div>

              {/* Valid Targets */}
              <div className="flex items-center flex-wrap gap-1.5">
                <span className="text-xs font-medium text-zinc-600">{t("analysis.magicItemTargets")}</span>
                {vtNames.length ? vtNames.map(n => (
                  <Chip key={n} tone="blue">{n}</Chip>
                )) : <span className="text-sm text-zinc-400">—</span>}
              </div>
            </div>
          </div>
        </div>

        {/* Type Coverage */}
        <div className="grid md:grid-cols-2 gap-4">
          {/* Offensive Gaps */}
          <div className="p-4 rounded-lg border-2 border-orange-200 bg-gradient-to-br from-orange-50/30 via-white to-orange-50/20">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-sm font-semibold text-zinc-800">{t("analysis.offensiveGaps")}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {analysis.type_coverage.weak_against_types?.length ? (
                analysis.type_coverage.weak_against_types.map(typeId => {
                  const typeObj = byId.get(typeId);
                  if (!typeObj) return null;
                  const typeName = pickName(typeObj as any, lang) || typeObj.name;
                  const typeIcon = typeIconUrl(typeObj.name, 45);
                  return (
                    <div key={typeId} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white border border-orange-200 shadow-sm">
                      {typeIcon && <img src={typeIcon} alt="" width={20} height={20} />}
                      <span className="text-sm font-medium text-zinc-700">{typeName}</span>
                    </div>
                  );
                })
              ) : (
                <span className="text-sm text-zinc-400">—</span>
              )}
            </div>
          </div>

          {/* Team Weak To */}
          <div className="p-4 rounded-lg border-2 border-rose-200 bg-gradient-to-br from-rose-50/30 via-white to-rose-50/20">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-sm font-semibold text-zinc-800">{t("analysis.teamWeakTo")}</span>
            </div>
            <div className="flex flex-wrap gap-2">
              {analysis.type_coverage.team_weak_to?.length ? (
                analysis.type_coverage.team_weak_to.map(typeId => {
                  const typeObj = byId.get(typeId);
                  if (!typeObj) return null;
                  const typeName = pickName(typeObj as any, lang) || typeObj.name;
                  const typeIcon = typeIconUrl(typeObj.name, 45);
                  return (
                    <div key={typeId} className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white border border-rose-200 shadow-sm">
                      {typeIcon && <img src={typeIcon} alt="" width={20} height={20} />}
                      <span className="text-sm font-medium text-zinc-700">{typeName}</span>
                    </div>
                  );
                })
              ) : (
                <span className="text-sm text-zinc-400">—</span>
              )}
            </div>
          </div>
        </div>
        </div>
        )}
      </section>

      {/* 2) Per-monster grid */}
      <section className="rounded-lg border-2 border-zinc-200 bg-gradient-to-br from-white via-zinc-50 to-white shadow-lg overflow-hidden">
        <button
          onClick={() => setPerMonsterExpanded(!perMonsterExpanded)}
          className="w-full flex items-center gap-2 px-5 py-4 hover:bg-zinc-50 transition-colors border-b-2 border-zinc-100"
        >
          <div className="h-5 w-1 bg-gradient-to-b from-zinc-800 to-zinc-600 rounded-full" />
          <h2 className="text-lg font-semibold text-zinc-800">{t("analysis.perMonster")}</h2>
          <span className={`ml-auto text-lg text-zinc-600 transition-transform ${perMonsterExpanded ? "rotate-180" : ""}`}>▼</span>
        </button>

        {perMonsterExpanded && (
        <div className="p-5">
        <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-4">
          {analysis.per_monster.map(pm => <MonsterAnalysisCard key={pm.user_monster.id} data={pm} />)}
        </div>
        </div>
        )}
      </section>

      {/* 3) Recommendations */}
      <section className="rounded-lg border-2 border-zinc-200 bg-gradient-to-br from-white via-zinc-50 to-white shadow-lg overflow-hidden">
        <button
          onClick={() => setRecommendationsExpanded(!recommendationsExpanded)}
          className="w-full flex items-center gap-2 px-5 py-4 hover:bg-zinc-50 transition-colors border-b-2 border-zinc-100"
        >
          <div className="h-5 w-1 bg-gradient-to-b from-zinc-800 to-zinc-600 rounded-full" />
          <h2 className="text-lg font-semibold text-zinc-800">{t("analysis.recommendations")}</h2>
          <span className={`ml-auto text-lg text-zinc-600 transition-transform ${recommendationsExpanded ? "rotate-180" : ""}`}>▼</span>
        </button>

        {recommendationsExpanded && (
        <div className="p-5">

        <div className="space-y-4">
          {Array.from(recGroups.entries()).map(([cat, items], idx) => (
            <div key={cat} className="rounded-lg border-2 border-zinc-200 bg-white overflow-hidden shadow-sm hover:shadow-md transition-shadow">
              <div className="bg-gradient-to-r from-zinc-50 to-white border-b-2 border-zinc-100 px-4 py-3">
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center justify-center w-6 h-6 rounded-lg bg-zinc-800 text-white text-xs font-bold">
                    {idx + 1}
                  </span>
                  <h3 className="text-sm font-semibold text-zinc-800">
                    {t(`recommendationCategories.${cat}`)}
                  </h3>
                </div>
              </div>

              <ul className="divide-y divide-zinc-100">
                {items.map((r, i) => {
                  const severityConfig = {
                    danger: {
                      border: "border-l-red-500",
                      bg: "bg-gradient-to-r from-red-50 to-white",
                      iconBg: "bg-red-500",
                      iconBorder: "border-red-600",
                      textColor: "text-red-900",
                      badgeBg: "bg-red-100",
                      badgeText: "text-red-800",
                      badgeBorder: "border-red-300",
                      icon: "!",
                    },
                    warn: {
                      border: "border-l-amber-500",
                      bg: "bg-gradient-to-r from-amber-50 to-white",
                      iconBg: "bg-amber-500",
                      iconBorder: "border-amber-600",
                      textColor: "text-amber-900",
                      badgeBg: "bg-amber-100",
                      badgeText: "text-amber-800",
                      badgeBorder: "border-amber-300",
                      icon: "⚠",
                    },
                    info: {
                      border: "border-l-blue-500",
                      bg: "bg-gradient-to-r from-blue-50 to-white",
                      iconBg: "bg-blue-500",
                      iconBorder: "border-blue-600",
                      textColor: "text-blue-900",
                      badgeBg: "bg-blue-100",
                      badgeText: "text-blue-800",
                      badgeBorder: "border-blue-300",
                      icon: "ℹ",
                    },
                  };

                  const config = severityConfig[r.severity];

                  return (
                    <li key={i} className={`border-l-4 ${config.border} ${config.bg} px-4 py-3 transition-all hover:pl-5`}>
                      <div className="flex-1 min-w-0">
                        <div className="mb-2">
                          <span className={`inline-flex items-center gap-1.5 rounded-full border-2 ${config.badgeBorder} ${config.badgeBg} px-3 py-1 text-xs font-semibold ${config.badgeText} shadow-sm`}>
                            <Dot color={severityTone(r.severity) as any} />
                            {t(`severity.${r.severity}`)}
                          </span>
                        </div>

                        <p className={`text-sm leading-relaxed ${config.textColor} font-medium`}>
                          {r.message}
                        </p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
        </div>
        )}
      </section>

      {/* 4) Team Synergy */}
      {analysis.team_synergy && (
        <section className="rounded-lg border-2 border-zinc-200 bg-gradient-to-br from-white via-zinc-50 to-white shadow-lg overflow-hidden">
          <button
            onClick={() => setTeamSynergyExpanded(!teamSynergyExpanded)}
            className="w-full flex items-center gap-2 px-5 py-4 hover:bg-zinc-50 transition-colors border-b-2 border-zinc-100"
          >
            <div className="h-5 w-1 bg-gradient-to-b from-emerald-600 to-emerald-400 rounded-full" />
            <h2 className="text-lg font-semibold text-zinc-800">{t("analysis.teamSynergy")}</h2>
            <span className={`ml-auto text-lg text-zinc-600 transition-transform ${teamSynergyExpanded ? "rotate-180" : ""}`}>▼</span>
          </button>

          {teamSynergyExpanded && (
          <div className="p-5">

          <div className="space-y-3">
            {analysis.team_synergy.key_combos.length > 0 && (
              <CollapsibleSection
                title={t("analysis.keyCombos")}
                icon="💥"
                defaultExpanded={true}
              >
                <ul className="text-sm space-y-3">
                  {analysis.team_synergy.key_combos.map((combo, i) => (
                    <li key={i} className="leading-relaxed text-zinc-800 pl-4 py-2 border-l-4 border-emerald-300 bg-gradient-to-r from-emerald-50/50 to-transparent rounded-r-md transition-all hover:border-emerald-500 hover:from-emerald-50">
                      <span className="font-medium">• {combo}</span>
                    </li>
                  ))}
                </ul>
              </CollapsibleSection>
            )}

            {analysis.team_synergy.turn_order_strategy.length > 0 && (
              <CollapsibleSection
                title={t("analysis.turnOrderStrategy")}
                icon="🎲"
                defaultExpanded={false}
              >
                <ul className="text-sm space-y-3">
                  {analysis.team_synergy.turn_order_strategy.map((strategy, i) => (
                    <li key={i} className="leading-relaxed text-zinc-800 pl-4 py-2 border-l-4 border-blue-300 bg-gradient-to-r from-blue-50/50 to-transparent rounded-r-md transition-all hover:border-blue-500 hover:from-blue-50">
                      <span className="font-medium">• {strategy}</span>
                    </li>
                  ))}
                </ul>
              </CollapsibleSection>
            )}

            {analysis.team_synergy.magic_item_usage.length > 0 && (
              <CollapsibleSection
                title={t("analysis.magicItemUsage")}
                icon="💎"
                defaultExpanded={false}
              >
                <ul className="text-sm space-y-3">
                  {analysis.team_synergy.magic_item_usage.map((usage, i) => (
                    <li key={i} className="leading-relaxed text-zinc-800 pl-4 py-2 border-l-4 border-purple-300 bg-gradient-to-r from-purple-50/50 to-transparent rounded-r-md transition-all hover:border-purple-500 hover:from-purple-50">
                      <span className="font-medium">• {usage}</span>
                    </li>
                  ))}
                </ul>
              </CollapsibleSection>
            )}

            {analysis.team_synergy.general_strategy.length > 0 && (
              <CollapsibleSection
                title={t("analysis.generalStrategy")}
                icon="📋"
                defaultExpanded={false}
              >
                <ul className="text-sm space-y-3">
                  {analysis.team_synergy.general_strategy.map((general, i) => (
                    <li key={i} className="leading-relaxed text-zinc-800 pl-4 py-2 border-l-4 border-emerald-300 bg-gradient-to-r from-emerald-50/50 to-transparent rounded-r-md transition-all hover:border-emerald-500 hover:from-emerald-50">
                      <span className="font-medium">• {general}</span>
                    </li>
                  ))}
                </ul>
              </CollapsibleSection>
            )}
          </div>
          </div>
          )}
        </section>
      )}
    </div>
  );
}