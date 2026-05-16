import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { endpoints } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import { useMonstersByIds } from "@/hooks/useMonstersByIds";
import { useMovesByIds } from "@/hooks/useMovesByIds";
import { usePersonalities } from "@/hooks/usePersonalities";
import MatchupPanel from "@/components/MatchupPanel";
import PanelCard from "@/components/PanelCard";
import CustomDefenderInspector from "./CustomDefenderInspector";
import type {
  MonsterLiteOut,
  MonsterOut,
  MoveOut,
  PersonalityOut,
  StatusOut,
  TalentUpsert,
  TypeOut,
  UserMonsterCreate,
} from "@/types";

interface Props {
  attackerMonster: MonsterOut;
  attackerTalent: TalentUpsert;
  attackerPersonality: PersonalityOut;
  attackerMoves: readonly MoveOut[];
  attackerStatuses: readonly StatusOut[];
  attackerLegacyType?: TypeOut | null;
  willpowerActive?: boolean;
  /** Leader type ID — used to detect when the custom defender needs leader form fetching. */
  leaderTypeId?: number | null;
  customDefenderSlot: UserMonsterCreate | null;
  onCustomDefenderChange: (slot: UserMonsterCreate | null) => void;
}

export default function VsCustomDefenderTab({
  attackerMonster,
  attackerTalent,
  attackerPersonality,
  attackerMoves,
  attackerStatuses,
  attackerLegacyType,
  willpowerActive,
  leaderTypeId,
  customDefenderSlot,
  onCustomDefenderChange,
}: Props) {
  const { t } = useI18n();

  // Fetch full MonsterOut (with type effectiveness data) for the selected defender
  const defenderMonsterId = customDefenderSlot?.monster_id ?? 0;
  const monstersResult = useMonstersByIds([defenderMonsterId]);
  const defenderMonster = defenderMonsterId > 0 ? monstersResult.monsters.get(defenderMonsterId) : undefined;

  // Fetch full MoveOut objects for the defender's selected moves
  const rawMoveIds = useMemo(
    () => [
      customDefenderSlot?.move1_id,
      customDefenderSlot?.move2_id,
      customDefenderSlot?.move3_id,
      customDefenderSlot?.move4_id,
    ],
    [
      customDefenderSlot?.move1_id,
      customDefenderSlot?.move2_id,
      customDefenderSlot?.move3_id,
      customDefenderSlot?.move4_id,
    ],
  );
  const movesResult = useMovesByIds(rawMoveIds);

  // Re-map moves back to slot order (useMovesByIds returns sorted by ID)
  const defenderMovesData = useMemo(() => {
    const raw = movesResult.query.data;
    if (!raw) return [];
    const byId = new Map(raw.map((m) => m && [m.id, m] as const).filter(Boolean) as [number, MoveOut][]);
    return rawMoveIds
      .filter((id): id is number => typeof id === "number" && id > 0)
      .map((id) => byId.get(id))
      .filter((m): m is MoveOut => m != null);
  }, [movesResult.query.data, rawMoveIds]);

  // Resolve defender personality
  const personalitiesQ = usePersonalities();
  const defenderPersonality = useMemo(
    () => personalitiesQ.data?.find((p: PersonalityOut) => p.id === customDefenderSlot?.personality_id) ?? null,
    [personalitiesQ.data, customDefenderSlot?.personality_id],
  );

  // Defender leader form — eagerly pre-fetched when the defender has leader_potential
  // AND selected the Leader legacy type, so the toggle in MatchupPanel is instant.
  const defenderNeedsLeaderForm =
    !!defenderMonster?.leader_potential &&
    leaderTypeId != null &&
    customDefenderSlot?.legacy_type_id === leaderTypeId;

  const defenderLeaderInfoQ = useQuery({
    queryKey: QUERY_KEYS.LEADER_MONSTER(defenderMonsterId),
    queryFn: () =>
      endpoints
        .monsters({ evolves_from_id: defenderMonsterId, is_leader_form: true })
        .then((r) => ((r.data as MonsterLiteOut[])[0] ?? null)),
    enabled: defenderNeedsLeaderForm && defenderMonsterId > 0,
    staleTime: Infinity,
  });

  const defenderLeaderDetailQ = useQuery({
    queryKey: QUERY_KEYS.MONSTER_DETAIL(defenderLeaderInfoQ.data?.id ?? 0),
    queryFn: () =>
      endpoints.monsterById(defenderLeaderInfoQ.data!.id).then((r) => r.data as MonsterOut),
    enabled: !!defenderLeaderInfoQ.data?.id,
    staleTime: Infinity,
  });

  const defenderLeaderMonster: MonsterOut | undefined =
    defenderNeedsLeaderForm ? (defenderLeaderDetailQ.data ?? undefined) : undefined;

  // Determine readiness for rendering MatchupPanel
  const defenderConfigured =
    customDefenderSlot !== null &&
    customDefenderSlot.monster_id > 0 &&
    defenderPersonality !== null &&
    !monstersResult.isLoading &&
    !monstersResult.isError &&
    defenderMonster != null;

  return (
    <div className="space-y-3">
      {/* Defender configurator */}
      <CustomDefenderInspector
        slot={customDefenderSlot}
        onChange={onCustomDefenderChange}
      />

      {/* Matchup panel — shown only when defender is fully configured */}
      {customDefenderSlot && customDefenderSlot.monster_id > 0 && (
        <>
          {monstersResult.isError && (
            <PanelCard>
              <div className="text-sm text-rose-600">{t("analysis.matchupDataUnavailable")}</div>
            </PanelCard>
          )}
          {monstersResult.isLoading && (
            <PanelCard>
              <div className="text-sm text-zinc-500">{t("common.loading")}</div>
            </PanelCard>
          )}
          {defenderConfigured && (
            <MatchupPanel
              attackerMonster={attackerMonster}
              attackerTalent={attackerTalent}
              attackerPersonality={attackerPersonality}
              attackerMoves={attackerMoves}
              attackerStatuses={attackerStatuses}
              attackerLegacyType={attackerLegacyType}
              willpowerActive={willpowerActive}
              defender={customDefenderSlot}
              defenderMonster={defenderMonster!}
              defenderPersonality={defenderPersonality!}
              defenderMoves={defenderMovesData}
              defenderLeaderMonster={defenderLeaderMonster}
              tabKey="vsCustom"
              defenderSideLabel={t("analysis.vsCustomDefenderLabel")}
            />
          )}
        </>
      )}
    </div>
  );
}
