import { useMemo } from "react";
import { useI18n } from "@/i18n";
import { useMonstersByIds } from "@/hooks/useMonstersByIds";
import MatchupPanel from "@/components/MatchupPanel";
import PanelCard from "@/components/PanelCard";
import type {
  MonsterOut,
  MoveOut,
  PersonalityOut,
  StatusOut,
  TalentUpsert,
  TeamOut,
  UserMonsterCreate,
  UserMonsterOut,
} from "@/types";

/**
 * Map a hydrated UserMonsterOut to the ID-only UserMonsterCreate shape
 * that MonsterCard and MatchupPanel's `defender` prop expect.
 * Strips TalentOut.id — UserMonsterCreate.talent is TalentUpsert (no id).
 */
function toCreate(um: UserMonsterOut): UserMonsterCreate {
  return {
    monster_id: um.monster.id,
    personality_id: um.personality.id,
    legacy_type_id: um.legacy_type.id,
    move1_id: um.move1.id,
    move2_id: um.move2.id,
    move3_id: um.move3.id,
    move4_id: um.move4.id,
    talent: {
      hp_boost: um.talent.hp_boost,
      phy_atk_boost: um.talent.phy_atk_boost,
      mag_atk_boost: um.talent.mag_atk_boost,
      phy_def_boost: um.talent.phy_def_boost,
      mag_def_boost: um.talent.mag_def_boost,
      spd_boost: um.talent.spd_boost,
    },
  };
}

/**
 * Renders ONE featured team's defender lineup against the attacker.
 *
 * Uses `team: TeamOut` (fully hydrated from /teams/featured). Personality
 * and moves come directly from UserMonsterOut, so no re-fetching those.
 * useMonstersByIds is kept for full MonsterOut (includes type effectiveness
 * data — vulnerable_to/resistant_to — needed by computeMatchup).
 */
interface Props {
  team: TeamOut;
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

  const allMonsterIds = useMemo(
    () => team.user_monsters.map((um) => um.monster.id),
    [team],
  );

  const monstersResult = useMonstersByIds(allMonsterIds);

  const isLoading = monstersResult.isLoading;
  const isError = monstersResult.isError;

  const defenderRows = useMemo(() => {
    return team.user_monsters.map((um, idx) => {
      const monster = monstersResult.monsters.get(um.monster.id);
      const moves: MoveOut[] = [um.move1, um.move2, um.move3, um.move4];
      return {
        key: `${team.id}-${idx}`,
        defender: toCreate(um),
        monster,
        personality: um.personality,
        moves,
      };
    });
  }, [team, monstersResult.monsters]);

  if (isLoading) {
    return (
      <PanelCard>
        <div className="text-sm text-zinc-500">{t("common.loading")}</div>
      </PanelCard>
    );
  }

  if (isError) {
    return (
      <PanelCard>
        <div className="text-sm text-rose-600">{t("analysis.matchupDataUnavailable")}</div>
      </PanelCard>
    );
  }

  return (
    <div className="space-y-3">
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
