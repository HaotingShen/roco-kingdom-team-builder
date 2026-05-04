import { useMemo } from "react";
import { useI18n } from "@/i18n";
import { useMonstersByIds } from "@/hooks/useMonstersByIds";
import { useMovesByIds } from "@/hooks/useMovesByIds";
import { usePersonalities } from "@/hooks/usePersonalities";
import MatchupPanel from "@/components/MatchupPanel";
import PanelCard from "@/components/PanelCard";
import type {
  MonsterOut,
  MoveOut,
  PersonalityOut,
  StatusOut,
  TalentUpsert,
} from "@/types";
import type { MockFeaturedTeam } from "./featuredTeamsMock";

/**
 * Renders ONE active featured team's defender lineup against the configured
 * attacker.
 *
 * Owns ALL defender-side data fetching for this team:
 *   - useMonstersByIds   — every defender's monster detail (one batched
 *                          set of fetches; cache-shared with MonsterCard)
 *   - useMovesByIds      — every defender's 4 move ids, deduped/sorted into
 *                          one batched fetch
 *   - usePersonalities   — app-wide cached, just resolves the per-defender
 *                          personality_id from the same list
 *
 * Why a per-team component (instead of inlining in VsFeaturedTeamsTab):
 *   - **Mounting boundary** — switching sub-tabs unmounts this component and
 *     mounts a fresh one for the next team. Inactive teams don't fetch.
 *     React-query still caches the previous team's data, so going back is
 *     instant.
 *   - **Per-team isolation** — an error in one team's data doesn't break
 *     the sub-tab strip; the user can still click to a different team.
 *   - **Real-data swap point** — this is the component that will eventually
 *     consume `team: TeamOut` (instead of MockFeaturedTeam). The translation
 *     from `UserMonsterOut` (hydrated) → ID-only fields lives here so the
 *     change is one file in the next PR.
 */
interface Props {
  team: MockFeaturedTeam;
  attackerMonster: MonsterOut;
  attackerTalent: TalentUpsert;
  attackerPersonality: PersonalityOut;
  attackerMoves: readonly MoveOut[];
  attackerStatuses: readonly StatusOut[];
}

export default function FeaturedTeamView({
  team,
  attackerMonster,
  attackerTalent,
  attackerPersonality,
  attackerMoves,
  attackerStatuses,
}: Props) {
  const { t } = useI18n();

  // Aggregate every defender's IDs for batch fetching. Both arrays are
  // memoized on `team` so the dep arrays in the hooks below see a stable
  // identity until the user switches sub-tabs.
  const allMonsterIds = useMemo(
    () => team.user_monsters.map((um) => um.monster_id),
    [team],
  );
  const allMoveIds = useMemo(
    () =>
      team.user_monsters.flatMap((um) => [
        um.move1_id,
        um.move2_id,
        um.move3_id,
        um.move4_id,
      ]),
    [team],
  );

  const monstersResult = useMonstersByIds(allMonsterIds);
  const movesResult = useMovesByIds(allMoveIds);
  const personalitiesQ = usePersonalities();

  const isLoading =
    monstersResult.isLoading ||
    movesResult.query.isLoading ||
    personalitiesQ.isLoading;
  const isError =
    monstersResult.isError ||
    movesResult.query.isError ||
    personalitiesQ.isError;

  // Build a moves map for fast per-defender lookup. Rebuilt only when the
  // batched moves data changes.
  const moveMap = useMemo(() => {
    const m = new Map<number, MoveOut>();
    (movesResult.query.data ?? []).forEach((mv) => m.set(mv.id, mv));
    return m;
  }, [movesResult.query.data]);

  // For each defender in the team, hydrate its bundle by looking up the
  // monster + personality + ordered moves from the maps. Skip defenders
  // whose monster is missing (probably a bad mock id, or a freshly added
  // monster the local DB doesn't have yet) — we render an inline error in
  // its place rather than crashing the whole team view.
  const defenderRows = useMemo(() => {
    return team.user_monsters.map((um, idx) => {
      const monster = monstersResult.monsters.get(um.monster_id);
      const personality =
        personalitiesQ.data?.find((p) => p.id === um.personality_id) ?? null;
      const moves = [um.move1_id, um.move2_id, um.move3_id, um.move4_id]
        .map((id) => moveMap.get(id))
        .filter((mv): mv is MoveOut => !!mv);
      return {
        key: `${team.id}-${idx}`,
        defender: um,
        monster,
        personality,
        moves,
      };
    });
  }, [team, monstersResult.monsters, moveMap, personalitiesQ.data]);

  // Placeholder info panel — leave the body as a single hint line for now.
  // Real implementation (magic item, team-level matchups, win conditions)
  // comes in the next PR alongside the real /teams/featured fetch.
  const infoPanel = (
    <PanelCard title={team.name}>
      <div className="text-sm text-zinc-500">
        {t("analysis.featuredTeamInfoPlaceholder")}
      </div>
    </PanelCard>
  );

  if (isLoading) {
    return (
      <div className="space-y-3">
        {infoPanel}
        <PanelCard>
          <div className="text-sm text-zinc-500">{t("common.loading")}</div>
        </PanelCard>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="space-y-3">
        {infoPanel}
        <PanelCard>
          <div className="text-sm text-rose-600">
            {t("analysis.matchupDataUnavailable")}
          </div>
        </PanelCard>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {infoPanel}
      {defenderRows.map((row) =>
        row.monster && row.personality ? (
          <MatchupPanel
            key={row.key}
            attackerMonster={attackerMonster}
            attackerTalent={attackerTalent}
            attackerPersonality={attackerPersonality}
            attackerMoves={attackerMoves}
            attackerStatuses={attackerStatuses}
            defender={row.defender}
            defenderMonster={row.monster}
            defenderPersonality={row.personality}
            defenderMoves={row.moves}
          />
        ) : (
          <PanelCard key={row.key}>
            <div className="text-sm text-rose-600">
              {t("analysis.matchupDataUnavailable")}
            </div>
          </PanelCard>
        ),
      )}
    </div>
  );
}
