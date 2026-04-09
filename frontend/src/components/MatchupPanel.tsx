import { useEffect, useMemo, useState } from "react";
import { useI18n, pickName } from "@/i18n";
import { computeMatchup } from "@/lib/matchup";
import MonsterCard from "./MonsterCard";
import PanelCard from "./PanelCard";
import type {
  MonsterOut,
  MoveOut,
  PersonalityOut,
  StatusOut,
  TalentUpsert,
  UserMonsterCreate,
} from "@/types";

/**
 * Per-defender matchup panel (presentational).
 *
 * Layout: defender card on the left (re-using <MonsterCard> from the
 * team-builder slot grid), status toggle + per-move damage list on the
 * right. The status toggle is single-active (radio-style) — selecting
 * a status flips the defender's active status set, and the damage rows
 * recompute live via the pure pipeline in lib/matchup.ts.
 *
 * Scaling note: this component does NO fetching. All of the data it
 * needs — attacker detail, attacker personality, attacker moves, defender
 * detail, defender personality, defender moves — is passed in fully
 * hydrated by the parent. The parent (`MonsterAnalysisPage`) runs the
 * fetches once and fans the result out to every MatchupPanel it renders.
 *
 * This is critical for the upcoming featured-teams rollout: an
 * analysis-page view can mount N MatchupPanels (one per defender across
 * all featured teams), and we MUST NOT fire N × 2 queries (defender-monster,
 * defender-moves) when a single batched fetch per unique id will do.
 *
 * The panel only knows about ONE attacker × ONE defender. Featured-team
 * aggregation (rolling up multiple panels into a team score) is a
 * separate layer that doesn't live here.
 */

interface Props {
  /** Attacker monster detail (hydrated by parent). */
  attackerMonster: MonsterOut;
  /** Attacker talent from the slot. */
  attackerTalent: TalentUpsert;
  /** Attacker personality (hydrated by parent). */
  attackerPersonality: PersonalityOut;
  /** Attacker moves in slot order, with any non-picked slots dropped (hydrated by parent). */
  attackerMoves: readonly MoveOut[];

  /**
   * Defender configuration — preserved on the props for the reset-effect
   * dependency + for MonsterCard, which takes IDs only.
   */
  defender: UserMonsterCreate;
  /** Defender monster detail (hydrated by parent). */
  defenderMonster: MonsterOut;
  /** Defender personality (hydrated by parent). */
  defenderPersonality: PersonalityOut;
  /** Defender moves in slot order (hydrated by parent). */
  defenderMoves: readonly MoveOut[];
}

export default function MatchupPanel({
  attackerMonster,
  attackerTalent,
  attackerPersonality,
  attackerMoves,
  defender,
  defenderMonster,
  defenderPersonality,
  defenderMoves,
}: Props) {
  const { lang, t } = useI18n();

  // ----- Status toggle options -----
  // "Original" (no status active) plus one option per status that any of
  // the defender's moves grants. We don't pre-filter to DEFENSE-category
  // moves: per the V1 model, attack and status moves can also grant
  // self-statuses, and the toggle should expose all of them. Future
  // refinement (filter by self-vs-target) lives elsewhere.
  type ToggleOption = { id: string; label: string; status: StatusOut | null };
  const statusOptions = useMemo<ToggleOption[]>(() => {
    const options: ToggleOption[] = [
      { id: "none", label: t("analysis.matchupOriginal"), status: null },
    ];
    const seen = new Set<number>();
    for (const move of defenderMoves) {
      for (const status of move.statuses) {
        if (seen.has(status.id)) continue;
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

  const [activeStatusId, setActiveStatusId] = useState<string>("none");

  // I4: When the defender changes (different monster_id => different moves,
  // different status option list), reset the toggle back to "none". Without
  // this the user can stay on a status id that no longer exists in the new
  // defender's list — the `activeOption` fallback below catches it visually,
  // but the toggle UI highlights the wrong pill until the user clicks again.
  useEffect(() => {
    setActiveStatusId("none");
  }, [defender.monster_id]);

  // Defensive: if the active id is no longer in the list (options changed
  // but the effect hasn't run yet), fall back to "none" rather than
  // referencing a stale option.
  const activeOption =
    statusOptions.find((o) => o.id === activeStatusId) ?? statusOptions[0];
  const activeStatus = activeOption?.status ?? null;

  // ----- Run the matchup pipeline -----
  const matchup = useMemo(
    () =>
      computeMatchup(
        {
          monster: attackerMonster,
          talent: attackerTalent,
          personality: attackerPersonality,
        },
        attackerMoves,
        {
          monster: defenderMonster,
          talent: defender.talent,
          personality: defenderPersonality,
        },
        {
          defenderStatuses: activeStatus ? [activeStatus] : [],
        },
      ),
    [
      attackerMonster,
      attackerTalent,
      attackerPersonality,
      attackerMoves,
      defenderMonster,
      defender.talent,
      defenderPersonality,
      activeStatus,
    ],
  );

  // ----- Render -----
  return (
    <PanelCard>
      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-4">
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
          {/* Status toggle (top of RHS) */}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
            <span className="text-xs font-semibold text-zinc-600 mr-1">
              {t("analysis.matchupDefenderStatus")}
            </span>
            {statusOptions.map((opt) => {
              const active = opt.id === activeOption?.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => setActiveStatusId(opt.id)}
                  aria-pressed={active}
                  className={`inline-flex items-center text-xs sm:text-sm rounded-full border px-2.5 sm:px-3 py-0.5 sm:py-1 transition-colors ${
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

          {/* Damage list (rest of RHS) */}
          <div className="pt-2 border-t border-zinc-100 space-y-1.5">
            {matchup.moves.length === 0 ? (
              <div className="text-sm text-zinc-500">{t("analysis.matchupNoMoves")}</div>
            ) : (
              matchup.moves.map((row, i) => {
                const moveName = pickName(row.move, lang) || row.move.name;
                const key = `${row.move.id}-${i}`;
                if (row.nonAttack) {
                  return (
                    <div
                      key={key}
                      className="flex items-baseline justify-between gap-2 text-sm text-zinc-400"
                    >
                      <span className="truncate">{moveName}</span>
                      <span className="shrink-0 tabular-nums">
                        {t("analysis.matchupNonAttack")}
                      </span>
                    </div>
                  );
                }
                return (
                  <div
                    key={key}
                    className="flex items-baseline justify-between gap-2 text-sm"
                  >
                    <span className="truncate font-medium text-zinc-800">
                      {moveName}
                    </span>
                    <span className="shrink-0 tabular-nums">
                      <span className="font-bold text-zinc-900">{row.damage}</span>{" "}
                      <span className="text-zinc-500">
                        ({row.hpPercent.toFixed(1)}%)
                      </span>
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </PanelCard>
  );
}
