import MatchupPanel from "@/components/MatchupPanel";
import type {
  MonsterOut,
  TalentUpsert,
  UserMonsterCreate,
} from "@/types";

/**
 * Content of the "vs Featured Teams" tab on MonsterAnalysisPage.
 *
 * V1 scope (this PR):
 *   - One MatchupPanel against a single HARDCODED test defender
 *   - The test defender uses real DB IDs so MonsterCard's existing fetch
 *     chain resolves it cleanly
 *   - The matchup panel itself is generic — it takes any UserMonsterCreate
 *     as `defender`, so swapping in real featured teams later is just
 *     replacing this constant with a fetched list
 *
 * Later (separate PR):
 *   - Fetch /teams/featured via endpoints.getFeaturedTeams()
 *   - Map over each team's user_monsters → multiple MatchupPanels
 *   - Group by team name, add team-level rollup later
 *
 * The hardcoded TEST_DEFENDER below is intentionally minimal: pick any
 * monster + personality + 4 moves + talent that exist in your local seed
 * database. If your DB IDs differ, edit the constants here. Treating this
 * as throwaway test data is the point — it'll be replaced by real
 * featured-team consumption in the next PR.
 */

// =============================================================
// Hardcoded V1 test defender. Swap-and-go: change these IDs to
// any monster/personality/move set in your local DB.
// =============================================================
const TEST_DEFENDER_TALENT: TalentUpsert = {
  hp_boost: 5,
  phy_atk_boost: 5,
  mag_atk_boost: 0,
  phy_def_boost: 5,
  mag_def_boost: 5,
  spd_boost: 5,
};

const TEST_DEFENDER: UserMonsterCreate = {
  // Edit these IDs if your local DB doesn't have them. Low IDs are
  // typically present in any seeded environment.
  monster_id: 1,
  personality_id: 1,
  legacy_type_id: 1,
  move1_id: 1,
  move2_id: 2,
  move3_id: 3,
  move4_id: 4,
  talent: TEST_DEFENDER_TALENT,
};
// =============================================================

interface Props {
  /** The user's slot's already-fetched monster (attacker). */
  attackerMonster: MonsterOut;
  /** The user's slot's talent (attacker). */
  attackerTalent: TalentUpsert;
  /** The user's slot's personality_id (attacker). */
  attackerPersonalityId: number;
  /** The user's slot's 4 move ids (attacker). */
  attackerMoveIds: ReadonlyArray<number | 0 | undefined | null>;
}

export default function VsFeaturedTeamsTab({
  attackerMonster,
  attackerTalent,
  attackerPersonalityId,
  attackerMoveIds,
}: Props) {
  return (
    <div className="space-y-3">
      <MatchupPanel
        attackerMonster={attackerMonster}
        attackerTalent={attackerTalent}
        attackerPersonalityId={attackerPersonalityId}
        attackerMoveIds={attackerMoveIds}
        defender={TEST_DEFENDER}
      />
    </div>
  );
}
