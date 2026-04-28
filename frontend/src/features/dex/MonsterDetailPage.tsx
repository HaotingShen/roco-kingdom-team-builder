import { Link, useParams, useSearchParams, useNavigate } from "react-router-dom";
import { useEffect, useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n, pickName, pickDesc, pickFormName } from "@/i18n";
import { useSeoMeta } from "@/hooks/useSeoMeta";
import type { TypeOut, MoveOut, MonsterOut, StatKey } from "@/types";
import { STAT_KEYS } from "@/types";
import { typeIconUrl, monsterImageFallbackChain, monsterPlaceholder, moveSubIconUrl, moveIconUrlFromCn } from "@/lib/images";
import { useMonsterNavigation } from "./useMonsterNavigation";
import { QUERY_KEYS, LEGACY_TYPES_ORDER } from "@/lib/constants";
import { normalizeMoveCategory } from "@/lib/typeEffectiveness";
import { buildDexForwardQuery } from "@/lib/dexNavigation";
import EvolutionTree from "./EvolutionTree";
import RichDescription from "@/components/RichDescription";
import TypeDefensePanel from "@/components/TypeDefensePanel";

/* ---------- helpers ---------- */

export function extractStats(m: MonsterOut): Record<StatKey, number> {
  return {
    hp:      m.base_hp ?? 0,
    phy_atk: m.base_phy_atk ?? 0,
    mag_atk: m.base_mag_atk ?? 0,
    phy_def: m.base_phy_def ?? 0,
    mag_def: m.base_mag_def ?? 0,
    spd:     m.base_spd ?? 0,
  };
}

/* If legacy moves come as ids, fetch details via /moves?ids=1,2,3  */
function useMoveObjects(list: any[] | undefined) {
  const ids = Array.isArray(list)
    ? list.map((x) => (typeof x === "number" ? x : (x?.id ?? x?.move_id))).filter(Boolean)
    : [];
  const needFetch =
    Array.isArray(list) &&
    list.length > 0 &&
    (typeof list[0] === "number" || !!(list[0] as any)?.move_id);
  const q = useQuery({
    queryKey: QUERY_KEYS.MOVES_BY_IDS(ids.join(",")),
    queryFn: () => endpoints.moves({ ids: ids.join(",") }).then((r) => r.data?.items ?? r.data),
    enabled: needFetch && ids.length > 0,
  });
  if (needFetch) return q.data ?? [];
  return list ?? [];
}

