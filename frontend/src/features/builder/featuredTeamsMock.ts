import type { TalentUpsert, UserMonsterCreate } from "@/types";

/**
 * Throwaway mock for the V1 of the vs-Featured-Teams UI.
 *
 * Each entry mirrors the SHAPE of TeamOut (id, name, list of monster
 * configs) so the swap to the real /teams/featured endpoint in the next
 * PR is mechanical:
 *
 *   - Real API returns TeamOut[] with `user_monsters: UserMonsterOut[]`
 *     (hydrated). The translator at the call site will be a small
 *     `userMonsterOutToCreate(um)` adapter mapping `um.monster.id` →
 *     `monster_id`, etc., feeding the same MatchupPanel/MonsterCard chain
 *     we use here.
 *
 * Uses low monster/personality/move IDs that are typically present in
 * any seeded local DB. If your DB doesn't have them, edit the constants
 * below — they are intentionally easy to swap.
 *
 * Module-level export so the array identity is stable across renders.
 * Importing this from a render path will NOT cause downstream memos to
 * thrash.
 */
export interface MockFeaturedTeam {
  id: number;
  name: string;
  user_monsters: UserMonsterCreate[];
}

// ---- Talent presets (shared across the mock teams) ----

const TALENT_BALANCED: TalentUpsert = {
  hp_boost: 5,
  phy_atk_boost: 5,
  mag_atk_boost: 0,
  phy_def_boost: 5,
  mag_def_boost: 5,
  spd_boost: 5,
};

const TALENT_PHYSICAL: TalentUpsert = {
  hp_boost: 5,
  phy_atk_boost: 10,
  mag_atk_boost: 0,
  phy_def_boost: 5,
  mag_def_boost: 0,
  spd_boost: 10,
};

const TALENT_MAGICAL: TalentUpsert = {
  hp_boost: 5,
  phy_atk_boost: 0,
  mag_atk_boost: 10,
  phy_def_boost: 0,
  mag_def_boost: 10,
  spd_boost: 5,
};

// ---- Mock teams (3 × 6 defenders) ----
//
// Team Gamma intentionally REUSES some monster IDs from Team Alpha so we
// can verify in the react-query DevTools that `useMonstersByIds` shares
// cache entries across team switches — clicking from Alpha → Gamma should
// trigger ZERO new MONSTER_DETAIL fetches for the overlapping ids.

export const MOCK_FEATURED_TEAMS: readonly MockFeaturedTeam[] = [
  {
    id: 1,
    name: "Sample Team Alpha",
    user_monsters: [
      { monster_id: 1, personality_id: 1, legacy_type_id: 1, move1_id: 1, move2_id: 2, move3_id: 3, move4_id: 4, talent: TALENT_BALANCED },
      { monster_id: 2, personality_id: 2, legacy_type_id: 1, move1_id: 5, move2_id: 6, move3_id: 7, move4_id: 8, talent: TALENT_PHYSICAL },
      { monster_id: 3, personality_id: 3, legacy_type_id: 2, move1_id: 1, move2_id: 3, move3_id: 5, move4_id: 7, talent: TALENT_MAGICAL },
      { monster_id: 4, personality_id: 1, legacy_type_id: 2, move1_id: 2, move2_id: 4, move3_id: 6, move4_id: 8, talent: TALENT_BALANCED },
      { monster_id: 5, personality_id: 2, legacy_type_id: 3, move1_id: 1, move2_id: 2, move3_id: 5, move4_id: 6, talent: TALENT_PHYSICAL },
      { monster_id: 6, personality_id: 3, legacy_type_id: 3, move1_id: 3, move2_id: 4, move3_id: 7, move4_id: 8, talent: TALENT_MAGICAL },
    ],
  },
  {
    id: 2,
    name: "Sample Team Beta",
    user_monsters: [
      { monster_id: 7,  personality_id: 1, legacy_type_id: 4, move1_id: 9,  move2_id: 10, move3_id: 11, move4_id: 12, talent: TALENT_BALANCED },
      { monster_id: 8,  personality_id: 2, legacy_type_id: 4, move1_id: 13, move2_id: 14, move3_id: 15, move4_id: 16, talent: TALENT_PHYSICAL },
      { monster_id: 9,  personality_id: 3, legacy_type_id: 5, move1_id: 9,  move2_id: 11, move3_id: 13, move4_id: 15, talent: TALENT_MAGICAL },
      { monster_id: 10, personality_id: 1, legacy_type_id: 5, move1_id: 10, move2_id: 12, move3_id: 14, move4_id: 16, talent: TALENT_BALANCED },
      { monster_id: 11, personality_id: 2, legacy_type_id: 6, move1_id: 9,  move2_id: 10, move3_id: 13, move4_id: 14, talent: TALENT_PHYSICAL },
      { monster_id: 12, personality_id: 3, legacy_type_id: 6, move1_id: 11, move2_id: 12, move3_id: 15, move4_id: 16, talent: TALENT_MAGICAL },
    ],
  },
  {
    id: 3,
    name: "Sample Team Gamma",
    user_monsters: [
      // Reuses 1, 3, 5 from Alpha + 7, 9, 11 from Beta — exercises cache sharing.
      { monster_id: 1,  personality_id: 2, legacy_type_id: 7, move1_id: 2, move2_id: 4, move3_id: 6,  move4_id: 8,  talent: TALENT_PHYSICAL },
      { monster_id: 3,  personality_id: 1, legacy_type_id: 7, move1_id: 1, move2_id: 5, move3_id: 9,  move4_id: 13, talent: TALENT_BALANCED },
      { monster_id: 5,  personality_id: 3, legacy_type_id: 8, move1_id: 3, move2_id: 7, move3_id: 11, move4_id: 15, talent: TALENT_MAGICAL },
      { monster_id: 7,  personality_id: 2, legacy_type_id: 8, move1_id: 4, move2_id: 8, move3_id: 12, move4_id: 16, talent: TALENT_PHYSICAL },
      { monster_id: 9,  personality_id: 1, legacy_type_id: 9, move1_id: 1, move2_id: 6, move3_id: 11, move4_id: 16, talent: TALENT_BALANCED },
      { monster_id: 11, personality_id: 3, legacy_type_id: 9, move1_id: 2, move2_id: 7, move3_id: 12, move4_id: 13, talent: TALENT_MAGICAL },
    ],
  },
] as const;
