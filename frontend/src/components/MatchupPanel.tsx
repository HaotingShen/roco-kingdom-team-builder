import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAnalysisStore } from "@/features/builder/analysisStore";
import { useI18n, pickName, pickDesc } from "@/i18n";
import { computeMatchup } from "@/lib/matchup";
import { computeMoveDamage } from "@/lib/damageCalc";
import { computeEffectiveStats } from "@/lib/effectiveStats";
import { setsFor } from "@/lib/typeEffectiveness";
import { getAttackerStatusOptions } from "@/lib/attackerStatusOptions";
import { typeIconUrl, monsterImageFallbackChain, monsterPlaceholder, moveSubIconUrl } from "@/lib/images";
import { useLocalizedPath } from "@/lib/locale";
import PanelCard from "./PanelCard";
import type { MoveMatchupResult } from "@/lib/matchup";
import type {
  MonsterOut,
  MoveOut,
  PersonalityOut,
  StatusOut,
  TalentUpsert,
  TypeOut,
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

function AltDamageTooltip({ damage, hpPercent }: { damage: number; hpPercent: number }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

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
      <span className="text-sm font-bold tabular-nums text-violet-500">{damage}</span>
      <span className="text-sm tabular-nums text-violet-500">({hpPercent.toFixed(1)}%)</span>
      <span
        className={`pointer-events-none absolute z-20 bottom-full right-0 mb-2 w-max max-w-[220px] rounded-md bg-zinc-800 px-2.5 py-1.5 text-[11px] leading-snug text-white shadow-lg transition-opacity duration-150 ${
          open ? "opacity-100" : "opacity-0"
        } group-hover:opacity-100`}
      >
        {t("analysis.matchupConditionalHint")}
        <span className="absolute top-full right-3 border-4 border-transparent border-t-zinc-800" />
      </span>
    </span>
  );
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
      <span className={`text-sm tabular-nums ${colorCls}`}>({hpPercent.toFixed(1)}%)</span>

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

// ─── PowerFormulaIcon ─────────────────────────────────────────────────────────

function PowerFormulaIcon({
  formula,
  effectivePower,
  statDiff,
}: {
  formula: "speed_diff" | "phy_def_diff" | "energy";
  effectivePower: number;
  statDiff?: number;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  let label = "";
  if (formula === "speed_diff" && statDiff !== undefined) {
    const sign = statDiff >= 0 ? "+" : "";
    label = t("analysis.matchupFormulaSpeedDiff")
      .replace("{sign}", sign)
      .replace("{diff}", String(statDiff))
      .replace("{power}", String(effectivePower));
  } else if (formula === "phy_def_diff" && statDiff !== undefined) {
    const sign = statDiff >= 0 ? "+" : "";
    label = t("analysis.matchupFormulaPhyDefDiff")
      .replace("{sign}", sign)
      .replace("{diff}", String(statDiff))
      .replace("{power}", String(effectivePower));
  }

  if (!label) return null;

  return (
    <span ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-3.5 h-3.5 rounded-full border border-zinc-300 bg-white text-zinc-400 hover:text-zinc-600 text-[9px] font-bold leading-none flex items-center justify-center cursor-pointer transition-colors"
        aria-label="Formula info"
      >
        i
      </button>
      {open && (
        <span className="absolute z-20 bottom-full left-1/2 -translate-x-1/2 mb-2 whitespace-nowrap rounded-md bg-zinc-800 px-2 py-1 text-[11px] leading-snug text-white shadow-lg">
          {label}
          <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-zinc-800" />
        </span>
      )}
    </span>
  );
}

// ─── MoveRow ──────────────────────────────────────────────────────────────────

function MoveRow({
  row,
  defenderHp,
  magicEnergyLevel,
  onMagicEnergyChange,
}: {
  row: MoveMatchupResult;
  defenderHp: number;
  magicEnergyLevel?: number;
  onMagicEnergyChange?: (level: number) => void;
}) {
  const { lang, t } = useI18n();

  const moveName = pickName(row.move, lang) || row.move.name;
  const moveDesc = pickDesc(row.move, lang);
  const moveTypeName = row.move.move_type?.name ?? row.move.type?.name;
  const typeIcon = moveTypeName ? typeIconUrl(moveTypeName, 30) : null;
  const cat = normalizeCat(row.move);

  const catIconFile: Record<string, string> = {
    PHY_ATTACK: "physical-attack",
    MAG_ATTACK: "magic-attack",
    DEFENSE: "defense",
    STATUS: "status",
  };
  const catIconUrl = moveSubIconUrl(`${catIconFile[cat] ?? "status"}.png`);

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
  const comboCount = row.baseCombo ?? 1;
  return (
    <div className="py-2.5 border-b border-zinc-100 last:border-0">
      <div className="flex items-center justify-between gap-2 sm:gap-3">
        <span className="flex items-center gap-2 flex-1 min-w-0">
          {typeIconEl}
          <span className="text-sm font-medium text-zinc-800 leading-snug min-w-0">{moveName}</span>
          {(cat === "PHY_ATTACK" || cat === "MAG_ATTACK") && (row.formulaAnnotation?.effectivePower ?? row.move.power) != null && (
            <span className="flex items-center gap-1 shrink-0 ml-1">
              <img src={catIconUrl} alt={cat} className="w-3 h-3 opacity-80" />
              <span className="text-xs font-medium text-zinc-500 tabular-nums">
                {row.formulaAnnotation?.effectivePower ?? row.move.power}
              </span>
              {row.formulaAnnotation && row.formulaAnnotation.formula !== "energy" && (
                <PowerFormulaIcon
                  formula={row.formulaAnnotation.formula}
                  effectivePower={row.formulaAnnotation.effectivePower}
                  statDiff={row.formulaAnnotation.statDiff}
                />
              )}
            </span>
          )}
          {comboCount > 1 && (
            <span className="text-[10px] font-semibold rounded-full bg-zinc-100 text-zinc-500 px-1.5 py-0.5 shrink-0">
              x{comboCount}
            </span>
          )}
        </span>
        <span className="flex items-center gap-1.5 shrink-0">
          {kill && (
            <span className={`inline-flex items-center text-[10px] font-bold rounded-full px-1.5 py-0.5 ${kill.cls}`}>{kill.text}</span>
          )}
          <span className="inline-flex items-center text-xs text-zinc-400 select-none">{t("analysis.matchupDmgLabel")}</span>
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
      {row.move.power_formula === "energy" && onMagicEnergyChange && (
        <div className="flex items-center gap-2 pl-7 mt-1">
          <span className="text-xs text-zinc-400 shrink-0">{t("analysis.matchupEnergyLabel")}</span>
          <select
            value={magicEnergyLevel ?? 10}
            onChange={(e) => onMagicEnergyChange(Number(e.target.value))}
            className="border border-zinc-300 rounded px-1 py-0 text-xs text-zinc-600 bg-white cursor-pointer focus:outline-none focus:ring-1 focus:ring-zinc-400"
          >
            {Array.from({ length: 11 }, (_, i) => (
              <option key={i} value={i}>{i}</option>
            ))}
          </select>
        </div>
      )}
      {row.altDamage != null && row.altCondition && (
        <div className="flex items-center justify-between gap-2 sm:gap-3 pl-7 mt-1">
          <span className="text-xs text-violet-500 truncate">
            {lang === "zh" ? row.altCondition.zh : row.altCondition.en}
          </span>
          <span className="flex items-center gap-1.5 shrink-0">
            <span className="inline-flex items-center text-xs text-zinc-400 select-none">{t("analysis.matchupDmgLabel")}</span>
            <AltDamageTooltip
              damage={row.altDamage}
              hpPercent={row.altHpPercent ?? 0}
            />
          </span>
        </div>
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
  /** The attacker's selected legacy type — needed for Willpower Impact type. */
  attackerLegacyType?: TypeOut | null;
  /** Whether Willpower Enhancement magic item is active for the attacker. */
  willpowerActive?: boolean;
  defender: UserMonsterCreate;
  defenderMonster: MonsterOut;
  defenderPersonality: PersonalityOut;
  defenderMoves: readonly MoveOut[];
  /** Pre-fetched leader-form MonsterOut for the defender. When provided, a toggle
   *  appears so the user can switch between regular and leader form calculations. */
  defenderLeaderMonster?: MonsterOut;
  /** Which analysis tab to link back to in Dex URLs. Defaults to "vsFeatured". */
  tabKey?: string;
  /** Override the defender side-label. Defaults to the "Featured" translation. */
  defenderSideLabel?: string;
}

export default function MatchupPanel({
  attackerMonster,
  attackerTalent,
  attackerPersonality,
  attackerMoves,
  attackerStatuses,
  attackerLegacyType,
  willpowerActive,
  defender,
  defenderMonster,
  defenderPersonality,
  defenderMoves,
  defenderLeaderMonster,
  tabKey = "vsFeatured",
  defenderSideLabel,
}: Props) {
  const { lang, t } = useI18n();
  const location = useLocation();
  const localized = useLocalizedPath();
  const matchupBack = encodeURIComponent(location.pathname + `?tab=${tabKey}`);

  // Persistent state — survives navigation away and back within the same session.
  // Key is unique per attacker slot (encoded in pathname) + defender monster.
  // The locale prefix is stripped so switching language preserves panel state.
  const pathKey = location.pathname.replace(/^\/(en|zh)(?=\/|$)/, "") || "/";
  const storeKey = `${pathKey}:${defender.monster_id}`;
  // Imperative read — no reactive subscription; value only matters for useState init.
  const stored = useAnalysisStore.getState().matchupStates[storeKey];

  const [isReversed, setIsReversed] = useState(stored?.isReversed ?? false);
  const [showDefLeaderForm, setShowDefLeaderForm] = useState(stored?.defShowLeaderForm ?? false);

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

  // Opponent debuff statuses (affect=opponent, reduce phy_def or mag_def).
  // Outgoing: debuffs my jingling can apply to the featured jingling.
  const outgoingOpponentDebuffOptions = useMemo<StatusOut[]>(() => {
    const seen = new Set<number>();
    const opts: StatusOut[] = [];
    for (const move of attackerMoves) {
      for (const status of move.statuses ?? []) {
        if (
          seen.has(status.id) ||
          status.affect !== "opponent" ||
          status.usage === "move_specific" ||
          (status.phy_def_boost >= 0 && status.mag_def_boost >= 0)
        ) continue;
        seen.add(status.id);
        opts.push(status);
      }
    }
    return opts;
  }, [attackerMoves]);

  // Incoming: debuffs featured jingling can apply to my jingling.
  const incomingOpponentDebuffOptions = useMemo<StatusOut[]>(() => {
    const seen = new Set<number>();
    const opts: StatusOut[] = [];
    for (const move of defenderMoves) {
      for (const status of move.statuses ?? []) {
        if (
          seen.has(status.id) ||
          status.affect !== "opponent" ||
          status.usage === "move_specific" ||
          (status.phy_def_boost >= 0 && status.mag_def_boost >= 0)
        ) continue;
        seen.add(status.id);
        opts.push(status);
      }
    }
    return opts;
  }, [defenderMoves]);

  const [defDefenseId, setDefDefenseId] = useState(stored?.defDefenseId ?? "none");
  const [atkDefenseId, setAtkDefenseId] = useState(stored?.atkDefenseId ?? "none");
  const [featuredAtkStatusIds, setFeaturedAtkStatusIds] = useState<number[]>(stored?.featuredAtkStatusIds ?? []);
  const [outgoingDebuffIds, setOutgoingDebuffIds] = useState<number[]>(stored?.outgoingDebuffIds ?? []);
  const [incomingDebuffIds, setIncomingDebuffIds] = useState<number[]>(stored?.incomingDebuffIds ?? []);
  const [magicEnergyLevel, setMagicEnergyLevel] = useState(stored?.magicEnergyLevel ?? 10);

  // When the defender changes within a mounted component (vsCustom tab, cached
  // monster data): restore previously stored state for the new defender, or
  // reset to defaults if never visited. Skip on initial mount to preserve the
  // state already loaded from the store via useState.
  const mountedMonsterIdRef = useRef(defender.monster_id);
  useEffect(() => {
    if (mountedMonsterIdRef.current === defender.monster_id) return;
    mountedMonsterIdRef.current = defender.monster_id;
    const saved = useAnalysisStore.getState().matchupStates[storeKey];
    setIsReversed(saved?.isReversed ?? false);
    setShowDefLeaderForm(saved?.defShowLeaderForm ?? false);
    setDefDefenseId(saved?.defDefenseId ?? "none");
    setAtkDefenseId(saved?.atkDefenseId ?? "none");
    setFeaturedAtkStatusIds(saved?.featuredAtkStatusIds ?? []);
    setOutgoingDebuffIds(saved?.outgoingDebuffIds ?? []);
    setIncomingDebuffIds(saved?.incomingDebuffIds ?? []);
    setMagicEnergyLevel(saved?.magicEnergyLevel ?? 10);
  }, [defender.monster_id, storeKey]);

  // Sync current state to the store imperatively — no reactive subscription needed.
  useEffect(() => {
    useAnalysisStore.getState().setMatchupState(storeKey, {
      isReversed, defShowLeaderForm: showDefLeaderForm,
      defDefenseId, atkDefenseId,
      featuredAtkStatusIds, outgoingDebuffIds, incomingDebuffIds,
      magicEnergyLevel,
    });
  }, [storeKey, isReversed, showDefLeaderForm, defDefenseId, atkDefenseId,
      featuredAtkStatusIds, outgoingDebuffIds, incomingDebuffIds, magicEnergyLevel]);

  const featuredAtkStatuses = useMemo(() => {
    const active = new Set(featuredAtkStatusIds);
    return featuredAttackerOptions.filter((s) => active.has(s.id));
  }, [featuredAttackerOptions, featuredAtkStatusIds]);

  const activeOutgoingDebuffs = useMemo(() => {
    const active = new Set(outgoingDebuffIds);
    return outgoingOpponentDebuffOptions.filter((s) => active.has(s.id));
  }, [outgoingOpponentDebuffOptions, outgoingDebuffIds]);

  const activeIncomingDebuffs = useMemo(() => {
    const active = new Set(incomingDebuffIds);
    return incomingOpponentDebuffOptions.filter((s) => active.has(s.id));
  }, [incomingOpponentDebuffOptions, incomingDebuffIds]);

  // Resolved defender: switches to leader form when the toggle is ON and data is available.
  const resolvedDefenderMonster = showDefLeaderForm && defenderLeaderMonster
    ? defenderLeaderMonster
    : defenderMonster;

  // Willpower Impact damage — computed only when willpowerActive and legacy type is known.
  const willpowerDamage = useMemo(() => {
    if (!willpowerActive || !attackerLegacyType || attackerLegacyType.name === "Leader") return null;
    const atkStats = computeEffectiveStats(attackerMonster, attackerTalent, attackerPersonality);
    const isMagic = atkStats.mag_atk >= atkStats.phy_atk;
    const atkValue = isMagic ? atkStats.mag_atk : atkStats.phy_atk;
    const defMainSets = resolvedDefenderMonster.main_type ? setsFor(resolvedDefenderMonster.main_type) : null;
    const defSubSets = resolvedDefenderMonster.sub_type ? setsFor(resolvedDefenderMonster.sub_type) : null;
    if (!defMainSets) return null;
    const defValue = isMagic
      ? computeEffectiveStats(resolvedDefenderMonster, defender.talent, defenderPersonality).mag_def
      : computeEffectiveStats(resolvedDefenderMonster, defender.talent, defenderPersonality).phy_def;
    const defHp = computeEffectiveStats(resolvedDefenderMonster, defender.talent, defenderPersonality).hp;
    const base = computeMoveDamage({
      movePower: 80,
      moveTypeName: attackerLegacyType.name,
      isMagic,
      attackerAtk: atkValue,
      attackerMainType: attackerMonster.main_type?.name ?? "",
      attackerSubType: attackerMonster.sub_type?.name ?? null,
      defenderDef: defValue,
      defenderMainSets: defMainSets,
      defenderSubSets: defSubSets,
      attackerStatuses: [...attackerStatuses],
      defenderStatuses: activeOutgoingDebuffs.length > 0 ? activeOutgoingDebuffs : undefined,
    });
    const counter = computeMoveDamage({
      movePower: 200,
      moveTypeName: attackerLegacyType.name,
      isMagic,
      attackerAtk: atkValue,
      attackerMainType: attackerMonster.main_type?.name ?? "",
      attackerSubType: attackerMonster.sub_type?.name ?? null,
      defenderDef: defValue,
      defenderMainSets: defMainSets,
      defenderSubSets: defSubSets,
      attackerStatuses: [...attackerStatuses],
      defenderStatuses: activeOutgoingDebuffs.length > 0 ? activeOutgoingDebuffs : undefined,
    });
    return {
      isMagic,
      damage: base.damage,
      hpPercent: defHp > 0 ? (base.damage / defHp) * 100 : 0,
      typeMultiplier: base.typeMultiplier,
      counterDamage: counter.damage,
      counterHpPercent: defHp > 0 ? (counter.damage / defHp) * 100 : 0,
      defHp,
    };
  }, [willpowerActive, attackerLegacyType, attackerMonster, attackerTalent, attackerPersonality,
      resolvedDefenderMonster, defender.talent, defenderPersonality, attackerStatuses, activeOutgoingDebuffs]);

  const toggleFeaturedAtkStatus = (id: number) => {
    setFeaturedAtkStatusIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const toggleOutgoingDebuff = (id: number) => {
    setOutgoingDebuffIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const toggleIncomingDebuff = (id: number) => {
    setIncomingDebuffIds((prev) =>
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
      { monster: resolvedDefenderMonster, talent: defender.talent, personality: defenderPersonality },
      {
        attackerStatuses: [...attackerStatuses],
        defenderStatuses: [
          ...(activeDefenderStatus ? [activeDefenderStatus] : []),
          ...activeOutgoingDebuffs,
        ],
        magicEnergyLevel,
      },
    ),
    [attackerMonster, attackerTalent, attackerPersonality, attackerMoves, attackerStatuses,
     resolvedDefenderMonster, defender.talent, defenderPersonality, activeDefenderStatus,
     activeOutgoingDebuffs, magicEnergyLevel],
  );

  // Incoming: the featured team member attacks my jingling.
  const incoming = useMemo(
    () => computeMatchup(
      { monster: resolvedDefenderMonster, talent: defender.talent, personality: defenderPersonality },
      defenderMoves,
      { monster: attackerMonster, talent: attackerTalent, personality: attackerPersonality },
      {
        attackerStatuses: featuredAtkStatuses,
        defenderStatuses: [
          ...(activeAttackerDefenseStatus ? [activeAttackerDefenseStatus] : []),
          ...activeIncomingDebuffs,
        ],
        magicEnergyLevel,
      },
    ),
    [resolvedDefenderMonster, defender.talent, defenderPersonality, defenderMoves,
     attackerMonster, attackerTalent, attackerPersonality,
     featuredAtkStatuses, activeAttackerDefenseStatus, activeIncomingDebuffs, magicEnergyLevel],
  );

  const displayResult = isReversed ? incoming : outgoing;
  const displayDefenseOptions = isReversed ? attackerDefenseOptions : defenderDefenseOptions;
  const displayDefenseId = isReversed ? atkDefenseId : defDefenseId;
  const handleDefenseChange = (id: string) => {
    if (isReversed) setAtkDefenseId(id);
    else setDefDefenseId(id);
  };

  const sameMonster = attackerMonster.id === resolvedDefenderMonster.id;
  const atkName = pickName(attackerMonster, lang) || attackerMonster.name;
  const defName = pickName(resolvedDefenderMonster, lang) || resolvedDefenderMonster.name;
  const atkNameLabeled = sameMonster ? atkName + (lang === "zh" ? "（我方）" : " (Mine)") : atkName;
  const defNameLabeled = sameMonster ? defName + (lang === "zh" ? "（防守方）" : " (Defender)") : defName;
  const defAsAtkNameLabeled = sameMonster ? defName + (lang === "zh" ? "（攻击方）" : " (Attacker)") : defName;

  return (
    <PanelCard>
      <div className="space-y-3">
        {/* ── Monster identity header ── */}
        <div className="grid grid-cols-[1fr_28px_1fr] sm:grid-cols-[1fr_36px_1fr] items-center gap-1 sm:gap-2">
          <MonsterStrip
            monster={attackerMonster}
            sideLabel={t("analysis.matchupMyJingling")}
            dexBackUrl={localized(`/dex/monsters/${attackerMonster.id}`) + `?from=analysis&back=${matchupBack}`}
            align="left"
          />
          <div className="flex flex-col items-center justify-center gap-0.5 text-zinc-400 select-none">
            <div className="h-px w-3 bg-zinc-300 rounded-full" />
            <span className="text-[9px] lg:text-xs font-black uppercase tracking-wider leading-none">vs</span>
            <div className="h-px w-3 bg-zinc-300 rounded-full" />
          </div>
          <MonsterStrip
            monster={resolvedDefenderMonster}
            sideLabel={defenderSideLabel ?? t("analysis.matchupFeaturedJingling")}
            dexBackUrl={localized(`/dex/monsters/${resolvedDefenderMonster.id}`) + `?from=analysis&back=${matchupBack}`}
            align="right"
          />
        </div>

        {/* ── Defender leader form toggle — only when leader form data is available ── */}
        {defenderLeaderMonster && (
          <div className="flex items-center justify-end gap-3 rounded-lg border border-rose-100 bg-rose-50 px-3 py-2">
            <span className="text-xs font-semibold text-rose-500 uppercase tracking-wide shrink-0">
              {t("analysis.matchupDefenderFormLabel")}
            </span>
            <div className="flex items-center gap-2">
              <span
                className={`text-xs cursor-pointer select-none transition-colors duration-150 ${
                  !showDefLeaderForm ? "font-semibold text-zinc-800" : "text-zinc-400"
                }`}
                onClick={() => setShowDefLeaderForm(false)}
              >
                {t("analysis.regularForm")}
              </span>
              <button
                type="button"
                role="switch"
                aria-checked={showDefLeaderForm}
                onClick={() => setShowDefLeaderForm((v) => !v)}
                className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-rose-400 ${
                  showDefLeaderForm ? "bg-rose-500" : "bg-zinc-300"
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-sm transition-transform duration-200 ${
                    showDefLeaderForm ? "translate-x-4" : "translate-x-0"
                  }`}
                />
              </button>
              <span
                className={`text-xs cursor-pointer select-none transition-colors duration-150 ${
                  showDefLeaderForm ? "font-semibold text-zinc-800" : "text-zinc-400"
                }`}
                onClick={() => setShowDefLeaderForm(true)}
              >
                {t("analysis.leaderForm")}
              </span>
            </div>
          </div>
        )}

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
                magicEnergyLevel={magicEnergyLevel}
                onMagicEnergyChange={setMagicEnergyLevel}
              />
            ))
          )}
        </div>

        {/* ── Willpower Impact section (outgoing direction only) ── */}
        {!isReversed && willpowerDamage && attackerLegacyType && (
          <div className="border-t border-violet-100 pt-2.5 space-y-1">
            <p className="text-xs font-semibold text-violet-500 mb-1.5">
              {t("analysis.matchupWillpowerTitle")}
            </p>
            <div className="flex items-center justify-between gap-2 sm:gap-3">
              <span className="flex items-center gap-2 flex-1 min-w-0">
                {(() => {
                  const icon = typeIconUrl(attackerLegacyType.name, 30);
                  return icon
                    ? <img src={icon} alt={attackerLegacyType.name} className="w-5 h-5 sm:w-[22px] sm:h-[22px] shrink-0" />
                    : <div className="w-5 h-5 sm:w-[22px] sm:h-[22px] rounded-full bg-zinc-100 shrink-0" />;
                })()}
                <span className="text-sm font-medium text-zinc-800 leading-snug min-w-0">
                  {t("analysis.matchupWillpowerMoveName")}
                </span>
                <span className="flex items-center gap-1 shrink-0 ml-1">
                  <img
                    src={moveSubIconUrl(`${willpowerDamage.isMagic ? "magic-attack" : "physical-attack"}.png`)}
                    alt={willpowerDamage.isMagic ? "MAG_ATTACK" : "PHY_ATTACK"}
                    className="w-3 h-3 opacity-80"
                  />
                  <span className="text-xs font-medium text-zinc-500 tabular-nums">80</span>
                </span>
              </span>
              <span className="flex items-center gap-1.5 shrink-0">
                <span className="inline-flex items-center text-xs text-zinc-400 select-none">{t("analysis.matchupDmgLabel")}</span>
                <DamageTooltip
                  damage={willpowerDamage.damage}
                  hpPercent={willpowerDamage.hpPercent}
                  typeMultiplier={willpowerDamage.typeMultiplier}
                />
              </span>
            </div>
            <div className="flex items-center justify-between gap-2 sm:gap-3 pl-7 mt-1">
              <span className="text-xs text-violet-500 truncate">
                {t("analysis.matchupWillpowerCounter")}
              </span>
              <span className="flex items-center gap-1.5 shrink-0">
                <span className="inline-flex items-center text-xs text-zinc-400 select-none">{t("analysis.matchupDmgLabel")}</span>
                <AltDamageTooltip
                  damage={willpowerDamage.counterDamage}
                  hpPercent={willpowerDamage.counterHpPercent}
                />
              </span>
            </div>
          </div>
        )}

        {/* ── Opponent debuff toggles ── */}
        {!isReversed && outgoingOpponentDebuffOptions.length > 0 && (
          <div className="border-t border-zinc-100 pt-2.5">
            <p className="text-xs font-semibold text-zinc-500 mb-1.5">
              {t("analysis.matchupOpponentDebuffs")}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {outgoingOpponentDebuffOptions.map((status) => {
                const active = outgoingDebuffIds.includes(status.id);
                return (
                  <button
                    key={status.id}
                    type="button"
                    onClick={() => toggleOutgoingDebuff(status.id)}
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
        {isReversed && incomingOpponentDebuffOptions.length > 0 && (
          <div className="border-t border-zinc-100 pt-2.5">
            <p className="text-xs font-semibold text-zinc-500 mb-1.5">
              {t("analysis.matchupOpponentDebuffs")}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {incomingOpponentDebuffOptions.map((status) => {
                const active = incomingDebuffIds.includes(status.id);
                return (
                  <button
                    key={status.id}
                    type="button"
                    onClick={() => toggleIncomingDebuff(status.id)}
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

        {/* ── Featured jingling attacker status (shown only when reversed and options exist) ── */}
        {isReversed && featuredAttackerOptions.length > 0 && (
          <div className="border-t border-zinc-100 pt-2.5">
            <p className="text-xs font-semibold text-zinc-500 mb-1.5">
              {t("analysis.matchupAttackerStatusNamed", { name: defAsAtkNameLabeled })}
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
                ? t("analysis.matchupMoveThisTurn", { name: atkNameLabeled })
                : t("analysis.matchupMoveThisTurn", { name: defNameLabeled })}
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
