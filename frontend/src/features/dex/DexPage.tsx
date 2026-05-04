import { useMemo, useState, useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { endpoints } from "@/lib/api";
import { useI18n, pickName, pickDesc, pickFormName } from "@/i18n";
import type { MonsterLiteOut, MoveOut, TypeOut, MagicItemOut, GameTermOut } from "@/types";
import PageTabs from "@/components/PageTabs";
import useDebounce from "@/hooks/useDebounce";
import { useSeoMeta } from "@/hooks/useSeoMeta";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useWindowVirtualizer } from "@tanstack/react-virtual";
import { typeIconUrl, magicItemImageUrl, monsterImageFallbackChain, monsterPlaceholder, magicItemPlaceholder, moveIconUrlFromCn, moveSubIconUrl } from "@/lib/images";
import { QUERY_KEYS } from "@/lib/constants";
import RichDescription from "@/components/RichDescription";

/* ---------------- helpers ---------------- */

function useColumns(kind: "monsters" | "moves") {
  const [w, setW] = useState<number>(() => (typeof window !== "undefined" ? window.innerWidth : 1024));
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const onR = () => {
      clearTimeout(timer);
      timer = setTimeout(() => setW(window.innerWidth), 150);
    };
    window.addEventListener("resize", onR);
    return () => { window.removeEventListener("resize", onR); clearTimeout(timer); };
  }, []);
  if (kind === "monsters") {
    // matches: 2 / 2(sm) / 3(lg) / 5(xl)
    return w >= 1280 ? 5 : w >= 1024 ? 3 : 2;
  }
  // moves: 1 / 2(800px) / 3(1400px)
  return w >= 1400 ? 3 : w >= 800 ? 2 : 1;
}

/* ---------------- tiny UI atoms ---------------- */

function FilterButton({
  active,
  onClick,
  children,
  className = "",
}: {
  active?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`
        inline-flex h-9 items-center px-3 rounded-full text-sm font-medium cursor-pointer
        transition-all duration-200
        ${active
          ? "bg-zinc-800 text-white shadow-md hover:bg-zinc-700"
          : "bg-white border border-zinc-300 text-zinc-700 hover:bg-zinc-50 hover:border-zinc-400"
        }
        ${className}
      `}
    >
      {children}
    </button>
  );
}

function Pill({
  children,
  tone = "zinc",
}: {
  children: React.ReactNode;
  tone?: "zinc" | "blue" | "amber" | "emerald" | "red";
}) {
  const styles: Record<string, string> = {
    zinc: "border-zinc-200 bg-zinc-50 text-zinc-700",
    blue: "border-blue-300 bg-blue-50 text-blue-700",
    amber: "border-amber-300 bg-amber-50 text-amber-800",
    emerald: "border-emerald-300 bg-emerald-50 text-emerald-700",
    red: "border-red-300 bg-red-50 text-red-700",
  };
  return (
    <span className={`inline-flex h-7 items-center gap-0.5 rounded-full border px-2 text-xs ${styles[tone]}`}>
      {children}
    </span>
  );
}

const MONSTER_SORT_OPTIONS = [
  { key: "base_hp",      labelKey: "labels.hp" },
  { key: "base_phy_atk", labelKey: "labels.phyAtk" },
  { key: "base_mag_atk", labelKey: "labels.magAtk" },
  { key: "base_phy_def", labelKey: "labels.phyDef" },
  { key: "base_mag_def", labelKey: "labels.magDef" },
  { key: "base_spd",     labelKey: "labels.spd" },
] as const;

const VALID_MOVE_SORT_KEYS = ["energy_cost", "power"] as const;
type MoveSortKey = typeof VALID_MOVE_SORT_KEYS[number];

const MOVE_SORT_OPTIONS = [
  { key: "energy_cost" as MoveSortKey, labelKey: "dex.sort_energy" },
  { key: "power"       as MoveSortKey, labelKey: "dex.sort_power" },
] as const;

/* ===========================================================
   Monsters tab
   =========================================================== */

const VALID_FORM_VARIANTS = ["all", "regional", "highest", "leader"] as const;
type FormVariant = typeof VALID_FORM_VARIANTS[number];

