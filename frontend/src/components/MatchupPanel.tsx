import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n, pickName } from "@/i18n";
import { QUERY_KEYS } from "@/lib/constants";
import { computeMatchup } from "@/lib/matchup";
import MonsterCard from "./MonsterCard";
import type {
  MonsterOut,
  MoveOut,
  PersonalityOut,
  StatusOut,
  TalentUpsert,
  UserMonsterCreate,
} from "@/types";

/**
 * Per-defender matchup panel.
 *
 * Layout: defender card on the left (re-using <MonsterCard> from the
 * team-builder slot grid), status toggle + per-move damage list on the
 * right. The status toggle is single-active (radio-style) — selecting
 * a status flips the defender's active status set, and the damage rows
 * recompute live via the pure pipeline in lib/matchup.ts.
 *
 * Inputs:
 *   - attacker: the user's slot (read from useBuilderStore upstream)
 *     plus its already-fetched MonsterOut detail (passed in to share
 *     the parent's react-query cache)
 *   - defender: a UserMonsterCreate config — currently a hardcoded test
 *     constant from VsFeaturedTeamsTab; later this becomes one element
 *     of a featured team's user_monsters array, no panel changes needed
 *
 * The panel only knows about ONE attacker × ONE defender. Featured-team
 * aggregation (rolling up multiple panels into a team score) is a
 * separate layer that doesn't exist yet.
 */

interface Props {
  /** Attacker monster (already fetched by parent — for cache sharing). */
  attackerMonster: MonsterOut;
  /** Attacker talent from the slot. */
  attackerTalent: TalentUpsert;
  /** Attacker personality_id from the slot. */
  attackerPersonalityId: number;
  /** Attacker move ids from the slot (4 entries). */
  attackerMoveIds: ReadonlyArray<number | 0 | undefined | null>;

  /** Defender configuration — IDs only, like a builder slot. */
  defender: UserMonsterCreate;
}

export default function MatchupPanel({
  attackerMonster,
  attackerTalent,
  attackerPersonalityId,
  attackerMoveIds,
  defender,
}: Props) {
  const { lang, t } = useI18n();

  // ----- Defender data fetches (share react-query caches with the rest of the app) -----
  const defenderMonsterQ = useQuery({
    queryKey: QUERY_KEYS.MONSTER_DETAIL(defender.monster_id),
    queryFn: () =>
      endpoints
        .monsterById(defender.monster_id)
        .then((r) => r.data as MonsterOut),
    enabled: defender.monster_id > 0,
  });

  // Personalities — one fetch, shared across the whole app via the same key.
  const personalitiesQ = useQuery({
    queryKey: QUERY_KEYS.PERSONALITIES,
    queryFn: () =>
      endpoints.personalities().then((r) => r.data as PersonalityOut[]),
  });

  // Attacker moves — for the damage list rows.
  const attackerMoveIdsList = useMemo(
    () =>
      Array.from(
        new Set(
          attackerMoveIds.filter(
            (x): x is number => typeof x === "number" && x > 0,
          ),
        ),
      ),
    [attackerMoveIds],
  );
  const attackerMovesQ = useQuery({
    queryKey: ["moves-by-ids", attackerMoveIdsList.join(",")],
    queryFn: () =>
      endpoints
        .moves({ ids: attackerMoveIdsList.join(",") })
        .then((r) => (r.data?.items ?? r.data) as MoveOut[]),
    enabled: attackerMoveIdsList.length > 0,
  });

  // Defender moves — we need their .statuses to populate the toggle.
  const defenderMoveIdsList = useMemo(
    () =>
      Array.from(
        new Set(
          [
            defender.move1_id,
            defender.move2_id,
            defender.move3_id,
            defender.move4_id,
          ].filter((x): x is number => typeof x === "number" && x > 0),
        ),
      ),
    [defender],
  );
  const defenderMovesQ = useQuery({
    queryKey: ["moves-by-ids", defenderMoveIdsList.join(",")],
    queryFn: () =>
      endpoints
        .moves({ ids: defenderMoveIdsList.join(",") })
        .then((r) => (r.data?.items ?? r.data) as MoveOut[]),
    enabled: defenderMoveIdsList.length > 0,
  });

  const attackerPersonality = useMemo(
    () =>
      personalitiesQ.data?.find((p) => p.id === attackerPersonalityId) ?? null,
    [personalitiesQ.data, attackerPersonalityId],
  );
  const defenderPersonality = useMemo(
    () =>
      personalitiesQ.data?.find((p) => p.id === defender.personality_id) ??
      null,
    [personalitiesQ.data, defender.personality_id],
  );

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
    for (const move of defenderMovesQ.data ?? []) {
      for (const status of move.statuses ?? []) {
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
  }, [defenderMovesQ.data, lang, t]);

  const [activeStatusId, setActiveStatusId] = useState<string>("none");
  // Defensive: if the active id is no longer in the list (defender changed),
  // fall back to "none" rather than referencing a stale option.
  const activeOption =
    statusOptions.find((o) => o.id === activeStatusId) ?? statusOptions[0];
  const activeStatus = activeOption?.status ?? null;

  // ----- Run the matchup pipeline -----
  const matchup = useMemo(() => {
    if (
      !defenderMonsterQ.data ||
      !attackerPersonality ||
      !defenderPersonality ||
      !attackerMovesQ.data
    ) {
      return null;
    }
    return computeMatchup(
      {
        monster: attackerMonster,
        talent: attackerTalent,
        personality: attackerPersonality,
      },
      attackerMovesQ.data,
      {
        monster: defenderMonsterQ.data,
        talent: defender.talent,
        personality: defenderPersonality,
      },
      {
        defenderStatuses: activeStatus ? [activeStatus] : [],
      },
    );
  }, [
    attackerMonster,
    attackerTalent,
    attackerPersonality,
    attackerMovesQ.data,
    defenderMonsterQ.data,
    defender.talent,
    defenderPersonality,
    activeStatus,
  ]);

  // ----- Render -----
  const card = (body: React.ReactNode) => (
    <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4">
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
        <div className="space-y-3 min-w-0">{body}</div>
      </div>
    </section>
  );

  // Loading: any required data still in flight.
  if (
    defenderMonsterQ.isLoading ||
    personalitiesQ.isLoading ||
    attackerMovesQ.isLoading ||
    defenderMovesQ.isLoading
  ) {
    return card(<div className="text-sm text-zinc-500">{t("common.loading")}</div>);
  }

  // Required data unavailable.
  if (
    defenderMonsterQ.isError ||
    personalitiesQ.isError ||
    attackerMovesQ.isError ||
    defenderMovesQ.isError ||
    !matchup
  ) {
    return card(
      <div className="text-sm text-rose-600">
        {t("analysis.matchupDataUnavailable")}
      </div>,
    );
  }

  return card(
    <>
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
    </>,
  );
}
