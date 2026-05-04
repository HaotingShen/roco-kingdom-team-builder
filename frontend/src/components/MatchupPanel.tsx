import { useEffect, useMemo, useState } from "react";
import { useI18n, pickName } from "@/i18n";
import { computeMatchup } from "@/lib/matchup";
import { typeIconUrl } from "@/lib/images";
import MonsterCard from "./MonsterCard";
import PanelCard from "./PanelCard";
import type {
  MoveCategory,
  MonsterOut,
  MoveOut,
  PersonalityOut,
  StatusOut,
  TalentUpsert,
  UserMonsterCreate,
} from "@/types";

interface Props {
  attackerMonster: MonsterOut;
  attackerTalent: TalentUpsert;
  attackerPersonality: PersonalityOut;
  attackerMoves: readonly MoveOut[];
  /** Active attacker statuses selected once in the analysis inspector. */
  attackerStatuses: readonly StatusOut[];
  defender: UserMonsterCreate;
  defenderMonster: MonsterOut;
  defenderPersonality: PersonalityOut;
  defenderMoves: readonly MoveOut[];
}

// ----- helpers -----

function hpColor(pct: number): string {
  if (pct >= 50) return "text-emerald-600 font-bold";
  if (pct >= 25) return "text-amber-500 font-bold";
  return "text-rose-500 font-bold";
}

function killLabel(damage: number, effectiveHp: number, t: (k: string) => string): string | null {
  if (damage <= 0 || effectiveHp <= 0) return null;
  if (damage >= effectiveHp) return t("analysis.matchupOneHko");
  if (damage * 2 >= effectiveHp) return t("analysis.matchupTwoHko");
  return null;
}

