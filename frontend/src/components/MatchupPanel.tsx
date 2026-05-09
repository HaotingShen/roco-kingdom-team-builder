import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useI18n, pickName, pickDesc } from "@/i18n";
import { computeMatchup } from "@/lib/matchup";
import { getAttackerStatusOptions } from "@/lib/attackerStatusOptions";
import { typeIconUrl, monsterImageFallbackChain, monsterPlaceholder } from "@/lib/images";
import PanelCard from "./PanelCard";
import type { MoveMatchupResult } from "@/lib/matchup";
import type {
  MonsterOut,
  MoveOut,
  PersonalityOut,
  StatusOut,
  TalentUpsert,
  UserMonsterCreate,
} from "@/types";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function damageColorClass(typeMultiplier: number): string {
  if (typeMultiplier > 1) return "text-emerald-600";
  if (typeMultiplier < 1) return "text-rose-500";
  return "text-zinc-500";
}

function killBadge(damage: number, hp: number, t: (k: string) => string) {
  if (damage <= 0 || hp <= 0) return null;
  if (damage >= hp) return { text: t("analysis.matchupOneHko"), cls: "bg-rose-100 text-rose-700" };
  return null;
}

function normalizeCat(move: MoveOut): string {
  const raw = (move.move_category ?? move.category ?? "") as string;
  const u = raw.toUpperCase();
  if (u === "PHYSICAL ATTACK") return "PHY_ATTACK";
  if (u === "MAGIC ATTACK") return "MAG_ATTACK";
  return u || "STATUS";
}

function DamageTooltip({
  damage,
  hpPercent,
  typeMultiplier,
}: {
  damage: number;
  hpPercent: number;
  typeMultiplier: number;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const colorCls = damageColorClass(typeMultiplier);

  const hint =
    typeMultiplier > 1
      ? t("analysis.matchupEffectiveHint")
      : typeMultiplier < 1
      ? t("analysis.matchupNotEffectiveHint")
      : t("analysis.matchupNeutralHint");

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const closeOnScroll = () => setOpen(false);
    document.addEventListener("mousedown", close);
    window.addEventListener("scroll", closeOnScroll, { passive: true, capture: true });
    return () => {
      document.removeEventListener("mousedown", close);
      window.removeEventListener("scroll", closeOnScroll, { capture: true });
    };
  }, [open]);

  return (
    <span
      ref={ref}
      className="relative group flex items-center gap-1 cursor-help"
      onClick={() => setOpen((v) => !v)}
    >
      <span className={`text-sm font-bold tabular-nums ${colorCls}`}>{damage}</span>
      <span className={`text-xs tabular-nums ${colorCls}`}>({hpPercent.toFixed(1)}%)</span>

      {/* Tooltip */}
      <span
        className={`pointer-events-none absolute z-20 bottom-full right-0 mb-2 w-max max-w-[220px] rounded-md bg-zinc-800 px-2.5 py-1.5 text-[11px] leading-snug text-white shadow-lg transition-opacity duration-150 ${
          open ? "opacity-100" : "opacity-0"
        } group-hover:opacity-100`}
      >
        {hint}
        <span className="absolute top-full right-3 border-4 border-transparent border-t-zinc-800" />
      </span>
    </span>
  );
}

type DefenseOption = { id: string; label: string; status: StatusOut | null };

// ─── MonsterStrip ─────────────────────────────────────────────────────────────

