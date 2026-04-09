import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useI18n } from "@/i18n";
import { QUERY_KEYS } from "@/lib/constants";
import { useMovesByIds } from "@/hooks/useMovesByIds";
import { usePersonalities } from "@/hooks/usePersonalities";
import MatchupPanel from "@/components/MatchupPanel";
import type {
  MonsterOut,
  MoveOut,
  PersonalityOut,
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
 *   - The matchup panel itself is generic — it takes a fully-hydrated
 *     attacker + defender bundle, so swapping in real featured teams later
 *     is "fetch teams, map over their user_monsters, hydrate each, render".
 *
 * Data-ownership model (post-refactor): this tab owns defender-side hydration.
 * It fetches the defender monster detail + defender moves + personalities
 * once, then hands the hydrated result to MatchupPanel. When this tab grows
 * into N featured defenders:
 *
 *   - We batch the N defender monster ids into as few fetches as the API
 *     supports (today: one monsters-by-id call, or N parallel monsterById
 *     calls sharing react-query cache entries).
 *   - We batch ALL defender move ids (N * 4, deduped) into a SINGLE
 *     useMovesByIds call — the shared hook dedupes + sorts the id list, so
 *     the cache key stays canonical and the fan-in is free.
 *   - Personalities is one cached /personalities call app-wide.
 *
 * Today's single-defender implementation is the shape of that loop, compressed
 * into an array-of-one. The V2 (real featured teams) change is purely "replace
 * the constant with a fetched list and the N === 1 special-case with N > 1".
 *
 * M2: TEST_DEFENDER must stay at module scope (NOT inside the component).
 * Moving it inside would allocate a new object literal every render, which
 * cascades through useMovesByIds's memo (it has a different identity but the
 * same values — dedupe still works, but we'd re-run the memo unnecessarily)
 * and through MatchupPanel's reset-on-defender-change effect (new identity
 * every render → reset fires every render → toggle resets on every keystroke).
 * A const at module scope gives every render the same identity for free.
 */

// =============================================================
// Hardcoded V1 test defender. Swap-and-go: change these IDs to
// any monster/personality/move set in your local DB.
// Must stay at module scope — see M2 comment above.
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
  /** The user's slot's already-fetched monster detail (attacker). */
  attackerMonster: MonsterOut;
  /** The user's slot's talent (attacker). */
  attackerTalent: TalentUpsert;
  /** The user's slot's resolved personality (attacker). */
  attackerPersonality: PersonalityOut;
  /** The user's slot's 4 moves, already fetched (attacker). */
  attackerMoves: readonly MoveOut[];
}

export default function VsFeaturedTeamsTab({
  attackerMonster,
  attackerTalent,
  attackerPersonality,
  attackerMoves,
}: Props) {
  const { t } = useI18n();

  // --- Defender-side fetches ---

  const defenderMonsterQ = useQuery({
    queryKey: QUERY_KEYS.MONSTER_DETAIL(TEST_DEFENDER.monster_id),
    queryFn: () =>
      endpoints
        .monsterById(TEST_DEFENDER.monster_id)
        .then((r) => r.data as MonsterOut),
    enabled: TEST_DEFENDER.monster_id > 0,
  });

  const defenderMovesResult = useMovesByIds([
    TEST_DEFENDER.move1_id,
    TEST_DEFENDER.move2_id,
    TEST_DEFENDER.move3_id,
    TEST_DEFENDER.move4_id,
  ]);

  // Personalities is app-wide cached — the analysis page already triggered
  // it, this is a cache hit. We still call the hook here so that defender
  // personality resolution stays local to the defender-owning component.
  const personalitiesQ = usePersonalities();
  const defenderPersonality =
    personalitiesQ.data?.find((p) => p.id === TEST_DEFENDER.personality_id) ?? null;

  const isLoading =
    defenderMonsterQ.isLoading ||
    defenderMovesResult.query.isLoading ||
    personalitiesQ.isLoading;
  const isError =
    defenderMonsterQ.isError ||
    defenderMovesResult.query.isError ||
    personalitiesQ.isError;
  const ready =
    !!defenderMonsterQ.data &&
    !!defenderMovesResult.query.data &&
    !!defenderPersonality;

  if (isLoading || !ready) {
    return (
      <div className="space-y-3">
        <section className="rounded-lg border border-zinc-200 bg-white shadow-sm p-4">
          <div className={isError ? "text-sm text-rose-600" : "text-sm text-zinc-500"}>
            {isError ? t("analysis.matchupDataUnavailable") : t("common.loading")}
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <MatchupPanel
        attackerMonster={attackerMonster}
        attackerTalent={attackerTalent}
        attackerPersonality={attackerPersonality}
        attackerMoves={attackerMoves}
        defender={TEST_DEFENDER}
        defenderMonster={defenderMonsterQ.data!}
        defenderPersonality={defenderPersonality!}
        defenderMoves={defenderMovesResult.query.data!}
      />
    </div>
  );
}