function normalizeMoveCategory(move: MoveOut): MoveCategory | "PHY_ATTACK" | "MAG_ATTACK" {
  const raw = (move.move_category ?? move.category ?? "") as string;
  const upper = raw.toUpperCase();
  if (upper === "PHYSICAL ATTACK") return "PHY_ATTACK";
  if (upper === "MAGIC ATTACK") return "MAG_ATTACK";
  return (upper || "STATUS") as MoveCategory;
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

  // ----- Defender Defense toggle -----
  // Only Defense-category moves with actual damage reduction are shown.
  type DefenseOption = { id: string; label: string; status: StatusOut | null };

  const defenderDefenseOptions = useMemo<DefenseOption[]>(() => {
    const options: DefenseOption[] = [
      { id: "none", label: t("analysis.matchupOriginal"), status: null },
    ];
    const seen = new Set<number>();
    for (const move of defenderMoves) {
      for (const status of move.statuses ?? []) {
        if (seen.has(status.id)) continue;
        if (!status.dmg_reduction_pct) continue;
        seen.add(status.id);
        options.push({
          id: String(status.id),
          label: pickName(status, lang) || status.name,
          status,
        });
      }
    }
    return options;
  }, [defenderMoves, lang, t]);

  // ----- User Defense toggle (for incoming direction) -----
  const userDefenseOptions = useMemo<DefenseOption[]>(() => {
    const options: DefenseOption[] = [
      { id: "none", label: t("analysis.matchupOriginal"), status: null },
    ];
    const seen = new Set<number>();
    for (const move of attackerMoves) {
      for (const status of move.statuses ?? []) {
        if (seen.has(status.id)) continue;
        if (!status.dmg_reduction_pct) continue;
        seen.add(status.id);
        options.push({
          id: String(status.id),
          label: pickName(status, lang) || status.name,
          status,
        });
      }
    }
    return options;
  }, [attackerMoves, lang, t]);

  const [activeDefenseId, setActiveDefenseId] = useState<string>("none");
  const [activeUserDefenseId, setActiveUserDefenseId] = useState<string>("none");

  useEffect(() => {
    setActiveDefenseId("none");
    setActiveUserDefenseId("none");
  }, [defender.monster_id]);

  const activeDefenseStatus =
    (defenderDefenseOptions.find((o) => o.id === activeDefenseId) ?? defenderDefenseOptions[0])?.status ?? null;
  const activeUserDefenseStatus =
    (userDefenseOptions.find((o) => o.id === activeUserDefenseId) ?? userDefenseOptions[0])?.status ?? null;

  // ----- Outgoing: my moves → them -----
  const outgoing = useMemo(
    () =>
      computeMatchup(
        { monster: attackerMonster, talent: attackerTalent, personality: attackerPersonality },
        attackerMoves,
        { monster: defenderMonster, talent: defender.talent, personality: defenderPersonality },
        {
          attackerStatuses: [...attackerStatuses],
          defenderStatuses: activeDefenseStatus ? [activeDefenseStatus] : [],
        },
      ),
    [
      attackerMonster,
      attackerTalent,
      attackerPersonality,
      attackerMoves,
      attackerStatuses,
      defenderMonster,
      defender.talent,
      defenderPersonality,
      activeDefenseStatus,
    ],
  );

  // ----- Incoming: their moves → me -----
  const incoming = useMemo(
    () =>
      computeMatchup(
        { monster: defenderMonster, talent: defender.talent, personality: defenderPersonality },
        defenderMoves,
        { monster: attackerMonster, talent: attackerTalent, personality: attackerPersonality },
        { defenderStatuses: activeUserDefenseStatus ? [activeUserDefenseStatus] : [] },
      ),
    [
      defenderMonster,
      defender.talent,
      defenderPersonality,
      defenderMoves,
      attackerMonster,
      attackerTalent,
      attackerPersonality,
      activeUserDefenseStatus,
    ],
  );

  // ----- Render helpers -----

  const renderMoveRow = (
    row: (typeof outgoing.moves)[number],
    i: number,
    effectiveHp: number,
    direction: "out" | "in",
  ) => {
    const moveName = pickName(row.move, lang) || row.move.name;
    const moveTypeName = row.move.move_type?.name ?? row.move.type?.name;
    const iconUrl = moveTypeName ? typeIconUrl(moveTypeName, 30) : null;
    const key = `${direction}-${row.move.id}-${i}`;
    const cat = normalizeMoveCategory(row.move);

    if (row.nonAttack) {
      const badge =
        cat === "DEFENSE"
          ? t("analysis.matchupNonAttackDef")
          : cat === "STATUS"
            ? t("analysis.matchupNonAttackStatus")
            : t("analysis.matchupNonAttack");
      return (
        <div
          key={key}
          className="flex items-center justify-between gap-2 text-sm text-zinc-400"
        >
          <span className="flex items-center gap-1.5 truncate min-w-0">
            {iconUrl && (
              <img src={iconUrl} alt={moveTypeName} className="w-4 h-4 shrink-0" />
            )}
            <span className="truncate">{moveName}</span>
          </span>
          <span className="shrink-0 tabular-nums text-xs bg-zinc-100 text-zinc-500 rounded px-1.5 py-0.5">
            {badge}
          </span>
        </div>
      );
    }

    const label = killLabel(row.damage, effectiveHp, t);
    return (
      <div
        key={key}
        className="flex items-center justify-between gap-2 text-sm"
      >
        <span className="flex items-center gap-1.5 truncate min-w-0 font-medium text-zinc-800">
          {iconUrl && (
            <img src={iconUrl} alt={moveTypeName} className="w-4 h-4 shrink-0" />
          )}
          <span className="truncate">{moveName}</span>
        </span>
        <span className="flex items-center gap-1.5 shrink-0 tabular-nums">
          {label && (
            <span className="text-xs font-semibold bg-rose-100 text-rose-700 rounded px-1.5 py-0.5">
              {label}
            </span>
          )}
          <span className={`font-bold ${hpColor(row.hpPercent)}`}>{row.damage}</span>
          <span className="text-zinc-400 text-xs">
            ({row.hpPercent.toFixed(1)}%)
          </span>
        </span>
      </div>
    );
  };

  const renderToggle = (
    label: string,
    options: DefenseOption[],
    activeId: string,
    setActive: (id: string) => void,
  ) => {
    if (options.length <= 1) return null;
    return (
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <span className="text-xs font-semibold text-zinc-600 mr-1">{label}</span>
        {options.map((opt) => {
          const active = opt.id === activeId;
          return (
            <button
              key={opt.id}
              type="button"
              onClick={() => setActive(opt.id)}
              aria-pressed={active}
              className={`inline-flex items-center text-xs rounded-full border px-2.5 py-0.5 transition-colors ${
                active
                  ? "bg-zinc-800 text-white border-zinc-800 shadow-sm"
                  : "bg-white text-zinc-700 border-zinc-300 hover:bg-zinc-50 hover:border-zinc-400"
              }`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    );
  };

  return (
    <PanelCard>
      <div className="grid grid-cols-1 md:grid-cols-[220px_1fr] lg:grid-cols-[260px_1fr] gap-4">
        <div>
          <MonsterCard
            monsterId={defender.monster_id}
            personalityId={defender.personality_id}
            legacyTypeId={defender.legacy_type_id}
            moveIds={[
              defender.move1_id,
              defender.move2_id,
              defender.move3_id,
              defender.move4_id,
            ]}
            talent={defender.talent}
          />
        </div>
        <div className="space-y-3 min-w-0">

          {/* Toggles */}
          {renderToggle(
            t("analysis.matchupDefenderMoveThisTurn"),
            defenderDefenseOptions,
            activeDefenseId,
            setActiveDefenseId,
          )}
          {renderToggle(
            t("analysis.matchupMyMoveThisTurn"),
            userDefenseOptions,
            activeUserDefenseId,
            setActiveUserDefenseId,
          )}

          {/* Outgoing section */}
          <div className="pt-2 border-t border-zinc-100 space-y-1.5">
            <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-1">
              {t("analysis.matchupOutgoingMoves")}
            </div>
            {outgoing.moves.length === 0 ? (
              <div className="text-sm text-zinc-500">{t("analysis.matchupNoMoves")}</div>
            ) : (
              outgoing.moves.map((row, i) =>
                renderMoveRow(row, i, outgoing.defenderEffectiveHp, "out"),
              )
            )}
          </div>

          {/* Incoming section */}
          <div className="pt-2 border-t border-zinc-100 space-y-1.5">
            <div className="text-xs font-semibold text-zinc-500 uppercase tracking-wide mb-1">
              {t("analysis.matchupIncomingMoves")}
            </div>
            {incoming.moves.length === 0 ? (
              <div className="text-sm text-zinc-500">{t("analysis.matchupNoMoves")}</div>
            ) : (
              incoming.moves.map((row, i) =>
                renderMoveRow(row, i, incoming.defenderEffectiveHp, "in"),
              )
            )}
          </div>

          {/* Formula disclaimer */}
          <p className="text-xs text-zinc-400 italic pt-1">
            {t("analysis.matchupFormulaDisclaimer")}
          </p>
        </div>
      </div>
    </PanelCard>
  );
}