export default function MonsterDetailPage() {
  const { id } = useParams();
  const [sp] = useSearchParams();
  const fromTab = sp.get("tab") || "monsters";
  const movesParam = sp.get("moves");
  const which = movesParam === "legacy" ? "legacy" : movesParam === "stones" ? "stones" : "pool";
  const fromParam = sp.get("from");
  const fromBuilder = fromParam === "builder";
  // "analyze" mode: launched from MonsterAnalysisPage via MonsterInspector.
  // Carries the originating slot index so the back link can return to
  // /build/analyze/:slot. Only accept strict non-negative integers — any
  // other value is treated as a malformed URL, and the page falls back to
  // the bare dex behaviour (back button labelled + targeted as "Back to
  // Dex" rather than mismatching between label and target).
  const fromAnalyze = fromParam === "analyze";
  const analyzeSlotRaw = fromAnalyze ? sp.get("slot") : null;
  const analyzeSlot: string | undefined =
    analyzeSlotRaw !== null && /^\d+$/.test(analyzeSlotRaw)
      ? analyzeSlotRaw
      : undefined;
  const hasAnalyzeReturn = fromAnalyze && analyzeSlot !== undefined;

  const backRaw = sp.get("back"); // decoded full dex URL (e.g. /dex?tab=monsters&sort=base_spd)
  const dexUrl = backRaw ?? `/dex?tab=${fromTab}`;
  // Forward params: carry back (or tab fallback) + any from=... context
  // through all in-page navigation (moves tab switcher, evolution tree links).
  const forwardQuery = buildDexForwardQuery({
    backRaw,
    fromTab,
    fromBuilder,
    fromAnalyze: hasAnalyzeReturn,
    analyzeSlot,
  });

  // Back-link target + label derived from ONE flag (hasAnalyzeReturn) so the
  // two can't disagree on a malformed URL. See lib/dexNavigation for the
  // matching forward-query logic.
  const backTo = hasAnalyzeReturn
    ? `/build/analyze/${analyzeSlot}`
    : fromBuilder
    ? "/build"
    : dexUrl;
  const backLabelKey = hasAnalyzeReturn
    ? "dex.backToMonsterAnalysis"
    : fromBuilder
    ? "dex.backToBuilder"
    : "dex.backToDex";
  const { lang, t } = useI18n();
  const navigate = useNavigate();

  const [formDropdownOpen, setFormDropdownOpen] = useState(false);

  const q = useQuery({
    queryKey: ["monster", id],
    queryFn: () => endpoints.monsterById(id!).then((r) => r.data),
    enabled: !!id,
  });

  const m = q.data;
  const monsterName = m ? pickName(m, lang) : "";
  useSeoMeta({
    title: monsterName
      ? lang === "zh" ? `${monsterName} | 洛手配队器` : `${monsterName} | RK Team Builder`
      : lang === "zh" ? "精灵详情 | 洛手配队器" : "Jingling Detail | RK Team Builder",
    description: monsterName
      ? lang === "zh"
        ? `${monsterName} 的数值、招式、特性和进化 — 洛克王国: 世界。`
        : `${monsterName} — stats, moves, traits, and evolution for Roco Kingdom: World.`
      : lang === "zh"
        ? "查看精灵的数值、招式、特性和进化。"
        : "View jingling stats, moves, traits, and evolution for Roco Kingdom: World.",
    canonicalPath: id ? `/dex/monsters/${id}` : "/dex",
  });

  // Fetch all forms of the same species (for leader form selection)
  const allForms = useQuery({
    queryKey: ["monster-forms", m?.name],
    queryFn: async () => {
      if (!m?.name) return [];
      const response = await endpoints.monsters({ name: m.name });
      const items = response.data?.items ?? response.data ?? [];
      // Filter to only leader forms of this monster
      return items.filter((item: any) =>
        item.is_leader_form === true &&
        (pickName(item, lang) || item.name) === (pickName(m, lang) || m.name)
      );
    },
    enabled: !!m && m.is_leader_form === true,
  });

  const leaderForms = (allForms.data ?? []) as any[];
  const hasMultipleForms = leaderForms.length > 1;

  // Use smart navigation to skip monster forms
  const { prevMonsterId, nextMonsterId, isLoadingPrev, isLoadingNext } =
    useMonsterNavigation(m, lang);

  useEffect(() => { window.scrollTo(0, 0); }, [id]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (!target.closest('[data-form-dropdown]')) {
        setFormDropdownOpen(false);
      }
    };

    if (formDropdownOpen) {
      document.addEventListener('click', handleClickOutside);
      return () => document.removeEventListener('click', handleClickOutside);
    }
  }, [formDropdownOpen]);

  const nm = pickName(m as any, lang) || m?.name;
  const fm = pickFormName(m as any, lang);
  // Don't show form in title for leader monsters with multiple forms
  const showFormInTitle = !(m?.is_leader_form && hasMultipleForms);
  const title = showFormInTitle && fm ? `${nm} (${fm})` : nm;

  const trait = m?.trait || m?.ability || null;

  const baseStats = extractStats(m || {});
  const total = STAT_KEYS.reduce<number>((s, k) => s + (baseStats[k] ?? 0), 0);

  const movePool = useMoveObjects(m?.move_pool);
  const moveStones = useMoveObjects(m?.move_stones);
  const legacyMovesRaw = useMoveObjects(m?.legacy_moves);

  // Fetch types for sorting legacy moves
  const typesQ = useQuery({
    queryKey: QUERY_KEYS.TYPES,
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
  });

  // Sort legacy moves by LEGACY_TYPES_ORDER
  const legacyMoves = useMemo(() => {
    if (!typesQ.data || !legacyMovesRaw || legacyMovesRaw.length === 0) {
      return legacyMovesRaw;
    }

    // Create a map from type_id to type_name
    const typeIdToName = new Map<number, string>();
    typesQ.data.forEach(type => {
      typeIdToName.set(type.id, type.name);
    });

    // Sort legacy moves based on their type's position in LEGACY_TYPES_ORDER
    return [...legacyMovesRaw].sort((a, b) => {
      const typeA = (a as any).move_type || (a as any).type;
      const typeB = (b as any).move_type || (b as any).type;

      const nameA = typeA?.name || typeIdToName.get(typeA?.id) || "";
      const nameB = typeB?.name || typeIdToName.get(typeB?.id) || "";

      const indexA = LEGACY_TYPES_ORDER.indexOf(nameA as any);
      const indexB = LEGACY_TYPES_ORDER.indexOf(nameB as any);

      // If not found in order, put at end
      return (indexA === -1 ? 999 : indexA) - (indexB === -1 ? 999 : indexB);
    });
  }, [legacyMovesRaw, typesQ.data]);

  // Image fallback chain for leader form handling
  const fallbackChain = m ? monsterImageFallbackChain(m, 360) : [];
  const mainImageSrc = fallbackChain[0] || monsterPlaceholder;

  if (q.isLoading) return <div>{t("common.loading")}</div>;
  if (!q.data) return <div>Not found.</div>;

  return (
    <div className="space-y-3">
      <div className="flex items-center">
        <Link
          to={backTo}
          className="inline-flex items-center gap-1 text-sm font-medium rounded-lg border border-zinc-300 bg-white px-4 py-2 shadow-sm hover:bg-zinc-50 hover:border-zinc-400 hover:shadow transition-all duration-200"
        >
          <span aria-hidden className="text-xl leading-none text-zinc-600 -translate-y-[1px]">←</span>
          <span className="text-zinc-700">{t(backLabelKey)}</span>
        </Link>
      </div>

      {/* Top monster info */}
      <section className="rounded-lg border border-zinc-200 bg-white shadow-sm overflow-hidden">
        <div className="grid grid-cols-1 lg:grid-cols-2">
          {/* Left: name, types, image on gradient - vertically centered */}
          <div className="relative p-6 bg-gradient-to-br from-zinc-50 via-white to-zinc-50 flex flex-col justify-center items-center gap-4 min-h-[320px]">
            {/* Previous Monster Button */}
            {prevMonsterId !== null && (
              <Link
                to={`/dex/monsters/${prevMonsterId}?${forwardQuery}`}
                className="absolute left-2 top-1/2 -translate-y-1/2 inline-flex items-center justify-center w-10 h-10 rounded-full bg-white border border-zinc-300 shadow-md hover:bg-zinc-50 hover:border-zinc-400 hover:shadow-lg transition-all duration-200 text-zinc-600 hover:text-zinc-900"
                aria-label="Previous jingling"
              >
                <span className="text-3xl leading-none -translate-y-[3px]">‹</span>
              </Link>
            )}

            {/* Loading spinner while searching for previous */}
            {isLoadingPrev && (
              <div className="absolute left-2 top-1/2 -translate-y-1/2 inline-flex items-center justify-center w-10 h-10">
                <div className="animate-spin h-4 w-4 border-2 border-zinc-300 border-t-zinc-600 rounded-full" />
              </div>
            )}

            {/* Next Monster Button */}
            {nextMonsterId !== null && (
              <Link
                to={`/dex/monsters/${nextMonsterId}?${forwardQuery}`}
                className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center justify-center w-10 h-10 rounded-full bg-white border border-zinc-300 shadow-md hover:bg-zinc-50 hover:border-zinc-400 hover:shadow-lg transition-all duration-200 text-zinc-600 hover:text-zinc-900"
                aria-label="Next jingling"
              >
                <span className="text-3xl leading-none -translate-y-[3px]">›</span>
              </Link>
            )}

            {/* Loading spinner while searching for next */}
            {isLoadingNext && (
              <div className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center justify-center w-10 h-10">
                <div className="animate-spin h-4 w-4 border-2 border-zinc-300 border-t-zinc-600 rounded-full" />
              </div>
            )}

            <div className="text-center space-y-2">
              <h1 className="text-2xl font-bold text-zinc-800">{title}</h1>

              {/* Leader Evolution Source Dropdown - Shows which form this leader evolved from */}
              {m?.is_leader_form && hasMultipleForms && (
                <div className="relative inline-block mt-1" data-form-dropdown>
                  <button
                    onClick={() => setFormDropdownOpen(!formDropdownOpen)}
                    className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded-lg border-2 border-amber-400 bg-amber-50 text-amber-800 hover:bg-amber-100 hover:border-amber-500 transition-all focus:outline-none focus:ring-2 focus:ring-amber-400 cursor-pointer"
                  >
                    {/* Evolution icon */}
                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M7 17L17 7M17 7H7M17 7V17" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>

                    {/* Label and current form */}
                    <span className="text-xs opacity-75">
                      {t("dex.evolvedFrom")}:
                    </span>
                    <span className="font-semibold">
                      {pickFormName(m as any, lang) || m?.form || "—"}
                    </span>

                    {/* Dropdown arrow */}
                    <svg
                      className={`w-4 h-4 transition-transform ${formDropdownOpen ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {/* Dropdown menu */}
                  {formDropdownOpen && (
                    <div className="absolute left-0 mt-2 min-w-full rounded-lg border-2 border-amber-300 bg-white shadow-lg z-10">
                      <div className="max-h-60 overflow-y-auto p-1">
                        {leaderForms
                          .sort((a, b) => (a as any).id - (b as any).id)
                          .map((form) => {
                            const formName = pickFormName(form as any, lang) || (form as any).form;
                            const isActive = (form as any).id === m?.id;

                            return (
                              <button
                                key={(form as any).id}
                                onClick={() => {
                                  navigate(`/dex/monsters/${(form as any).id}?${forwardQuery}`);
                                  setFormDropdownOpen(false);
                                }}
                                className={`
                                  w-full text-left px-3 py-2 rounded-md text-sm transition-all cursor-pointer
                                  ${isActive
                                    ? 'bg-amber-100 text-amber-900 font-semibold border-l-4 border-amber-500'
                                    : 'text-zinc-700 hover:bg-zinc-50 hover:text-zinc-900'
                                  }
                                `}
                              >
                                <div className="flex items-center gap-2">
                                  {isActive && (
                                    <svg className="w-4 h-4 text-amber-600" fill="currentColor" viewBox="0 0 20 20">
                                      <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                                    </svg>
                                  )}
                                  <span>{formName}</span>
                                </div>
                              </button>
                            );
                          })}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div className="flex items-center justify-center gap-2">
                {[m.main_type, m.sub_type].filter(Boolean).map((tp: TypeOut) => (
                  <span key={tp.id} className="inline-flex items-center gap-1 rounded-full bg-white border border-zinc-200 text-sm px-3 py-1 shadow-sm">
                    {typeIconUrl(tp.name, 30) ? <img src={typeIconUrl(tp.name, 30)!} alt="" width={22} height={22} /> : null}
                    <span className="font-medium text-zinc-700">{pickName(tp as any, lang)}</span>
                  </span>
                ))}
                {m.is_leader_form && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 text-amber-800 text-sm px-3 py-1 shadow-sm">
                    <span className="font-medium">{t("labels.leader")}</span>
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center justify-center">
              <img
                src={mainImageSrc}
                alt=""
                width={360}
                height={360}
                className="h-[200px] w-[200px] object-contain drop-shadow-md hover:scale-105 transition-transform duration-200"
                data-fallback-step="0"
                onError={(e) => {
                  const img = e.currentTarget as HTMLImageElement;
                  const step = Number(img.dataset.fallbackStep || "0");
                  const next = step + 1;
                  if (next < fallbackChain.length) {
                    img.dataset.fallbackStep = String(next);
                    img.src = fallbackChain[next]!;
                  } else if (img.src !== monsterPlaceholder) {
                    img.src = monsterPlaceholder;
                  }
                }}
              />
            </div>
          </div>

          {/* Right: stat bars + trait */}
          <div className="p-6 bg-white border-l border-zinc-100">
            <div className="space-y-4">
              {/* Base Stats */}
              <div>
                <div className="flex items-center gap-3 mb-3">
                  <span className="text-sm font-semibold text-zinc-700">{t("dex.totalBase")}</span>
                  <span className="text-lg font-bold text-zinc-800 bg-zinc-200 px-3 py-1 rounded-full">
                    {total}
                  </span>
                </div>
                <div className="space-y-2">
                  {STAT_KEYS.map((k) => {
                    const labels: Record<StatKey, string> = {
                      hp: t("labels.hp"),
                      phy_atk: t("labels.phyAtk"),
                      mag_atk: t("labels.magAtk"),
                      phy_def: t("labels.phyDef"),
                      mag_def: t("labels.magDef"),
                      spd: t("labels.spd"),
                    };
                    const colors: Record<StatKey, string> = {
                      hp: "bg-red-500",
                      phy_atk: "bg-orange-500",
                      mag_atk: "bg-purple-500",
                      phy_def: "bg-blue-500",
                      mag_def: "bg-indigo-500",
                      spd: "bg-yellow-500",
                    };
                    const val = baseStats[k] ?? 0;
                    const pct = Math.min(100, Math.round((val / 200) * 100));
                    return (
                      <div key={k} className="flex items-center gap-3">
                        <div className="w-12 text-xs font-medium text-zinc-600">{labels[k]}</div>
                        <div className="flex-1 h-3 rounded-full bg-zinc-100 overflow-hidden shadow-inner">
                          <div className={`h-full ${colors[k]} transition-all duration-300`} style={{ width: `${pct}%` }} />
                        </div>
                        <div className="w-10 text-right text-sm font-semibold text-zinc-700 tabular-nums">{val}</div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Trait */}
              {trait ? (
                <div className="pt-4 border-t border-zinc-200">
                  <div className="bg-gradient-to-br from-amber-50 to-orange-50 rounded-lg border border-amber-200 p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-amber-400 text-white text-xs font-bold shadow-sm leading-none">
                        <span className="translate-x-[0.5px] -translate-y-[0.5px]">★</span>
                      </span>
                      <span className="font-semibold text-amber-900">
                        {pickName(trait as any, lang) || trait.name}
                      </span>
                    </div>
                    <div className="text-sm text-amber-800 leading-relaxed">
                      <RichDescription text={pickDesc(trait as any, lang) || trait.description || ""} />
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      {/* Type Defense (defender matchups) */}
      <TypeDefensePanel monster={m} />

      {/* Evolution chain */}
      {m?.evolution_tree && m.evolution_tree.stages && m.evolution_tree.stages.length > 1 ? (
        <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-lg font-semibold text-zinc-800">
              {t("dex.evolutionChain")}
            </span>
            {m.evolution_tree.total_unique_monsters > 1 && (
              <span className="text-sm text-zinc-500">
                ({m.evolution_tree.max_depth + 1} {t("dex.stages")})
              </span>
            )}
          </div>
          <EvolutionTree
            treeData={m.evolution_tree}
            currentMonsterId={m.id}
            fromTab={fromTab}
            fromBuilder={fromBuilder}
            fromAnalyze={hasAnalyzeReturn}
            analyzeSlot={analyzeSlot}
            back={backRaw ?? undefined}
          />
        </section>
      ) : null}

      {/* Moves */}
      <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4">
        {/* Tab Switcher */}
        <div className="flex items-center justify-center mb-4">
          <div className="inline-flex items-center gap-1 p-1 rounded-full bg-zinc-100 shadow-inner">
            <Link
              to={`?${forwardQuery}&moves=pool`}
              className={`
                inline-flex items-center justify-center h-9 px-6 rounded-full text-sm font-medium
                transition-all duration-200 ease-in-out
                ${which === "pool"
                  ? "bg-white text-zinc-900 shadow-md"
                  : "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-50"
                }
              `}
            >
              {t("dex.learnable")}
            </Link>
            <Link
              to={`?${forwardQuery}&moves=stones`}
              className={`
                inline-flex items-center justify-center h-9 px-6 rounded-full text-sm font-medium
                transition-all duration-200 ease-in-out
                ${which === "stones"
                  ? "bg-white text-zinc-900 shadow-md"
                  : "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-50"
                }
              `}
            >
              {t("dex.move_stones")}
            </Link>
            <Link
              to={`?${forwardQuery}&moves=legacy`}
              className={`
                inline-flex items-center justify-center h-9 px-6 rounded-full text-sm font-medium
                transition-all duration-200 ease-in-out
                ${which === "legacy"
                  ? "bg-white text-zinc-900 shadow-md"
                  : "text-zinc-600 hover:text-zinc-900 hover:bg-zinc-50"
                }
              `}
            >
              {t("dex.legacy")}
            </Link>
          </div>
        </div>
        <MovesList
          list={which === "legacy" ? legacyMoves : which === "stones" ? moveStones : movePool}
          backUrl={`/dex/monsters/${id}?${forwardQuery}&moves=${which}`}
        />
      </section>
    </div>
  );
}

function MovesList({ list, backUrl }: { list: any[]; backUrl: string }) {
  const { lang, t } = useI18n();

  // Show warning if no moves available
  if (!list || list.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-amber-100 mb-4">
          <span className="inline-block text-3xl translate-y-[-5px]">⚠️</span>
        </div>
        <div className="text-lg font-semibold text-zinc-800 mb-2">
          {t("dex.noMovesAvailable")}
        </div>
        <div className="text-sm text-zinc-600">
          {t("dex.noMovesExplanation")}
        </div>
      </div>
    );
  }

  // Type color mapping for 19 types
  const typeColors: Record<string, string> = {
    normal: "border-l-slate-500",
    grass: "border-l-green-400",
    fire: "border-l-orange-600",
    water: "border-l-blue-500",
    light: "border-l-cyan-400",
    ground: "border-l-yellow-600",
    ice: "border-l-sky-500",
    dragon: "border-l-rose-500",
    electric: "border-l-yellow-400",
    poison: "border-l-purple-400",
    bug: "border-l-lime-400",
    fighting: "border-l-orange-400",
    flying: "border-l-teal-400",
    cute: "border-l-pink-400",
    ghost: "border-l-violet-500",
    dark: "border-l-pink-600",
    mechanical: "border-l-emerald-400",
    illusion: "border-l-indigo-300",
    leader: "border-l-zinc-400",
  };

  return (
    <div className="grid gap-3 grid-cols-1 moves-md:grid-cols-2 moves-lg:grid-cols-3">
      {(list ?? []).map((m: MoveOut & any) => {
        const tp = (m.move_type || m.type) as TypeOut | null;
        const cname = pickName(m as any, lang) || m.name;
        const desc = pickDesc(m as any, lang) || m.localized?.[lang]?.description || m.description || "";
        const normalizedCategory = normalizeMoveCategory(m.move_category || m.category || "");
        const energy = (m.energy_cost ?? m.energy ?? null);
        const power = m.power ?? null;
        const isDef = normalizedCategory === "DEFENSE";
        const isSta = normalizedCategory === "STATUS";

        const moveNameZh = pickName(m as any, "zh") || cname;
        const moveImg = moveIconUrlFromCn(moveNameZh);
        const typeImg = tp?.name ? typeIconUrl(tp.name, 30) : null;
        const energyImg = moveSubIconUrl("energy.png");
        const catToFile: Record<string, string> = {
          PHY_ATTACK: "physical-attack",
          MAG_ATTACK: "magic-attack",
          DEFENSE: "defense",
          STATUS: "status",
        };
        const catImg = moveSubIconUrl(`${catToFile[normalizedCategory] ?? "physical-attack"}.png`);

        // Get type color class, fallback to zinc if type not found
        // Convert type name to lowercase to match our mapping
        const typeName = tp?.name?.toLowerCase() || "";
        const typeColorClass = typeName ? (typeColors[typeName] || "border-l-zinc-400") : "border-l-zinc-400";

        return (
          <Link
            key={m.id}
            to={`/dex/moves/${m.id}?back=${encodeURIComponent(backUrl)}`}
            className={`
              block rounded-lg border border-zinc-200 bg-white p-3 shadow-sm
              border-l-4 ${typeColorClass}
              transition-all duration-200
              hover:shadow-md hover:-translate-y-0.5
            `}
          >
            <div
              className="
                grid
                grid-cols-[70px_minmax(0,1fr)_40px_8px_50px_4px]
                sm:grid-cols-[80px_minmax(0,1fr)_40px_12px_50px_4px]
                md:grid-cols-[80px_minmax(0,1fr)_40px_20px_50px_8px]
                lg:grid-cols-[80px_minmax(0,1fr)_40px_28px_50px_12px]
                grid-rows-[auto_auto]
                items-start
                gap-2
                text-[13px] sm:text-sm
              "
            >
              {/* Image (spans both rows) */}
              <div className="row-[1/3] self-center h-[70px] w-[70px] sm:h-[80px] sm:w-[80px] rounded bg-zinc-100/60 overflow-hidden flex items-center justify-center">
                <img
                  src={moveImg}
                  alt={cname}
                  width={80}
                  height={80}
                  className="h-full w-full object-contain"
                  loading="lazy"
                  onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none'; }}
                />
              </div>

              {/* Type icon + Move name (col 2) */}
              <div className="col-[2] self-center min-w-0">
                <div className="flex items-center gap-1 min-w-0">
                  {typeImg ? (
                    <img
                      src={typeImg}
                      alt=""
                      aria-hidden="true"
                      width={30}
                      height={30}
                      className="block shrink-0"
                    />
                  ) : null}
                  <div className="font-medium whitespace-normal break-words min-w-0">
                    {cname}
                  </div>
                </div>
              </div>

              {/* Energy icon + value (col 3) */}
              <div className="col-[3] self-center flex items-center justify-end gap-[6px]">
                <img src={energyImg} alt="" aria-hidden="true" width={15} height={15} />
                <span className="w-8 text-[13px] sm:text-xs text-left tabular-nums">{energy ?? "—"}</span>
              </div>

              {/* (col 4 is the spacer) */}

              {/* Category icon + power/label (col 5) */}
              <div className="col-[5] self-center flex items-center justify-end gap-x-[6px]">
                <img src={catImg} alt="" aria-hidden="true" width={15} height={15} />
                <span className="w-10 text-[13px] sm:text-xs text-left tabular-nums">
                  {isDef ? t("dex.defense") : isSta ? t("dex.status") : (power ?? "—")}
                </span>
              </div>

              {/* (col 6 is the end spacer) */}

              {/* Description (row 2, spans full width from col 2 to end) */}
              <div className="row-[2/3] col-[2/-1] text-[13px] sm:text-sm text-zinc-600 pl-1">
                <RichDescription text={desc} />
              </div>
            </div>
          </Link>
        );
      })}
      {!list?.length && <div className="text-zinc-500">{t("dex.noResults")}</div>}
    </div>
  );
}