function MonstersTab() {
  const { lang, t } = useI18n();
  const [sp, setSp] = useSearchParams();
  // keep state in URL so returning to the page restores filters
  const [q, setQ] = useState(sp.get("q") ?? "");
  const dq = useDebounce(q, 200);
  const [selectedTypes, setSelectedTypes] = useState<number[]>(
    () => (sp.get("types")?.split(",").map(Number).filter(Boolean) ?? [])
  );
  const [filterVariant, setFilterVariant] = useState<FormVariant>(() => {
    const f = sp.get("form") as FormVariant;
    return VALID_FORM_VARIANTS.includes(f) ? f : "all";
  });
  const validSortKeys = ["base_hp","base_phy_atk","base_mag_atk","base_phy_def","base_mag_def","base_spd"];
  const [sortStat, setSortStat] = useState<string | null>(() => {
    const s = sp.get("sort");
    return s && validSortKeys.includes(s) ? s : null;
  });
  const [sortDir, setSortDir] = useState<"desc" | "asc">(() =>
    sp.get("dir") === "asc" ? "asc" : "desc"
  );
  const [sortOpen, setSortOpen] = useState(false);
  const sortRef = useRef<HTMLDivElement>(null);

  const types = useQuery<TypeOut[]>({
    queryKey: ["types-all"],
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
  });

  const monsters = useQuery<MonsterLiteOut[]>({
    queryKey: ["dex-monsters"],
    queryFn: () => endpoints.monsters().then((r) => (r.data?.items ?? r.data) as MonsterLiteOut[]),
  });

  // Compute highest (final) non-leader evolution IDs once per data fetch.
  // A monster is "highest form" if no other non-leader monster evolves from it.
  const highestFormIds = useMemo(() => {
    const list = monsters.data ?? [];
    const evolvedFromSet = new Set<number>();
    list.forEach((m) => {
      if (!m.is_leader_form && m.evolves_from_id != null) {
        evolvedFromSet.add(m.evolves_from_id);
      }
    });
    return new Set(
      list.filter((m) => !m.is_leader_form && !evolvedFromSet.has(m.id)).map((m) => m.id)
    );
  }, [monsters.data]);

  const filtered = useMemo(() => {
    const list = monsters.data ?? [];
    const keywords = dq.trim().toLowerCase();

    return list.filter((m) => {
      // type filter (AND across selected types)
      if (selectedTypes.length) {
        const ids = [m.main_type?.id, m.sub_type?.id].filter(Boolean) as number[];
        const hit = selectedTypes.every((id) => ids.includes(id));
        if (!hit) return false;
      }
      // form filters
      if (filterVariant === "regional" && (m.is_leader_form || !m.form || m.form.toLowerCase() === "default")) return false;
      if (filterVariant === "highest" && !highestFormIds.has(m.id)) return false;
      if (filterVariant === "leader" && !m.is_leader_form) return false;

      // local search – SUPPORT EN & 中文 regardless of current UI language
      if (!keywords) return true;
      const nameEN = (pickName(m as any, "en") || m.name || "").toLowerCase();
      const nameZH = (pickName(m as any, "zh") || "").toLowerCase();
      const formEN = (pickFormName(m as any, "en") || "").toLowerCase();
      const formZH = (pickFormName(m as any, "zh") || "").toLowerCase();
      const mainEN = (pickName(m.main_type as any, "en") || m.main_type?.name || "").toLowerCase();
      const mainZH = (pickName(m.main_type as any, "zh") || "").toLowerCase();
      const subEN  = (pickName(m.sub_type as any, "en") || m.sub_type?.name || "").toLowerCase();
      const subZH  = (pickName(m.sub_type as any, "zh") || "").toLowerCase();
      const leaderEN = m.is_leader_form ? "leader" : "";
      const leaderZH = m.is_leader_form ? "首领" : "";
      const hay = [nameEN, nameZH, formEN, formZH, mainEN, mainZH, subEN, subZH, leaderEN, leaderZH].join(" ");
      return hay.includes(keywords);
    });
  }, [monsters.data, dq, selectedTypes, filterVariant, highestFormIds]);

  // Always group leader forms by monster name to show only one card per species
  const displayList = useMemo(() => {
    // Group leader forms, keep only the form with lowest ID (first documented)
    const grouped = new Map<string, MonsterLiteOut>();
    const nonLeaders: MonsterLiteOut[] = [];

    filtered.forEach((m) => {
      if (m.is_leader_form) {
        const name = pickName(m as any, lang) || m.name;
        const existing = grouped.get(name);

        if (!existing || (m as any).id < (existing as any).id) {
          grouped.set(name, m);
        }
      } else {
        nonLeaders.push(m);
      }
    });

    // Combine grouped leaders with non-leaders, maintaining original order
    const groupedLeaders = Array.from(grouped.values());
    const combined = [...nonLeaders, ...groupedLeaders];

    if (sortStat) {
      return combined.sort((a, b) => {
        const aVal: number | null = (a as any)[sortStat] ?? null;
        const bVal: number | null = (b as any)[sortStat] ?? null;
        if (aVal === null && bVal === null) return (a.name || "").localeCompare(b.name || "");
        if (aVal === null) return 1;
        if (bVal === null) return -1;
        const diff = sortDir === "desc" ? bVal - aVal : aVal - bVal;
        return diff !== 0 ? diff : (a.name || "").localeCompare(b.name || "");
      });
    }
    return combined.sort((a, b) => (a as any).id - (b as any).id);
  }, [filtered, lang, sortStat, sortDir]);

  const toggleType = (id: number) =>
    setSelectedTypes((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  // --- virtualization (treat each grid *row* as one virtual item) ---
  const cols = useColumns("monsters");
  const rowCount = Math.ceil((displayList?.length ?? 0) / cols);
  const rowEstimate = 220; // ~ card + gaps
  const rowVirt = useWindowVirtualizer({
    count: rowCount,
    estimateSize: () => rowEstimate,
    overscan: 6,
    measureElement: (el: HTMLElement) => el.getBoundingClientRect().height,
  });
  const vis = rowVirt.getVirtualItems();
  const firstVis = vis[0];
  const lastVis = vis.length ? vis[vis.length - 1] : undefined;
  const topPad = firstVis?.start ?? 0;
  const bottomPad = lastVis ? Math.max(0, rowVirt.getTotalSize() - lastVis.end) : 0;

  // keep URL in sync
  useEffect(() => {
    const next = new URLSearchParams(sp);
    q ? next.set("q", q) : next.delete("q");
    selectedTypes.length ? next.set("types", selectedTypes.join(",")) : next.delete("types");
    filterVariant !== "all" ? next.set("form", filterVariant) : next.delete("form");
    sortStat ? next.set("sort", sortStat) : next.delete("sort");
    sortStat && sortDir === "asc" ? next.set("dir", "asc") : next.delete("dir");
    setSp(next, { replace: true });
  }, [q, selectedTypes, filterVariant, sortStat, sortDir]); // eslint-disable-line react-hooks/exhaustive-deps

  // restore scroll position when returning from a monster detail page
  useEffect(() => {
    const saved = sessionStorage.getItem("dex_monster_scroll");
    if (!saved) return;
    const y = Number(saved);
    let id2: number;
    // Remove the key inside the rAF so that App.tsx's effect (which runs after this
    // child effect) still sees the key and skips its own window.scrollTo(0,0).
    const id1 = requestAnimationFrame(() => {
      id2 = requestAnimationFrame(() => {
        sessionStorage.removeItem("dex_monster_scroll");
        window.scrollTo({ top: y, behavior: "instant" });
      });
    });
    return () => { cancelAnimationFrame(id1); cancelAnimationFrame(id2); };
  }, []);

  // close sort dropdown on outside click (mobile)
  useEffect(() => {
    if (!sortOpen) return;
    const handle = (e: MouseEvent) => {
      if (sortRef.current && !sortRef.current.contains(e.target as Node)) {
        setSortOpen(false);
      }
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [sortOpen]);

  // full dex URL to pass as "back" param to monster detail page
  const dexReturnParams = new URLSearchParams(sp);
  dexReturnParams.set("tab", "monsters");
  const dexReturnUrl = `/dex?${dexReturnParams.toString()}`;

  return (
    <div className="space-y-3">
      {/* Filters */}
      <div className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4 space-y-4">
        <div className="flex items-center gap-2">
          <div className="relative flex-1 sm:flex-none">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("dex.search")}
              className="h-10 w-full sm:w-[220px] rounded-lg border border-zinc-300 pl-4 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400 focus:border-transparent transition-all"
            />
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 text-lg">🔍</span>
          </div>
          {/* Sort dropdown — mobile only */}
          <div className="relative sm:hidden" ref={sortRef}>
            <button
              onClick={() => setSortOpen((v) => !v)}
              className={`h-10 px-3 rounded-lg border text-sm font-medium inline-flex items-center gap-1.5 transition-all ${
                sortStat
                  ? "bg-zinc-800 text-white border-zinc-800"
                  : "bg-white text-zinc-700 border-zinc-300 hover:border-zinc-400"
              }`}
            >
              <span>↑↓</span>
              <span>{t("dex.sortLabelMobile")}</span>
            </button>
            {sortOpen && (
              <div className="absolute right-0 top-full mt-1 z-50 bg-white border border-zinc-200 rounded-lg shadow-lg overflow-hidden min-w-[140px]">
                {MONSTER_SORT_OPTIONS.map((opt) => {
                  const isActive = sortStat === opt.key;
                  const label = t(opt.labelKey);
                  return (
                    <div
                      key={opt.key}
                      className={`flex items-center justify-between px-3 ${isActive ? "py-2 bg-zinc-100" : "py-3"}`}
                    >
                      <button
                        className={`flex-1 text-left text-sm ${isActive ? "font-semibold text-zinc-900" : "text-zinc-700"}`}
                        onClick={() => {
                          if (isActive) { setSortStat(null); setSortDir("desc"); }
                          else { setSortStat(opt.key); setSortDir("desc"); }
                        }}
                      >
                        {label}
                      </button>
                      {isActive && (
                        <button
                          className="ml-2 w-8 h-8 flex items-center justify-center rounded text-zinc-700 hover:bg-zinc-200 text-base"
                          onClick={() => setSortDir((d) => d === "desc" ? "asc" : "desc")}
                        >
                          {sortDir === "desc" ? "↓" : "↑"}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div className="grid gap-y-3 gap-x-4 grid-cols-1 sm:[grid-template-columns:max-content_1fr]">
          <div className="text-sm font-semibold text-zinc-500 uppercase tracking-wide sm:text-zinc-700 sm:normal-case sm:tracking-normal sm:self-center sm:text-center">{t("dex.typesLabel")}</div>
          <div className="flex flex-wrap gap-2">
            <FilterButton
              active={selectedTypes.length === 0}
              onClick={() => setSelectedTypes([])}
            >
              {t("dex.form_all")}
            </FilterButton>
            {(types.data ?? [])
              .filter((tp) => tp.name.toLowerCase() !== "leader" && (tp.localized?.zh ?? "") !== "首领")
              .map((tp) => (
              <FilterButton
                key={tp.id}
                active={selectedTypes.includes(tp.id)}
                onClick={() => toggleType(tp.id)}
              >
                <span className="inline-flex items-center gap-0.5">
                  {typeIconUrl(tp.name, 30) ? (
                    <img src={typeIconUrl(tp.name, 30)!} alt="" width={22} height={22} />
                  ) : null}
                  {pickName(tp as any, lang) || tp.name}
                </span>
              </FilterButton>
            ))}
          </div>

          <div className="text-sm font-semibold text-zinc-500 uppercase tracking-wide sm:text-zinc-700 sm:normal-case sm:tracking-normal sm:self-center sm:text-center mt-2 sm:mt-0">{t("dex.formsLabel")}</div>
          <div className="flex flex-wrap items-center gap-2">
            <FilterButton active={filterVariant === "all"} onClick={() => setFilterVariant("all")}>
              {t("dex.form_all")}
            </FilterButton>
            <FilterButton active={filterVariant === "regional"} onClick={() => setFilterVariant("regional")}>
              {t("dex.form_regional")}
            </FilterButton>
            <FilterButton active={filterVariant === "highest"} onClick={() => setFilterVariant("highest")}>
              {t("dex.form_highest")}
            </FilterButton>
            <FilterButton active={filterVariant === "leader"} onClick={() => setFilterVariant("leader")}>
              {t("dex.form_leader")}
            </FilterButton>
          </div>

          {/* Sort row — desktop only, inside same grid for column alignment */}
          <div className="hidden sm:block text-sm font-semibold text-zinc-700 self-center text-center">{t("dex.sortLabel")}</div>
          <div className="hidden sm:flex flex-wrap gap-2">
            {MONSTER_SORT_OPTIONS.map((opt) => {
              const isActive = sortStat === opt.key;
              const label = t(opt.labelKey);
              if (isActive) {
                return (
                  <div key={opt.key} className="inline-flex h-9 items-center rounded-full bg-zinc-800 text-white shadow-md text-sm font-medium overflow-hidden">
                    <button
                      className="pl-3 pr-1.5 h-full hover:bg-zinc-700 transition-colors"
                      onClick={() => { setSortStat(null); setSortDir("desc"); }}
                    >
                      {label}
                    </button>
                    <button
                      className="pr-3 pl-1 h-full hover:bg-zinc-700 transition-colors"
                      onClick={() => setSortDir((d) => d === "desc" ? "asc" : "desc")}
                    >
                      {sortDir === "desc" ? "↓" : "↑"}
                    </button>
                  </div>
                );
              }
              return (
                <FilterButton key={opt.key} active={false} onClick={() => { setSortStat(opt.key); setSortDir("desc"); }}>
                  {label}
                </FilterButton>
              );
            })}
          </div>
        </div>
      </div>

      {/* Virtualized grid (window-based) */}
      {monsters.isLoading ? (
        <div className="text-zinc-500">{t("common.loading")}</div>
      ) : !displayList.length ? (
        <div className="text-zinc-500">{t("dex.noResults")}</div>
      ) : (
        <div style={{ height: rowVirt.getTotalSize() + 90, position: "relative" }}>
          <div style={{ height: topPad }} />
          {vis.map((vi) => {
            const rowIndex = vi.index;
            const start = rowIndex * cols;
            const end = Math.min(displayList.length, start + cols);
            const rowMonsters = displayList.slice(start, end);
            return (
              <div
                key={(vi as any).key ?? rowIndex}
                ref={rowVirt.measureElement}
                data-index={vi.index}
                className="mb-3"
              >
                <div className="grid gap-3 grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
                  {rowMonsters.map((m) => {
                    const titleName = pickName(m as any, lang) || m.name;
                    const formLabel = m.is_leader_form ? "" : pickFormName(m as any, lang);
                    const title = [titleName, formLabel ? `(${formLabel})` : ""].filter(Boolean).join(" ");
                    const fallbackChain = monsterImageFallbackChain(m, 360);
                    const src = fallbackChain[0] || monsterPlaceholder;
                    return (
                      <Link
                        key={m.id}
                        to={`/dex/monsters/${m.id}?back=${encodeURIComponent(dexReturnUrl)}`}
                        onClick={() => sessionStorage.setItem("dex_monster_scroll", String(window.scrollY))}
                        className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400"
                      >
                        <div className="text-sm font-semibold truncate text-zinc-800" title={title}>{title}</div>
                        <div className="mt-3 flex items-center justify-center">
                          <img
                            src={src}
                            alt=""
                            width={360}
                            height={360}
                            className="h-[120px] w-[120px] object-contain drop-shadow-sm"
                            loading="lazy"
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
                        <div className="mt-3 flex items-center gap-1 flex-wrap">
                          {[m.main_type, m.sub_type].filter(Boolean).map((tp) => (
                            <Pill key={(tp as TypeOut).id}>
                              {typeIconUrl((tp as TypeOut).name, 30) ? (
                                <img src={typeIconUrl((tp as TypeOut).name, 30)!} alt="" width={20} height={20} />
                              ) : null}
                              {pickName(tp as any, lang)}
                            </Pill>
                          ))}
                          {m.is_leader_form ? <Pill tone="amber">{t("labels.leader")}</Pill> : null}
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </div>
            );
          })}
          <div style={{ height: bottomPad }} />
          <div style={{ height: 24 }} />
        </div>
      )}
    </div>
  );
}

/* ===========================================================
   Moves tab  (UPDATED: Plan B + padding spacers) + "Other" type for universal moves
   =========================================================== */

type LocalMove = MoveOut & {
  move_type?: TypeOut | null;  // BE sometimes uses move_type/type
  type?: TypeOut | null;
  move_category?: string;      // ATTACK/DEFENSE/STATUS/PHY_ATTACK/MAG_ATTACK
  category?: string;
  energy_cost?: number | null;
  energy?: number | null;      // be liberal in what we accept
  power?: number | null;
  description?: string | null;
  localized?: any;
};

// Normalize backend category values to frontend enum keys
function normalizeMoveCategory(category: string): string {
  const upper = category.toUpperCase();
  // Map backend enum values to frontend enum keys
  if (upper === "PHYSICAL ATTACK") return "PHY_ATTACK";
  if (upper === "MAGIC ATTACK") return "MAG_ATTACK";
  return upper; // DEFENSE, STATUS already match
}

function MovesTab() {
  const { lang, t } = useI18n();
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useState(sp.get("mq") ?? "");
  const dq = useDebounce(q, 200);
  // Special handling for "Other" type filter (stored as string "OTHER" instead of numeric ID)
  const [typeId, setTypeId] = useState<number | string | null>(() => {
    const v = sp.get("mtype");
    if (!v) return null;
    return v === "OTHER" ? "OTHER" : Number(v);
  });
  const [cat, setCat] = useState<string | null>(sp.get("mcat") ?? null);
  const [moveSortStat, setMoveSortStat] = useState<MoveSortKey | null>(() => {
    const s = sp.get("msort") as MoveSortKey;
    return VALID_MOVE_SORT_KEYS.includes(s) ? s : null;
  });
  const [moveSortDir, setMoveSortDir] = useState<"asc" | "desc">(() =>
    sp.get("mdir") === "asc" ? "asc" : "desc"
  );
  const [moveSortOpen, setMoveSortOpen] = useState(false);
  const moveSortRef = useRef<HTMLDivElement>(null);

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

  const types = useQuery<TypeOut[]>({
    queryKey: ["types-all"],
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
  });

  const moves = useQuery<LocalMove[]>({
    queryKey: ["dex-moves"],
    queryFn: () => endpoints.moves().then((r) => (r.data?.items ?? r.data) as LocalMove[]),
  });

  // Pre-seed individual move cache so MoveDetailPage renders instantly (no skeleton)
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!moves.data) return;
    moves.data.forEach((m) => {
      queryClient.setQueryData(["move", String(m.id)], m);
    });
  }, [moves.data, queryClient]);

  // Define special "Other" type moves (universal moves for all monsters)
  const otherTypeMoves = useMemo(() => new Set(["Focus", "focus", "聚能", "Willpower Impact", "willpower impact", "愿力冲击"]), []);

  const filtered = useMemo(() => {
    const list = moves.data ?? [];
    const kw = dq.trim().toLowerCase();

    // Helper to check if a move is in the "Other" type
    const isOtherTypeMove = (m: LocalMove): boolean => {
      const nameEN = (pickName(m as any, "en") || m.name || "").toLowerCase();
      const nameZH = (pickName(m as any, "zh") || "").toLowerCase();
      return otherTypeMoves.has(m.name) || otherTypeMoves.has(nameEN) || otherTypeMoves.has(nameZH);
    };

    // Helper to check if a move is "Willpower Impact"
    const isWillpowerImpact = (m: LocalMove): boolean => {
      const nameEN = (pickName(m as any, "en") || m.name || "").toLowerCase();
      const nameZH = (pickName(m as any, "zh") || "").toLowerCase();
      return m.name === "Willpower Impact" || nameEN === "willpower impact" || nameZH === "愿力冲击";
    };

    return list.filter((m) => {
      const isOtherType = isOtherTypeMove(m);

      // Move Type filtering
      if (typeId === "OTHER") {
        // Only show "Other" type moves
        if (!isOtherType) return false;
      } else if (typeId !== null) {
        // Regular type filtering - only show moves with the exact type
        const tp = (m.move_type || m.type) as TypeOut | null;
        if (!tp || tp.id !== typeId) {
          // Not a match for the selected type - filter it out
          return false;
        }
      }

      // Category filtering with special handling for "Willpower Impact"
      if (cat) {
        const normalizedCat = normalizeMoveCategory(m.move_category || m.category || "");
        const isWillpower = isWillpowerImpact(m);

        // "Willpower Impact" should appear in BOTH Physical and Magical filters
        if (isWillpower && (cat === "PHY_ATTACK" || cat === "MAG_ATTACK")) {
          // Allow it through for both physical and magical categories
        } else if (normalizedCat !== cat) {
          return false;
        }
      }

      if (!kw) return true;

      // names/descriptions — SUPPORT EN & 中文
      const nmEN = (pickName(m as any, "en") || m.name || "").toLowerCase();
      const nmZH = (pickName(m as any, "zh") || "").toLowerCase();
      const descEN = (m.localized?.en?.description ?? m.description ?? "").toLowerCase();
      const descZH = (m.localized?.zh?.description ?? "").toLowerCase();
      return [nmEN, nmZH, descEN, descZH].some((s) => s.includes(kw));
    });
  }, [moves.data, dq, typeId, cat, otherTypeMoves]);

  // Sort filtered moves — nulls always last regardless of direction
  const displayList = useMemo(() => {
    if (!moveSortStat) return filtered;
    return [...filtered].sort((a, b) => {
      const aVal = moveSortStat === "energy_cost"
        ? (a.energy_cost ?? a.energy ?? null)
        : (a.power ?? null);
      const bVal = moveSortStat === "energy_cost"
        ? (b.energy_cost ?? b.energy ?? null)
        : (b.power ?? null);
      if (aVal === null && bVal === null) return (pickName(a as any, "en") || a.name || "").localeCompare(pickName(b as any, "en") || b.name || "");
      if (aVal === null) return 1;
      if (bVal === null) return -1;
      const diff = moveSortDir === "desc" ? bVal - aVal : aVal - bVal;
      return diff !== 0 ? diff : (pickName(a as any, "en") || a.name || "").localeCompare(pickName(b as any, "en") || b.name || "");
    });
  }, [filtered, moveSortStat, moveSortDir]);

  const catOptions = [
    { key: "PHY_ATTACK", label: t("dex.cat_phy") },
    { key: "MAG_ATTACK", label: t("dex.cat_mag") },
    { key: "DEFENSE", label: t("dex.cat_def") },
    { key: "STATUS", label: t("dex.cat_sta") },
  ];

  // --- virtualization for moves grid (measureElement + padding spacers) ---
  const cols = useColumns("moves");
  const rowCount = Math.ceil((displayList?.length ?? 0) / cols);
  const rowEstimate = 180;

  const rowVirt = useWindowVirtualizer({
    count: rowCount,
    estimateSize: () => rowEstimate,
    overscan: 6,
    // dynamic measure real row height
    measureElement: (el: HTMLElement) => el.getBoundingClientRect().height,
  });

  // convenience
  const vis = rowVirt.getVirtualItems();

  const first = vis[0];
  const last  = vis.length ? vis[vis.length - 1] : undefined;

  const topPad = first?.start ?? 0;
  const bottomPad = last ? Math.max(0, rowVirt.getTotalSize() - last.end) : 0;

  // sync URL
  useEffect(() => {
    const next = new URLSearchParams(sp);
    q ? next.set("mq", q) : next.delete("mq");
    typeId !== null ? next.set("mtype", String(typeId)) : next.delete("mtype");
    cat ? next.set("mcat", cat) : next.delete("mcat");
    moveSortStat ? next.set("msort", moveSortStat) : next.delete("msort");
    moveSortStat && moveSortDir === "asc" ? next.set("mdir", "asc") : next.delete("mdir");
    setSp(next, { replace: true });
  }, [q, typeId, cat, moveSortStat, moveSortDir]); // eslint-disable-line react-hooks/exhaustive-deps

  // close sort dropdown on outside click (mobile)
  useEffect(() => {
    if (!moveSortOpen) return;
    const handle = (e: MouseEvent) => {
      if (moveSortRef.current && !moveSortRef.current.contains(e.target as Node)) {
        setMoveSortOpen(false);
      }
    };
    document.addEventListener("mousedown", handle);
    return () => document.removeEventListener("mousedown", handle);
  }, [moveSortOpen]);

  // restore scroll position when returning from a move detail page
  useEffect(() => {
    const saved = sessionStorage.getItem("dex_move_scroll");
    if (!saved) return;
    const y = Number(saved);
    let id2: number;
    const id1 = requestAnimationFrame(() => {
      id2 = requestAnimationFrame(() => {
        sessionStorage.removeItem("dex_move_scroll");
        window.scrollTo({ top: y, behavior: "instant" });
      });
    });
    return () => { cancelAnimationFrame(id1); cancelAnimationFrame(id2); };
  }, []);

  // full dex URL to pass as "back" param to move detail page
  const dexReturnParams = new URLSearchParams(sp);
  dexReturnParams.set("tab", "moves");
  const dexReturnUrl = `/dex?${dexReturnParams.toString()}`;

  return (
    <div className="space-y-3">
      {/* Filters */}
      <div className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4 space-y-4">
        <div className="flex items-center gap-2">
          <div className="relative flex-1 sm:flex-none">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("dex.search")}
              className="h-10 w-full sm:w-[220px] rounded-lg border border-zinc-300 pl-4 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400 focus:border-transparent transition-all"
            />
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 text-lg">🔍</span>
          </div>
          {/* Sort dropdown — mobile only */}
          <div className="relative sm:hidden" ref={moveSortRef}>
            <button
              onClick={() => setMoveSortOpen((v) => !v)}
              className={`h-10 px-3 rounded-lg border text-sm font-medium inline-flex items-center gap-1.5 transition-all ${
                moveSortStat
                  ? "bg-zinc-800 text-white border-zinc-800"
                  : "bg-white text-zinc-700 border-zinc-300 hover:border-zinc-400"
              }`}
            >
              <span>↑↓</span>
              <span>{t("dex.sortLabelMobile")}</span>
            </button>
            {moveSortOpen && (
              <div className="absolute right-0 top-full mt-1 z-50 bg-white border border-zinc-200 rounded-lg shadow-lg overflow-hidden min-w-[140px]">
                {MOVE_SORT_OPTIONS.map((opt) => {
                  const isActive = moveSortStat === opt.key;
                  const label = t(opt.labelKey);
                  return (
                    <div key={opt.key} className={`flex items-center justify-between px-3 ${isActive ? "py-2 bg-zinc-100" : "py-3"}`}>
                      <button
                        className={`flex-1 text-left text-sm ${isActive ? "font-semibold text-zinc-900" : "text-zinc-700"}`}
                        onClick={() => {
                          if (isActive) { setMoveSortStat(null); setMoveSortDir("desc"); }
                          else { setMoveSortStat(opt.key); setMoveSortDir("desc"); }
                        }}
                      >
                        {label}
                      </button>
                      {isActive && (
                        <button
                          className="ml-2 w-8 h-8 flex items-center justify-center rounded text-zinc-700 hover:bg-zinc-200 text-base"
                          onClick={() => setMoveSortDir((d) => d === "desc" ? "asc" : "desc")}
                        >
                          {moveSortDir === "desc" ? "↓" : "↑"}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div className="grid gap-y-3 gap-x-4 grid-cols-1 sm:[grid-template-columns:max-content_1fr]">
          <div className="text-sm font-semibold text-zinc-500 uppercase tracking-wide sm:text-zinc-700 sm:normal-case sm:tracking-normal sm:self-center sm:text-center">{t("dex.skill_type")}</div>
          <div className="flex flex-wrap gap-2">
            <FilterButton active={typeId == null} onClick={() => setTypeId(null)}>
              {t("dex.form_all")}
            </FilterButton>
            {(types.data ?? [])
              .filter((tp) => tp.name.toLowerCase() !== "leader" && (tp.localized?.zh ?? "") !== "首领")
              .map((tp) => (
                <FilterButton
                  key={tp.id}
                  active={typeId === tp.id}
                  onClick={() => setTypeId((prev) => (prev === tp.id ? null : tp.id))}
                >
                  <span className="inline-flex items-center gap-0.5">
                    {typeIconUrl(tp.name, 30) ? <img src={typeIconUrl(tp.name, 30)!} alt="" width={22} height={22} /> : null}
                    {pickName(tp as any, lang) || tp.name}
                  </span>
                </FilterButton>
              ))}
            <FilterButton
              active={typeId === "OTHER"}
              onClick={() => setTypeId((prev) => (prev === "OTHER" ? null : "OTHER"))}
            >
              {t("dex.type_other")}
            </FilterButton>
          </div>

          <div className="text-sm font-semibold text-zinc-500 uppercase tracking-wide sm:text-zinc-700 sm:normal-case sm:tracking-normal sm:self-center sm:text-center mt-2 sm:mt-0">{t("dex.skill_category")}</div>
          <div className="flex flex-wrap gap-2">
            <FilterButton active={cat == null} onClick={() => setCat(null)}>
              {t("dex.form_all")}
            </FilterButton>
            {catOptions.map((c) => (
              <FilterButton
                key={c.key}
                active={cat === c.key}
                onClick={() => setCat((prev) => (prev === c.key ? null : c.key))}
              >
                {c.label}
              </FilterButton>
            ))}
          </div>

          {/* Sort row — desktop only, inside same grid for column alignment */}
          <div className="hidden sm:block text-sm font-semibold text-zinc-700 self-center text-center">{t("dex.sortLabel")}</div>
          <div className="hidden sm:flex flex-wrap gap-2">
            {MOVE_SORT_OPTIONS.map((opt) => {
              const isActive = moveSortStat === opt.key;
              const label = t(opt.labelKey);
              if (isActive) {
                return (
                  <div key={opt.key} className="inline-flex h-9 items-center rounded-full bg-zinc-800 text-white shadow-md text-sm font-medium overflow-hidden">
                    <button
                      className="pl-3 pr-1.5 h-full hover:bg-zinc-700 transition-colors"
                      onClick={() => { setMoveSortStat(null); setMoveSortDir("desc"); }}
                    >
                      {label}
                    </button>
                    <button
                      className="pr-3 pl-1 h-full hover:bg-zinc-700 transition-colors"
                      onClick={() => setMoveSortDir((d) => d === "desc" ? "asc" : "desc")}
                    >
                      {moveSortDir === "desc" ? "↓" : "↑"}
                    </button>
                  </div>
                );
              }
              return (
                <FilterButton key={opt.key} active={false} onClick={() => { setMoveSortStat(opt.key); setMoveSortDir("desc"); }}>
                  {label}
                </FilterButton>
              );
            })}
          </div>
        </div>
      </div>

      {/* Virtualized grid (window-based) with dynamic-measured rows + controlled inter-row gap */}
      {moves.isLoading ? (
        <div className="text-zinc-500">{t("common.loading")}</div>
      ) : !displayList.length ? (
        <div className="text-zinc-500">{t("dex.noResults")}</div>
      ) : (
        <div /* wrapper keeps the total scroll height */ style={{ height: rowVirt.getTotalSize() + 90, position: "relative" }}>
          {/* TOP spacer equals the offset to the first visible row */}
          <div style={{ height: topPad }} />

          {/* Visible rows in normal flow; each row has mb-3 to match original grid gap */}
          {vis.map((vi) => {
            const rowIndex = vi.index;
            const start = rowIndex * cols;
            const end = Math.min(displayList.length, start + cols);
            const rowMoves = displayList.slice(start, end);

            return (
              <div
                key={(vi as any).key ?? rowIndex}
                ref={rowVirt.measureElement}
                data-index={vi.index}
                className="mb-3"
              >
                <div className="grid gap-3 grid-cols-1 moves-md:grid-cols-2 moves-lg:grid-cols-3">
                  {rowMoves.map((m) => {
                    const tp = (m.move_type || m.type) as TypeOut | null;
                    const cname = pickName(m as any, lang) || m.name;
                    const desc = pickDesc(m as any, lang) || m.localized?.[lang]?.description || m.description || "";
                    const normalizedCategory = normalizeMoveCategory(m.move_category || m.category || "");
                    const energy = (m.energy_cost ?? m.energy ?? null);
                    const power = m.power ?? null;
                    const isDef = normalizedCategory === "DEFENSE";
                    const isSta = normalizedCategory === "STATUS";

                    // assets
                    const moveNameZh = pickName(m as any, "zh") || cname;
                    const moveImg = moveIconUrlFromCn(moveNameZh);
                    const typeImg = tp?.name ? typeIconUrl(tp.name, 30) : null;
                    const energyImg = moveSubIconUrl("energy.png");

                    // Special handling for Willpower Impact - use conditional-attack icon
                    const isWillpower = m.name === "Willpower Impact" ||
                                       (pickName(m as any, "en") || "").toLowerCase() === "willpower impact" ||
                                       (pickName(m as any, "zh") || "") === "愿力冲击";

                    const catToFile: Record<string, string> = {
                      PHY_ATTACK: "physical-attack",
                      MAG_ATTACK: "magic-attack",
                      DEFENSE: "defense",
                      STATUS: "status",
                    };
                    const catImg = isWillpower
                      ? moveSubIconUrl("conditional-attack.png")
                      : moveSubIconUrl(`${catToFile[normalizedCategory] ?? "physical-attack"}.png`);

                    // Get type color class, fallback to zinc if type not found
                    const typeName = tp?.name?.toLowerCase() || "";
                    const typeColorClass = typeName ? (typeColors[typeName] || "border-l-zinc-400") : "border-l-zinc-400";

                    return (
                      <Link
                        key={m.id}
                        to={`/dex/moves/${m.id}?back=${encodeURIComponent(dexReturnUrl)}`}
                        onClick={() => sessionStorage.setItem("dex_move_scroll", String(window.scrollY))}
                        className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 rounded-lg"
                      >
                        <div
                          className={`
                            rounded-lg border border-zinc-200 bg-white p-3 shadow-sm
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
                              <span className="w-8 text-[13px] sm:text-sm text-left tabular-nums">{energy ?? "—"}</span>
                            </div>

                            {/* (col 4 is the spacer) */}

                            {/* Category icon + power/label (col 5) */}
                            <div className="col-[5] self-center flex items-center justify-end gap-x-[6px]">
                              <img src={catImg} alt="" aria-hidden="true" width={15} height={15} />
                              <span className="w-10 text-[13px] sm:text-sm text-left tabular-nums">
                                {isDef ? t("dex.defense") : isSta ? t("dex.status") : (power ?? "—")}
                              </span>
                            </div>

                            {/* (col 6 is the end spacer) */}

                            {/* Description (row 2, spans full width from col 2 to end) */}
                            <div className="row-[2/3] col-[2/-1] text-[13px] sm:text-sm text-zinc-600 pl-1">
                              <RichDescription text={desc} />
                            </div>
                          </div>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              </div>
            );
          })}

          {/* BOTTOM spacer to fill the remaining height */}
          <div style={{ height: bottomPad }} />
          {/* Additional bottom spacer for breathing room */}
          <div style={{ height: 24 }} />
        </div>
      )}
    </div>
  );
}

/* ===========================================================
   Magic Items tab
   =========================================================== */

function MagicItemsTab() {
  const { lang, t } = useI18n();
  const items = useQuery<MagicItemOut[]>({
    queryKey: ["dex-magic-items"],
    queryFn: () => endpoints.magicItems().then((r) => r.data as MagicItemOut[]),
  });

  return (
    <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {(items.data ?? []).map((it) => {
        const nm = pickName(it as any, lang) || it.name;
        const desc = pickDesc(it as any, lang) || it.description || "";
        const img = magicItemImageUrl(it) || magicItemPlaceholder;

        return (
          <div key={it.id} className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm hover:shadow-md transition-all duration-200 flex items-start gap-3">
            <div className="shrink-0 w-14 h-14 rounded-lg bg-gradient-to-br from-zinc-50 to-white flex items-center justify-center p-2">
              <img
                src={img}
                alt=""
                width={48}
                height={48}
                className="w-full h-full object-contain drop-shadow-sm"
                onError={(e) => { (e.currentTarget as HTMLImageElement).src = monsterPlaceholder; }}
              />
            </div>
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-zinc-800 truncate" title={nm}>{nm}</div>
              <div className="text-sm text-zinc-600 mt-1 leading-relaxed"><RichDescription text={desc} /></div>
            </div>
          </div>
        );
      })}
      {items.isLoading && <div className="text-zinc-500">{t("common.loading")}</div>}
      {!items.isLoading && !items.data?.length && <div className="text-zinc-500">{t("dex.noResults")}</div>}
    </div>
  );
}

/* ===========================================================
   Game Terms tab
   =========================================================== */

function GameTermsTab() {
  const { lang, t } = useI18n();
  const terms = useQuery<GameTermOut[]>({
    queryKey: QUERY_KEYS.GAME_TERMS,
    queryFn: () => endpoints.gameTerms().then((r) => r.data as GameTermOut[]),
  });

  return (
    <div className="grid gap-3 grid-cols-1 md:grid-cols-2">
      {(terms.data ?? []).map((g) => {
        const label = pickName(g as any, lang) || g.key;
        const desc = pickDesc(g as any, lang) || g.description || "";
        return (
          <div key={g.id} className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm hover:shadow-md transition-all duration-200">
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-zinc-800 text-white text-xs font-bold">
                ?
              </span>
              <div className="font-semibold text-zinc-800">{label}</div>
            </div>
            <div className="text-sm text-zinc-600 leading-relaxed">{desc}</div>
          </div>
        );
      })}
      {terms.isLoading && <div className="text-zinc-500">{t("common.loading")}</div>}
      {!terms.isLoading && !terms.data?.length && <div className="text-zinc-500">{t("dex.noResults")}</div>}
    </div>
  );
}

/* ===========================================================
   Page
   =========================================================== */

export default function DexPage() {
  const { t, lang } = useI18n();
  useSeoMeta({
    title: lang === "zh" ? "精灵图鉴 | 洛克王国: 世界" : "Jingling Dex | Roco Kingdom: World",
    description: lang === "zh"
      ? "浏览完整的洛克王国: 世界精灵图鉴，按属性、数值和招式搜索。"
      : "Browse the complete Roco Kingdom: World jingling dex. Search by type, stats, and moves.",
    canonicalPath: "/dex",
  });
  const [sp, setSp] = useSearchParams();

  // Get active tab from URL or default to "monsters"
  const activeTab = sp.get("tab") || "monsters";

  // Handle tab changes - update URL param
  const handleTabChange = (key: string) => {
    const next = new URLSearchParams(sp);
    next.set("tab", key);
    setSp(next, { replace: true });
  };

  return (
    <PageTabs
      activeTab={activeTab}
      onTabChange={handleTabChange}
      tabs={[
        { key: "monsters", label: t("dex.tab_monsters"), content: (<MonstersTab />) as ReactNode },
        { key: "moves",    label: t("dex.tab_moves"),    content: (<MovesTab />) as ReactNode },
        { key: "items",    label: t("dex.tab_items"),    content: (<MagicItemsTab />) as ReactNode },
        { key: "terms",    label: t("dex.tab_terms"),    content: (<GameTermsTab />) as ReactNode },
      ]}
    />
  );
}