function MonsterStrip({
  monster,
  sideLabel,
  dexBackUrl,
  align = "left",
}: {
  monster: MonsterOut;
  sideLabel: string;
  dexBackUrl: string;
  align?: "left" | "right";
}) {
  const { lang } = useI18n();
  const images = useMemo(() => monsterImageFallbackChain(monster, 180), [monster]);
  const [imgSrc, setImgSrc] = useState<string>(images[0] ?? monsterPlaceholder);
  const [fallIdx, setFallIdx] = useState(0);

  useEffect(() => {
    setImgSrc(images[0] ?? monsterPlaceholder);
    setFallIdx(0);
  }, [images]);

  const name = pickName(monster, lang) || monster.name;
  const isRight = align === "right";

  return (
    <div className={`flex items-center gap-2.5 min-w-0 ${isRight ? "flex-row-reverse" : ""}`}>
      {/* Monster avatar */}
      <Link
        to={dexBackUrl}
        className="shrink-0 w-12 h-12 sm:w-14 sm:h-14 md:w-16 md:h-16 rounded-xl overflow-hidden bg-zinc-100 border border-zinc-200 hover:opacity-80 transition-opacity"
      >
        <img
          src={imgSrc}
          alt={name}
          className="w-full h-full object-contain"
          onError={() => {
            const next = fallIdx + 1;
            const url = images[next];
            if (next < images.length && url) { setImgSrc(url); setFallIdx(next); }
          }}
        />
      </Link>
      {/* Identity info */}
      <div className={`min-w-0 flex-1 ${isRight ? "text-right" : ""}`}>
        <p className="text-[10px] font-bold uppercase tracking-widest text-zinc-400 leading-none mb-0.5">
          {sideLabel}
        </p>
        <p className="text-sm font-semibold text-zinc-900 truncate leading-tight">{name}</p>
        <div className={`flex flex-wrap items-center gap-1 mt-0 sm:mt-1 ${isRight ? "justify-end" : ""}`}>
          {[monster.main_type, monster.sub_type].filter(Boolean).map((tp) => {
            const icon = typeIconUrl(tp!.name, 30);
            return (
              <span
                key={tp!.id}
                className="inline-flex items-center gap-0.5 sm:rounded-full sm:bg-zinc-100 sm:px-1.5 sm:py-0.5 text-xs font-medium text-zinc-600"
              >
                {icon && <img src={icon} alt={tp!.name} className="w-5 h-5" />}
                <span className="hidden sm:inline">{pickName(tp!, lang) || tp!.name}</span>
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─── MoveRow ──────────────────────────────────────────────────────────────────

function MoveRow({ row, defenderHp }: { row: MoveMatchupResult; defenderHp: number }) {
  const { lang, t } = useI18n();

  const moveName = pickName(row.move, lang) || row.move.name;
  const moveDesc = pickDesc(row.move, lang);
  const moveTypeName = row.move.move_type?.name ?? row.move.type?.name;
  const typeIcon = moveTypeName ? typeIconUrl(moveTypeName, 30) : null;
  const cat = normalizeCat(row.move);

  const typeIconEl = typeIcon
    ? <img src={typeIcon} alt={moveTypeName} className="w-5 h-5 sm:w-[22px] sm:h-[22px] shrink-0" />
    : <div className="w-5 h-5 sm:w-[22px] sm:h-[22px] rounded-full bg-zinc-100 shrink-0" />;

  if (row.nonAttack) {
    const isDefense = cat === "DEFENSE";
    const badgeText = isDefense ? t("analysis.matchupNonAttackDef") : t("analysis.matchupNonAttackStatus");
    return (
      <div className="py-2.5 border-b border-zinc-100 last:border-0">
        <div className="flex items-center gap-2 flex-wrap">
          {typeIconEl}
          <span className="text-sm font-medium text-zinc-600 leading-snug">{moveName}</span>
          <span className={`text-[10px] font-semibold rounded-full px-2 py-0.5 shrink-0 ${isDefense ? "bg-sky-100 text-sky-700" : "bg-violet-100 text-violet-700"}`}>
            {badgeText}
          </span>
        </div>
        {moveDesc && (
          <p className="text-xs text-zinc-400 mt-0.5 leading-relaxed line-clamp-3 pl-7">{moveDesc}</p>
        )}
      </div>
    );
  }

  const kill = killBadge(row.damage, defenderHp, t);
  return (
    <div className="py-2.5 border-b border-zinc-100 last:border-0">
      <div className="flex items-center justify-between gap-2 sm:gap-3">
        <span className="flex items-center gap-2 flex-1 min-w-0">
          {typeIconEl}
          <span className="text-sm font-medium text-zinc-800 leading-snug min-w-0">{moveName}</span>
        </span>
        <span className="flex items-center gap-1 shrink-0 leading-none">
          {kill && (
            <span className={`text-[10px] font-bold rounded-full px-1.5 py-0.5 ${kill.cls}`}>{kill.text}</span>
          )}
          <DamageTooltip
            damage={row.damage}
            hpPercent={row.hpPercent}
            typeMultiplier={row.typeMultiplier}
          />
        </span>
      </div>
      {moveDesc && (
        <p className="text-xs text-zinc-400 mt-0.5 leading-relaxed line-clamp-3 pl-7">{moveDesc}</p>
      )}
    </div>
  );
}

// ─── MatchupPanel ─────────────────────────────────────────────────────────────

interface Props {
  attackerMonster: MonsterOut;
  attackerTalent: TalentUpsert;
  attackerPersonality: PersonalityOut;
  attackerMoves: readonly MoveOut[];
  /** Active attacker statuses selected in the analysis inspector. */
  attackerStatuses: readonly StatusOut[];
  defender: UserMonsterCreate;
  defenderMonster: MonsterOut;
  defenderPersonality: PersonalityOut;
  defenderMoves: readonly MoveOut[];
}

export default function MatchupPanel({
  attackerMonster,
  attackerTalent,
  attackerPersonality,
  attackerMoves,
  attackerStatuses,
  defender,
  defenderMonster,
  defenderPersonality,
  defenderMoves,
}: Props) {
  const { lang, t } = useI18n();
  const location = useLocation();
  const matchupBack = encodeURIComponent(location.pathname + "?tab=vsFeatured");
  const [isReversed, setIsReversed] = useState(false);

  // Defense-reducing options for each side (only moves with dmg_reduction_pct).
  const defenderDefenseOptions = useMemo<DefenseOption[]>(() => {
    const opts: DefenseOption[] = [{ id: "none", label: t("analysis.matchupOriginal"), status: null }];
    const seen = new Set<number>();
    for (const move of defenderMoves) {
      for (const status of move.statuses ?? []) {
        if (seen.has(status.id) || !status.dmg_reduction_pct) continue;
        seen.add(status.id);
        opts.push({ id: String(status.id), label: pickName(status, lang) || status.name, status });
      }
    }
    return opts;
  }, [defenderMoves, lang, t]);

  const attackerDefenseOptions = useMemo<DefenseOption[]>(() => {
    const opts: DefenseOption[] = [{ id: "none", label: t("analysis.matchupOriginal"), status: null }];
    const seen = new Set<number>();
    for (const move of attackerMoves) {
      for (const status of move.statuses ?? []) {
        if (seen.has(status.id) || !status.dmg_reduction_pct) continue;
        seen.add(status.id);
        opts.push({ id: String(status.id), label: pickName(status, lang) || status.name, status });
      }
    }
    return opts;
  }, [attackerMoves, lang, t]);

  // Attack-boosting statuses for the featured jingling (used when reversed).
  const featuredAttackerOptions = useMemo(
    () => getAttackerStatusOptions(defenderMoves),
    [defenderMoves],
  );

  const [defDefenseId, setDefDefenseId] = useState("none");
  const [atkDefenseId, setAtkDefenseId] = useState("none");
  const [featuredAtkStatusIds, setFeaturedAtkStatusIds] = useState<number[]>([]);

  useEffect(() => {
    setDefDefenseId("none");
    setAtkDefenseId("none");
    setFeaturedAtkStatusIds([]);
    setIsReversed(false);
  }, [defender.monster_id]);

  const featuredAtkStatuses = useMemo(() => {
    const active = new Set(featuredAtkStatusIds);
    return featuredAttackerOptions.filter((s) => active.has(s.id));
  }, [featuredAttackerOptions, featuredAtkStatusIds]);

  const toggleFeaturedAtkStatus = (id: number) => {
    setFeaturedAtkStatusIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const activeDefenderStatus =
    (defenderDefenseOptions.find((o) => o.id === defDefenseId) ?? defenderDefenseOptions[0])?.status ?? null;
  const activeAttackerDefenseStatus =
    (attackerDefenseOptions.find((o) => o.id === atkDefenseId) ?? attackerDefenseOptions[0])?.status ?? null;

  // Outgoing: my jingling attacks the featured team member.
  const outgoing = useMemo(
    () => computeMatchup(
      { monster: attackerMonster, talent: attackerTalent, personality: attackerPersonality },
      attackerMoves,
      { monster: defenderMonster, talent: defender.talent, personality: defenderPersonality },
      { attackerStatuses: [...attackerStatuses], defenderStatuses: activeDefenderStatus ? [activeDefenderStatus] : [] },
    ),
    [attackerMonster, attackerTalent, attackerPersonality, attackerMoves, attackerStatuses,
     defenderMonster, defender.talent, defenderPersonality, activeDefenderStatus],
  );

  // Incoming: the featured team member attacks my jingling.
  const incoming = useMemo(
    () => computeMatchup(
      { monster: defenderMonster, talent: defender.talent, personality: defenderPersonality },
      defenderMoves,
      { monster: attackerMonster, talent: attackerTalent, personality: attackerPersonality },
      {
        attackerStatuses: featuredAtkStatuses,
        defenderStatuses: activeAttackerDefenseStatus ? [activeAttackerDefenseStatus] : [],
      },
    ),
    [defenderMonster, defender.talent, defenderPersonality, defenderMoves,
     attackerMonster, attackerTalent, attackerPersonality,
     featuredAtkStatuses, activeAttackerDefenseStatus],
  );

  const displayResult = isReversed ? incoming : outgoing;
  const displayDefenseOptions = isReversed ? attackerDefenseOptions : defenderDefenseOptions;
  const displayDefenseId = isReversed ? atkDefenseId : defDefenseId;
  const handleDefenseChange = (id: string) => {
    if (isReversed) setAtkDefenseId(id);
    else setDefDefenseId(id);
  };

  return (
    <PanelCard>
      <div className="space-y-3">
        {/* ── Monster identity header ── */}
        <div className="grid grid-cols-[1fr_28px_1fr] sm:grid-cols-[1fr_36px_1fr] items-center gap-1 sm:gap-2">
          <MonsterStrip
            monster={attackerMonster}
            sideLabel={t("analysis.matchupMyJingling")}
            dexBackUrl={`/dex/monsters/${attackerMonster.id}?from=analysis&back=${matchupBack}`}
            align="left"
          />
          <div className="flex flex-col items-center justify-center gap-0.5 text-zinc-400 select-none">
            <div className="h-px w-3 bg-zinc-300 rounded-full" />
            <span className="text-[9px] lg:text-xs font-black uppercase tracking-wider leading-none">vs</span>
            <div className="h-px w-3 bg-zinc-300 rounded-full" />
          </div>
          <MonsterStrip
            monster={defenderMonster}
            sideLabel={t("analysis.matchupFeaturedJingling")}
            dexBackUrl={`/dex/monsters/${defenderMonster.id}?from=analysis&back=${matchupBack}`}
            align="right"
          />
        </div>

        {/* ── Direction tabs ── */}
        <div className="flex rounded-lg border border-zinc-200 bg-zinc-50 p-0.5 gap-0.5">
          <button
            type="button"
            onClick={() => setIsReversed(false)}
            className={`flex-1 rounded-md py-2 px-2 text-xs sm:text-sm transition-all duration-150 cursor-pointer border ${
              !isReversed
                ? "bg-white text-zinc-800 font-semibold shadow-sm border-zinc-300"
                : "border-transparent text-zinc-400 font-medium hover:text-zinc-600 hover:bg-white/60"
            }`}
          >
            {t("analysis.matchupMyAttacks")} →
          </button>
          <button
            type="button"
            onClick={() => setIsReversed(true)}
            className={`flex-1 rounded-md py-2 px-2 text-xs sm:text-sm transition-all duration-150 cursor-pointer border ${
              isReversed
                ? "bg-white text-zinc-800 font-semibold shadow-sm border-zinc-300"
                : "border-transparent text-zinc-400 font-medium hover:text-zinc-600 hover:bg-white/60"
            }`}
          >
            ← {t("analysis.matchupTheirAttacks")}
          </button>
        </div>

        {/* ── Active attacker buff notice (my jingling direction only) ── */}
        {!isReversed && attackerStatuses.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap rounded-md bg-indigo-50 border border-indigo-200 px-2.5 py-1.5">
            <span className="text-xs font-bold uppercase tracking-wider text-indigo-600 shrink-0">
              {t("analysis.matchupMyJinglingStatus")}
            </span>
            {attackerStatuses.map((s) => (
              <span
                key={s.id}
                className="text-xs font-medium text-indigo-800 bg-indigo-100 border border-indigo-200 rounded-full px-2 py-0.5"
              >
                {pickName(s, lang) || s.name}
              </span>
            ))}
          </div>
        )}

        {/* ── Move list with damage + descriptions ── */}
        <div>
          {displayResult.moves.length === 0 ? (
            <p className="text-sm text-zinc-400 py-3 text-center">{t("analysis.matchupNoMoves")}</p>
          ) : (
            displayResult.moves.map((row, i) => (
              <MoveRow
                key={`${isReversed ? "in" : "out"}-${row.move.id}-${i}`}
                row={row}
                defenderHp={displayResult.defenderEffectiveHp}
              />
            ))
          )}
        </div>

        {/* ── Featured jingling attacker status (shown only when reversed and options exist) ── */}
        {isReversed && featuredAttackerOptions.length > 0 && (
          <div className="border-t border-zinc-100 pt-2.5">
            <p className="text-xs font-semibold text-zinc-500 mb-1.5">
              {t("analysis.matchupAttackerStatus")}
            </p>
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => setFeaturedAtkStatusIds([])}
                aria-pressed={featuredAtkStatusIds.length === 0}
                className={`text-xs rounded-full border px-2.5 py-1 transition-colors cursor-pointer ${
                  featuredAtkStatusIds.length === 0
                    ? "bg-zinc-800 text-white border-zinc-800"
                    : "bg-white text-zinc-600 border-zinc-300 hover:bg-zinc-50 hover:border-zinc-400"
                }`}
              >
                {t("analysis.matchupOriginal")}
              </button>
              {featuredAttackerOptions.map((status) => {
                const active = featuredAtkStatusIds.includes(status.id);
                return (
                  <button
                    key={status.id}
                    type="button"
                    onClick={() => toggleFeaturedAtkStatus(status.id)}
                    aria-pressed={active}
                    className={`text-xs rounded-full border px-2.5 py-1 transition-colors cursor-pointer ${
                      active
                        ? "bg-zinc-800 text-white border-zinc-800"
                        : "bg-white text-zinc-600 border-zinc-300 hover:bg-zinc-50 hover:border-zinc-400"
                    }`}
                  >
                    {pickName(status, lang) || status.name}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* ── Defender side defense toggle (shown only when options exist) ── */}
        {displayDefenseOptions.length > 1 && (
          <div className="border-t border-zinc-100 pt-2.5">
            <p className="text-xs font-semibold text-zinc-500 mb-1.5">
              {isReversed
                ? t("analysis.matchupMyMoveThisTurn")
                : t("analysis.matchupDefenderMoveThisTurn")}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {displayDefenseOptions.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => handleDefenseChange(opt.id)}
                  aria-pressed={opt.id === displayDefenseId}
                  className={`text-xs rounded-full border px-2.5 py-1 transition-colors cursor-pointer ${
                    opt.id === displayDefenseId
                      ? "bg-zinc-800 text-white border-zinc-800"
                      : "bg-white text-zinc-600 border-zinc-300 hover:bg-zinc-50 hover:border-zinc-400"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ── Disclaimer ── */}
        <p className="text-[11px] text-zinc-400 italic leading-snug">
          {t("analysis.matchupFormulaDisclaimer")}
        </p>
      </div>
    </PanelCard>
  );
}
