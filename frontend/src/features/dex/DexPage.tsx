import { useMemo, useState, useEffect } from "react";
import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { endpoints } from "@/lib/api";
import { useI18n, pickName, pickDesc, pickFormName } from "@/i18n";
import type { MonsterLiteOut, MoveOut, TypeOut, MagicItemOut } from "@/types";
import PageTabs from "@/components/PageTabs";
import useDebounce from "@/hooks/useDebounce";
import { useQuery } from "@tanstack/react-query";
import { useWindowVirtualizer } from "@tanstack/react-virtual";
import { typeIconUrl, magicItemImageUrl } from "@/lib/images";

/* ---------------- helpers ---------------- */

/** Image filename matches Chinese name (and Chinese form in parentheses if not default). */
function monsterImgUrlCN(m: any, size: 180 | 270 | 360 = 180) {
  const cnName = pickName(m, "zh") || m.name || String(m.id);
  const cnForm = pickFormName(m, "zh");
  const base = cnForm ? `${cnName}(${cnForm})` : cnName;
  // Use encodeURI to support Chinese and parentheses in URLs.
  return encodeURI(`/monsters/${size}/${base}.png`);
}

function useColumns(kind: "monsters" | "moves") {
  const [w, setW] = useState<number>(() => (typeof window !== "undefined" ? window.innerWidth : 1024));
  useEffect(() => {
    const onR = () => setW(window.innerWidth);
    window.addEventListener("resize", onR);
    return () => window.removeEventListener("resize", onR);
  }, []);
  if (kind === "monsters") {
    // matches: 1 / 2(sm) / 3(lg) / 5(xl)
    return w >= 1280 ? 5 : w >= 1024 ? 3 : w >= 640 ? 2 : 1;
  }
  // moves: 1 / 2(sm) / 3(lg)
  return w >= 1024 ? 3 : w >= 640 ? 2 : 1;
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
        inline-flex h-8 items-center px-3 rounded-full text-sm font-medium cursor-pointer
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
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${styles[tone]}`}>
      {children}
    </span>
  );
}

/* ===========================================================
   Monsters tab
   =========================================================== */

function MonstersTab() {
  const { lang, t } = useI18n();
  const [sp, setSp] = useSearchParams();
  // keep state in URL so returning to the page restores filters
  const [q, setQ] = useState(sp.get("q") ?? "");
  const dq = useDebounce(q, 200);
  const [selectedTypes, setSelectedTypes] = useState<number[]>(
    () => (sp.get("types")?.split(",").map(Number).filter(Boolean) ?? [])
  );
  const [filterVariant, setFilterVariant] = useState<"all" | "regional" | "leader">(
    (sp.get("form") as any) || "all"
  );

  const types = useQuery<TypeOut[]>({
    queryKey: ["types-all"],
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
  });

  const monsters = useQuery<MonsterLiteOut[]>({
    queryKey: ["dex-monsters"],
    queryFn: () => endpoints.monsters().then((r) => (r.data?.items ?? r.data) as MonsterLiteOut[]),
  });

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
      if (filterVariant === "regional" && (!m.form || m.form.toLowerCase() === "default")) return false;
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
  }, [monsters.data, dq, selectedTypes, filterVariant]);

  const toggleType = (id: number) =>
    setSelectedTypes((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  // --- virtualization (treat each grid *row* as one virtual item) ---
  const cols = useColumns("monsters");
  const rowCount = Math.ceil((filtered?.length ?? 0) / cols);
  const rowEstimate = 220; // ~ card + gaps
  const rowVirt = useWindowVirtualizer({
    count: rowCount,
    estimateSize: () => rowEstimate,
    overscan: 6,
  });
  const vItems = rowVirt.getVirtualItems();
  const fromRow = vItems[0]?.index ?? 0;
  const toRow = vItems[vItems.length - 1]?.index ?? -1;
  const startIdx = fromRow * cols;
  const endIdx = Math.min(filtered.length, (toRow + 1) * cols);

  // keep URL in sync
  useEffect(() => {
    const next = new URLSearchParams(sp);
    q ? next.set("q", q) : next.delete("q");
    selectedTypes.length ? next.set("types", selectedTypes.join(",")) : next.delete("types");
    filterVariant !== "all" ? next.set("form", filterVariant) : next.delete("form");
    setSp(next, { replace: true });
  }, [q, selectedTypes, filterVariant]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-3">
      {/* Filters */}
      <div className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("dex.search")}
              className="h-10 w-[220px] rounded-lg border border-zinc-300 pl-4 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400 focus:border-transparent transition-all"
            />
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 text-lg">🔍</span>
          </div>
        </div>

        <div className="grid gap-y-3 gap-x-4 [grid-template-columns:max-content_1fr]">
          <div className="self-center text-sm font-semibold text-zinc-700">{t("dex.typesLabel")}</div>
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
                  {typeIconUrl(tp.name) ? (
                    <img src={typeIconUrl(tp.name)!} alt="" width={20} height={20} />
                  ) : null}
                  {pickName(tp as any, lang) || tp.name}
                </span>
              </FilterButton>
            ))}
          </div>

          <div className="self-center text-sm font-semibold text-zinc-700">{t("dex.formsLabel")}</div>
          <div className="flex flex-wrap items-center gap-2">
            <FilterButton active={filterVariant === "all"} onClick={() => setFilterVariant("all")}>
              {t("dex.form_all")}
            </FilterButton>
            <FilterButton active={filterVariant === "regional"} onClick={() => setFilterVariant("regional")}>
              {t("dex.form_regional")}
            </FilterButton>
            <FilterButton active={filterVariant === "leader"} onClick={() => setFilterVariant("leader")}>
              {t("dex.form_leader")}
            </FilterButton>
          </div>
        </div>
      </div>

      {/* Virtualized grid (window-based) */}
      {(!monsters.data || !filtered.length) ? (
        <div className="text-zinc-500">{t("dex.noResults")}</div>
      ) : (
        <div style={{ height: rowVirt.getTotalSize(), position: "relative" }}>
          <div style={{ transform: `translateY(${vItems[0]?.start ?? 0}px)` }}>
            <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
              {filtered.slice(startIdx, endIdx).map((m) => {
                const titleName = pickName(m as any, lang) || m.name;
                const formLabel = pickFormName(m as any, lang);
                const title = [titleName, formLabel ? `(${formLabel})` : ""].filter(Boolean).join(" ");
                const src = monsterImgUrlCN(m, 180);

                return (
                  <Link
                    key={m.id}
                    to={`/dex/monsters/${m.id}?tab=monsters`}
                    className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm hover:shadow-md hover:-translate-y-1 transition-all duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400"
                  >
                    <div className="text-sm font-semibold truncate text-zinc-800" title={title}>{title}</div>
                    <div className="mt-3 flex items-center justify-center">
                      <img
                        src={src}
                        alt=""
                        width={180}
                        height={180}
                        className="h-[120px] w-[120px] object-contain drop-shadow-sm"
                        loading="lazy"
                        onError={(e) => { (e.currentTarget as HTMLImageElement).src = "/monsters/placeholder.png"; }}
                      />
                    </div>
                    <div className="mt-3 flex items-center gap-1 flex-wrap">
                      {[m.main_type, m.sub_type].filter(Boolean).map((tp) => (
                        <Pill key={(tp as TypeOut).id}>
                          {typeIconUrl((tp as TypeOut).name) ? (
                            <img src={typeIconUrl((tp as TypeOut).name)!} alt="" width={16} height={16} />
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
        </div>
      )}
    </div>
  );
}

/* ===========================================================
   Moves tab  (UPDATED: Plan B + padding spacers) + hide first DB move
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
  is_move_stone?: boolean;
};

function MovesTab() {
  const { lang, t } = useI18n();
  const [sp, setSp] = useSearchParams();
  const [q, setQ] = useState(sp.get("mq") ?? "");
  const dq = useDebounce(q, 200);
  const [typeId, setTypeId] = useState<number | null>(() => {
    const v = sp.get("mtype");
    return v ? Number(v) : null;
  });
  const [cat, setCat] = useState<string | null>(sp.get("mcat") ?? null);

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

  // Identify the very first move ever recorded (lowest id) and hide it
  const firstMoveId = useMemo<number | null>(() => {
    const list = moves.data ?? [];
    if (!list.length) return null;
    let min = Infinity;
    for (const m of list) {
      const idNum = Number((m as any).id);
      if (!Number.isNaN(idNum) && idNum < min) min = idNum;
    }
    return min === Infinity ? null : min;
  }, [moves.data]);

  const filtered = useMemo(() => {
    const list = moves.data ?? [];
    const kw = dq.trim().toLowerCase();

    return list.filter((m) => {
      // hide the very first DB move regardless of filters
      if (firstMoveId != null && m.id === firstMoveId) return false;

      // type
      const tp = (m.move_type || m.type) as TypeOut | null;
      if (typeId && (!tp || tp.id !== typeId)) return false;

      // category (normalize) — compare to selected cat (single-select)
      const catUpper = (m.move_category || m.category || "").toUpperCase();
      if (cat && catUpper !== cat) return false;

      if (!kw) return true;

      // names/descriptions — SUPPORT EN & 中文
      const nmEN = (pickName(m as any, "en") || m.name || "").toLowerCase();
      const nmZH = (pickName(m as any, "zh") || "").toLowerCase();
      const descEN = (m.localized?.en?.description ?? m.description ?? "").toLowerCase();
      const descZH = (m.localized?.zh?.description ?? "").toLowerCase();
      return [nmEN, nmZH, descEN, descZH].some((s) => s.includes(kw));
    });
  }, [moves.data, dq, typeId, cat, firstMoveId]);

  const catOptions = [
    { key: "PHY_ATTACK", label: t("dex.cat_phy") },
    { key: "MAG_ATTACK", label: t("dex.cat_mag") },
    { key: "DEFENSE", label: t("dex.cat_def") },
    { key: "STATUS", label: t("dex.cat_sta") },
  ];

  // --- virtualization for moves grid (measureElement + padding spacers) ---
  const cols = useColumns("moves");
  const rowCount = Math.ceil((filtered?.length ?? 0) / cols);
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
    typeId ? next.set("mtype", String(typeId)) : next.delete("mtype");
    cat ? next.set("mcat", cat) : next.delete("mcat");
    setSp(next, { replace: true });
  }, [q, typeId, cat]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-3">
      {/* Filters */}
      <div className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={t("dex.search")}
              className="h-10 w-[220px] rounded-lg border border-zinc-300 pl-4 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-400 focus:border-transparent transition-all"
            />
            <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-zinc-400 text-lg">🔍</span>
          </div>
        </div>

        <div className="grid gap-y-3 gap-x-4 [grid-template-columns:max-content_1fr]">
          <div className="self-center text-sm font-semibold text-zinc-700">{t("dex.skill_type")}</div>
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
                    {typeIconUrl(tp.name) ? <img src={typeIconUrl(tp.name)!} alt="" width={20} height={20} /> : null}
                    {pickName(tp as any, lang) || tp.name}
                  </span>
                </FilterButton>
              ))}
          </div>

          <div className="self-center text-sm font-semibold text-zinc-700">{t("dex.skill_category")}</div>
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
        </div>
      </div>

      {/* Virtualized grid (window-based) with dynamic-measured rows + controlled inter-row gap */}
      {(!moves.data || !filtered.length) ? (
        <div className="text-zinc-500">{t("dex.noResults")}</div>
      ) : (
        <div /* wrapper keeps the total scroll height */ style={{ height: rowVirt.getTotalSize(), position: "relative" }}>
          {/* TOP spacer equals the offset to the first visible row */}
          <div style={{ height: topPad }} />

          {/* Visible rows in normal flow; each row has mb-3 to match original grid gap */}
          {vis.map((vi) => {
            const rowIndex = vi.index;
            const start = rowIndex * cols;
            const end = Math.min(filtered.length, start + cols);
            const rowMoves = filtered.slice(start, end);

            return (
              <div
                key={(vi as any).key ?? rowIndex}
                ref={rowVirt.measureElement}
                data-index={vi.index}
                className="mb-3"
              >
                <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
                  {rowMoves.map((m) => {
                    const tp = (m.move_type || m.type) as TypeOut | null;
                    const cname = pickName(m as any, lang) || m.name;
                    const desc = pickDesc(m as any, lang) || m.localized?.[lang]?.description || m.description || "";
                    const category = (m.move_category || m.category || "").toUpperCase();
                    const energy = (m.energy_cost ?? m.energy ?? null);
                    const power = m.power ?? null;
                    const isDef = category === "DEFENSE";
                    const isSta = category === "STATUS";

                    // assets
                    const moveNameZh = pickName(m as any, "zh") || cname;
                    const moveImg = encodeURI(`/move-icons/${moveNameZh}.png`); // 128x128 source
                    const typeImg = tp?.name ? typeIconUrl(tp.name, 30) : null;
                    const energyImg = "/move-sub-icons/energy.png";
                    const catToFile: Record<string, string> = {
                      PHY_ATTACK: "physical-attack",
                      MAG_ATTACK: "magic-attack",
                      DEFENSE: "defense",
                      STATUS: "status",
                    };
                    const catImg = `/move-sub-icons/${catToFile[category] ?? "physical-attack"}.png`;

                    // Get type color class, fallback to zinc if type not found
                    const typeName = tp?.name?.toLowerCase() || "";
                    const typeColorClass = typeName ? (typeColors[typeName] || "border-l-zinc-400") : "border-l-zinc-400";

                    return (
                      <div
                        key={m.id}
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
                            sm:grid-cols-[80px_minmax(0,1fr)_40px_8px_50px]
                            md:grid-cols-[80px_minmax(0,1fr)_40px_16px_50px]
                            lg:grid-cols-[80px_minmax(0,1fr)_40px_24px_50px]
                            grid-rows-[auto_auto_auto]
                            items-start
                            gap-2
                            text-sm
                          "
                        >
                          {/* Image (spans rows 1–2) */}
                          <div className="row-[1/3] h-[80px] w-[80px] rounded bg-zinc-100/60 overflow-hidden flex items-center justify-center">
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
                              <div className="font-medium whitespace-normal break-words sm:break-keep">
                                {cname}
                              </div>
                            </div>
                          </div>

                          {/* Energy icon + value (col 3) */}
                          <div className="col-[3] self-center flex items-center justify-end gap-[6px]">
                            <img src={energyImg} alt="" aria-hidden="true" width={15} height={15} />
                            <span className="w-8 text-xs text-left tabular-nums">{energy ?? "—"}</span>
                          </div>

                          {/* (col 4 is the spacer) */}

                          {/* Category icon + power/label (col 5) */}
                          <div className="col-[5] self-center flex items-center justify-end gap-x-[6px]">
                            <img src={catImg} alt="" aria-hidden="true" width={15} height={15} />
                            <span className="w-10 text-xs text-left tabular-nums">
                              {isDef ? t("dex.defense") : isSta ? t("dex.status") : (power ?? "—")}
                            </span>
                          </div>

                          {/* Description (rows 2–3, cols 2–5) */}
                          <div className="row-[2/4] col-[2/6] text-sm text-zinc-600 pl-1">
                            {desc}
                          </div>

                          {/* Move Stone badge */}
                          <div className="row-[3] col-[1] flex items-center justify-center">
                            {m.is_move_stone ? (
                              <span className="inline-flex items-center gap-0.5 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700 shadow-[0_0_0_1px_rgba(245,158,11,0.2)]">
                                <img alt="" width="13" height="13" src="/decorative-icons/move-stone.png" />
                                {t("dex.move_stone")}
                              </span>
                            ) : null}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}

          {/* BOTTOM spacer to fill the remaining height */}
          <div style={{ height: bottomPad }} />
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
        const img = magicItemImageUrl(it) || "/magic-items/placeholder.png";

        return (
          <div key={it.id} className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm hover:shadow-md transition-all duration-200 flex items-start gap-3">
            <div className="shrink-0 w-14 h-14 rounded-lg bg-gradient-to-br from-zinc-50 to-white flex items-center justify-center p-2">
              <img
                src={img}
                alt=""
                width={48}
                height={48}
                className="w-full h-full object-contain drop-shadow-sm"
                onError={(e) => { (e.currentTarget as HTMLImageElement).src = "/monsters/placeholder.png"; }}
              />
            </div>
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-zinc-800 truncate" title={nm}>{nm}</div>
              <div className="text-sm text-zinc-600 mt-1 leading-relaxed">{desc}</div>
            </div>
          </div>
        );
      })}
      {!items.data?.length && <div className="text-zinc-500">{t("dex.noResults")}</div>}
    </div>
  );
}

/* ===========================================================
   Game Terms tab
   =========================================================== */

type GameTerm = { id: number; key: string; name?: string; description?: string; localized?: any };

function GameTermsTab() {
  const { lang, t } = useI18n();
  const terms = useQuery<GameTerm[]>({
    queryKey: ["dex-terms"],
    queryFn: () => endpoints.gameTerms().then((r) => r.data as GameTerm[]),
  });

  return (
    <div className="grid gap-3 grid-cols-1 md:grid-cols-2">
      {(terms.data ?? []).map((g) => {
        const label = pickName(g as any, lang) || g.name || g.key;
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
      {!terms.data?.length && <div className="text-zinc-500">{t("dex.noResults")}</div>}
    </div>
  );
}

/* ===========================================================
   Page
   =========================================================== */

export default function DexPage() {
  const { t } = useI18n();
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