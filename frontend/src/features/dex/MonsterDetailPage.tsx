import { Link, useParams, useSearchParams } from "react-router-dom";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n, pickName, pickDesc, pickFormName } from "@/i18n";
import type { TypeOut, MoveOut, MonsterOut, StatKey } from "@/types";
import { STAT_KEYS } from "@/types";
import { typeIconUrl } from "@/lib/images";

/* ---------- helpers ---------- */

function monsterImgUrlCN(m: any, size: 180 | 270 | 360 = 270) {
  const cnName = pickName(m, "zh") || m.name || String(m.id);
  const cnForm = pickFormName(m, "zh");
  const base = cnForm ? `${cnName}(${cnForm})` : cnName;
  return encodeURI(`/monsters/${size}/${base}.png`);
}

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
    queryKey: ["moves-by-ids", ids.join(",")],
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
  const which = sp.get("moves") === "legacy" ? "legacy" : "pool";
  const fromBuilder = sp.get("from") === "builder";
  const { lang, t } = useI18n();

  const q = useQuery({
    queryKey: ["monster", id],
    queryFn: () => endpoints.monsterById(id!).then((r) => r.data),
    enabled: !!id,
  });

  // Check if previous monster exists
  const prevQ = useQuery({
    queryKey: ["monster", Number(id) - 1],
    queryFn: async () => {
      try {
        return await endpoints.monsterById(String(Number(id) - 1)).then((r) => r.data);
      } catch (err) {
        // Silently fail - 404 is expected when no previous monster exists
        return null;
      }
    },
    enabled: !!id && Number(id) > 1,
    retry: false,
  });

  // Check if next monster exists
  const nextQ = useQuery({
    queryKey: ["monster", Number(id) + 1],
    queryFn: async () => {
      try {
        return await endpoints.monsterById(String(Number(id) + 1)).then((r) => r.data);
      } catch (err) {
        // Silently fail - 404 is expected when no next monster exists
        return null;
      }
    },
    enabled: !!id,
    retry: false,
  });

  useEffect(() => { window.scrollTo(0, 0); }, [id]);

  const m = (q.data ?? {}) as any;
  const nm = pickName(m as any, lang) || m.name;
  const fm = pickFormName(m as any, lang);
  const title = [nm, fm ? `(${fm})` : ""].filter(Boolean).join(" ");

  const trait = m.trait || m.ability || null;
  const evo = m.evolution_chain || []; // array of ids or {id, name, form}
  
  const baseStats = extractStats(m);
  const total = STAT_KEYS.reduce<number>((s, k) => s + (baseStats[k] ?? 0), 0);

  const movePool = useMoveObjects(m.move_pool);
  const legacyMoves = useMoveObjects(m.legacy_moves);

  if (q.isLoading) return <div>{t("common.loading")}</div>;
  if (!q.data) return <div>Not found.</div>;

  return (
    <div className="space-y-3">
      <div className="flex items-center">
        <Link
          to={fromBuilder ? "/build" : `/dex?tab=${fromTab}`}
          className="inline-flex items-center gap-1 text-sm font-medium rounded-lg border border-zinc-300 bg-white px-4 py-2 shadow-sm hover:bg-zinc-50 hover:border-zinc-400 hover:shadow transition-all duration-200"
        >
          <span aria-hidden className="text-xl leading-none text-zinc-600 -translate-y-[1px]">←</span>
          <span className="text-zinc-700">{fromBuilder ? t("dex.backToBuilder") : t("dex.backToDex")}</span>
        </Link>
      </div>

      {/* Top monster info */}
      <section className="rounded-lg border border-zinc-200 bg-white shadow-sm overflow-hidden">
        <div className="grid grid-cols-1 lg:grid-cols-2">
          {/* Left: name, types, image on gradient - vertically centered */}
          <div className="relative p-6 bg-gradient-to-br from-zinc-50 via-white to-zinc-50 flex flex-col justify-center items-center gap-4 min-h-[320px]">
            {/* Previous Monster Button */}
            {prevQ.data && (
              <Link
                to={`/dex/monsters/${m.id - 1}?tab=${fromTab}${fromBuilder ? "&from=builder" : ""}`}
                className="absolute left-2 top-1/2 -translate-y-1/2 inline-flex items-center justify-center w-10 h-10 rounded-full bg-white border border-zinc-300 shadow-md hover:bg-zinc-50 hover:border-zinc-400 hover:shadow-lg transition-all duration-200 text-zinc-600 hover:text-zinc-900"
                aria-label="Previous monster"
              >
                <span className="text-3xl leading-none -translate-y-[3px]">‹</span>
              </Link>
            )}

            {/* Next Monster Button */}
            {nextQ.data && (
              <Link
                to={`/dex/monsters/${m.id + 1}?tab=${fromTab}${fromBuilder ? "&from=builder" : ""}`}
                className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center justify-center w-10 h-10 rounded-full bg-white border border-zinc-300 shadow-md hover:bg-zinc-50 hover:border-zinc-400 hover:shadow-lg transition-all duration-200 text-zinc-600 hover:text-zinc-900"
                aria-label="Next monster"
              >
                <span className="text-3xl leading-none -translate-y-[3px]">›</span>
              </Link>
            )}

            <div className="text-center space-y-2">
              <h1 className="text-2xl font-bold text-zinc-800">{title}</h1>
              <div className="flex items-center justify-center gap-2">
                {[m.main_type, m.sub_type].filter(Boolean).map((tp: TypeOut) => (
                  <span key={tp.id} className="inline-flex items-center gap-1 rounded-full bg-white border border-zinc-200 text-sm px-3 py-1 shadow-sm">
                    {typeIconUrl(tp.name) ? <img src={typeIconUrl(tp.name)!} alt="" width={22} height={22} /> : null}
                    <span className="font-medium text-zinc-700">{pickName(tp as any, lang)}</span>
                  </span>
                ))}
              </div>
            </div>
            <div className="flex items-center justify-center">
              <img
                src={monsterImgUrlCN(m, 270)}
                alt=""
                width={270}
                height={270}
                className="h-[200px] w-[200px] object-contain drop-shadow-md hover:scale-105 transition-transform duration-200"
                onError={(e)=>{(e.currentTarget as HTMLImageElement).src="/monsters/placeholder.png"}}
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
                  <span className="text-lg font-bold text-zinc-800 bg-zinc-100 px-3 py-1 rounded-full">
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
                      {pickDesc(trait as any, lang) || trait.description || ""}
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      {/* Evolution chain */}
      {Array.isArray(evo) && evo.length > 1 ? (
        <section className="rounded border bg-white p-3">
          <div className="font-medium mb-2">{t("dex.evolution")}</div>
          <div className="flex items-center gap-2 overflow-x-auto">
            {evo.map((n: any, i: number) => {
              const mid = typeof n === "number" ? n : n.id;
              const label = typeof n === "number" ? `#${n}` : pickName(n as any, lang) || n.name;
              return (
                <div key={`${mid}-${i}`} className="inline-flex items-center gap-2">
                  <img
                    src={monsterImgUrlCN(typeof n === "number" ? { id: mid, name: label } : n, 180)}
                    onError={(e)=>{(e.currentTarget as HTMLImageElement).src="/monsters/placeholder.png"}}
                    alt=""
                    className="h-16 w-16 object-contain"
                  />
                  {i < evo.length - 1 ? <span className="opacity-60">→</span> : null}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {/* Moves */}
      {(movePool?.length || legacyMoves?.length) ? (
        <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4">
          {/* Tab Switcher */}
          <div className="flex items-center justify-center mb-4">
            <div className="inline-flex items-center gap-1 p-1 rounded-full bg-zinc-100 shadow-inner">
              <Link
                to={`?tab=${fromTab}&moves=pool${fromBuilder ? "&from=builder" : ""}`}
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
                to={`?tab=${fromTab}&moves=legacy${fromBuilder ? "&from=builder" : ""}`}
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
          <MovesList list={which === "legacy" ? legacyMoves : movePool} />
        </section>
      ) : null}
    </div>
  );
}

function MovesList({ list }: { list: any[] }) {
  const { lang, t } = useI18n();

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
    <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
      {(list ?? []).map((m: MoveOut & any) => {
        const tp = (m.move_type || m.type) as TypeOut | null;
        const cname = pickName(m as any, lang) || m.name;
        const desc = pickDesc(m as any, lang) || m.localized?.[lang]?.description || m.description || "";
        const category = (m.move_category || m.category || "").toUpperCase();
        const energy = (m.energy_cost ?? m.energy ?? null);
        const power = m.power ?? null;
        const isDef = category === "DEFENSE";
        const isSta = category === "STATUS";

        const moveNameZh = pickName(m as any, "zh") || cname;
        const moveImg = encodeURI(`/move-icons/${moveNameZh}.png`);
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
        // Convert type name to lowercase to match our mapping
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
      {!list?.length && <div className="text-zinc-500">{t("dex.noResults")}</div>}
    </div>
  );
}