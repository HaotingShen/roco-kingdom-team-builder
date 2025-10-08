import { Link, useParams, useSearchParams } from "react-router-dom";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n, pickName, pickDesc, pickFormName } from "@/i18n";
import type { TypeOut, MoveOut, MonsterOut, StatKey } from "@/types";
import { STAT_KEYS } from "@/types";

/* ---------- helpers ---------- */

function typeIconUrl(name?: string, size: 30 | 45 | 60 = 45) {
  if (!name) return null;
  const slug = name.toLowerCase().replace(/\s+/g, "-");
  return `/type-icons/${size}/${slug}.png`;
}

function monsterImgUrlCN(m: any, size: 180 | 270 | 360 = 270) {
  const cnName = pickName(m, "zh") || m.name || String(m.id);
  const cnForm = pickFormName(m, "zh");
  const base = cnForm ? `${cnName}(${cnForm})` : cnName;
  return encodeURI(`/monsters/${size}/${base}.png`);
}

const catIcon: Record<string, string> = {
  PHY_ATTACK: "⚔️",
  MAG_ATTACK: "🪄",
  DEFENSE: "🛡️",
  STATUS: "✨",
  ATTACK: "⚔️",
};

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
  const { lang, t } = useI18n();

  const q = useQuery({
    queryKey: ["monster", id],
    queryFn: () => endpoints.monsterById(id!).then((r) => r.data),
    enabled: !!id,
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
          to={`/dex?tab=${fromTab}`}
          className="inline-flex items-center gap-1 text-sm rounded border px-2 py-1 hover:bg-zinc-50"
        >
          <span aria-hidden className="text-lg leading-none">←</span>
          {t("dex.backToDex") || "Back to Dex"}
        </Link>
      </div>

      {/* Top info — more visual & attractive */}
      <section className="rounded border bg-white p-0 overflow-hidden">
        <div className="grid grid-cols-1 lg:grid-cols-2">
          {/* Left: name, types, image on gradient */}
          <div className="p-4 bg-gradient-to-b from-zinc-50 to-white">
            <div className="text-lg font-semibold">{title}</div>
            <div className="mt-1 flex items-center gap-1">
              {[m.main_type, m.sub_type].filter(Boolean).map((tp: TypeOut) => (
                <span key={tp.id} className="inline-flex items-center gap-1 rounded bg-zinc-100 text-xs px-2 py-0.5">
                  {typeIconUrl(tp.name) ? <img src={typeIconUrl(tp.name)!} alt="" width={18} height={18} /> : null}
                  {pickName(tp as any, lang)}
                </span>
              ))}
            </div>
            <div className="mt-3 flex items-center justify-center">
              <img
                src={monsterImgUrlCN(m, 270)}
                alt=""
                width={270}
                height={270}
                className="h-[200px] w-[200px] object-contain drop-shadow-sm"
                onError={(e)=>{(e.currentTarget as HTMLImageElement).src="/monsters/placeholder.png"}}
              />
            </div>
          </div>

          {/* Right: stat bars */}
          <div className="p-4">
            <div className="font-medium mb-1">{t("dex.totalBase")}: {total}</div>
            <div className="space-y-1">
              {STAT_KEYS.map((k) => {
                const labels: Record<StatKey, string> = {
                  hp: t("labels.hp"),
                  phy_atk: t("labels.phyAtk"),
                  mag_atk: t("labels.magAtk"),
                  phy_def: t("labels.phyDef"),
                  mag_def: t("labels.magDef"),
                  spd: t("labels.spd"),
                };
                const val = baseStats[k] ?? 0;
                const pct = Math.min(100, Math.round((val / 200) * 100));
                return (
                  <div key={k} className="flex items-center gap-2">
                    <div className="w-24 text-[12px] text-zinc-600">{labels[k]}</div>
                    <div className="flex-1 h-2 rounded bg-zinc-100 overflow-hidden">
                      <div className="h-full bg-zinc-800" style={{ width: `${pct}%` }} />
                    </div>
                    <div className="w-10 text-right text-[11px] text-zinc-600 tabular-nums">{val}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>

      {/* Trait */}
      {trait ? (
        <section className="rounded border bg-white p-3">
          <div className="font-medium mb-1">{pickName(trait as any, lang) || trait.name}</div>
          <div className="text-sm text-zinc-700">
            {pickDesc(trait as any, lang) || trait.description || ""}
          </div>
        </section>
      ) : null}

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
        <section className="rounded border bg-white p-3">
          <div className="flex items-center gap-2 mb-2">
            <Link to={`?tab=${fromTab}&moves=pool`} className={`inline-flex items-center justify-center h-8 px-2 rounded border hover:bg-zinc-50 text-sm ${which === "pool" ? "bg-zinc-200" : ""}`}>
              {t("dex.learnable")}
            </Link>
            <Link to={`?tab=${fromTab}&moves=legacy`} className={`inline-flex items-center justify-center h-8 px-2 rounded border hover:bg-zinc-50 text-sm ${which === "legacy" ? "bg-zinc-200" : ""}`}>
              {t("dex.legacy")}
            </Link>
          </div>
          <MovesList list={which === "legacy" ? legacyMoves : movePool} />
        </section>
      ) : null}
    </div>
  );
}

function MovesList({ list }: { list: any[] }) {
  const { lang, t } = useI18n();
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

        return (
          <div key={m.id} className="rounded border bg-white p-3">
            <div className="
              grid
              sm:grid-cols-[80px_30px_minmax(0,1fr)_40px_8px_50px]
              md:grid-cols-[80px_30px_minmax(0,1fr)_40px_16px_50px]
              lg:grid-cols-[80px_30px_minmax(0,1fr)_40px_24px_50px]
              grid-rows-[auto_auto_auto]
              items-start gap-2 text-sm
            ">
              {/* Image (rows 1–2) */}
              <div className="row-[1/3] h-[80px] w-[80px] rounded bg-zinc-100/60 overflow-hidden flex items-center justify-center">
                <img
                  src={moveImg}
                  alt={cname}
                  width={80}
                  height={80}
                  loading="lazy"
                  className="h-full w-full object-contain"
                  onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
                />
              </div>

              {/* Type icon */}
              <div className="col-[2] self-center flex items-center justify-center">
                {typeImg ? <img src={typeImg} alt="" aria-hidden width={24} height={24} /> : null}
              </div>

              {/* Name */}
              <div className="col-[3] self-center min-w-0">
                <div className="font-medium truncate" title={cname}>{cname}</div>
              </div>

              {/* Energy */}
              <div className="col-[4] self-center flex items-center justify-end gap-[6px]">
                <img src={energyImg} alt="" aria-hidden width={15} height={15} />
                <span className="w-8 text-xs text-left tabular-nums">{energy ?? "—"}</span>
              </div>

              {/* (col 5 spacer) */}

              {/* Category + power/label */}
              <div className="col-[6] self-center flex items-center justify-end gap-[6px]">
                <img src={catImg} alt="" aria-hidden width={15} height={15} />
                <span className="w-10 text-xs text-left tabular-nums">
                  {isDef ? t("dex.defense") : isSta ? t("dex.status") : (power ?? "—")}
                </span>
              </div>

              {/* Description (rows 2–3, cols 2–5) */}
              <div className="row-[2/4] col-[2/7] text-sm text-zinc-600 pl-1">
                {desc}
              </div>

              {/* Move Stone badge (bottom-left) */}
              <div className="row-[3] col-[1] flex items-center justify-center">
                {m.is_move_stone ? (
                  <span className="inline-flex items-center gap-0.5 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700 shadow-[0_0_0_1px_rgba(245,158,11,0.2)]">
                    <img alt="" width="13" height="13" src="/decorative-icons/move-stone.png"></img>
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