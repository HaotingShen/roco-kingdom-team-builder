import { useMemo } from "react";
import { useI18n } from "@/i18n";
import { useMonstersByIds } from "@/hooks/useMonstersByIds";
import { useMovesByIds } from "@/hooks/useMovesByIds";
import { usePersonalities } from "@/hooks/usePersonalities";
import MatchupPanel from "@/components/MatchupPanel";
import PanelCard from "@/components/PanelCard";
import CustomDefenderInspector from "./CustomDefenderInspector";
import type {
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
              tabKey="vsCustom"
              defenderSideLabel={t("analysis.vsCustomDefenderLabel")}
            />
          )}
        </>
      )}
    </div>
  );
}
