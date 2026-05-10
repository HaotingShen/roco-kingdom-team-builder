import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { endpoints } from "@/lib/api";
import { QUERY_KEYS } from "@/lib/constants";
import SubTabs from "@/components/SubTabs";
import PanelCard from "@/components/PanelCard";
import FeaturedTeamView from "./FeaturedTeamView";
import type {
  MonsterOut,
  MoveOut,
  PersonalityOut,
  StatusOut,
  TalentUpsert,
  TeamOut,
  TypeOut,
} from "@/types";

interface Props {
  attackerMonster: MonsterOut;
  attackerTalent: TalentUpsert;
  attackerPersonality: PersonalityOut;
  attackerMoves: readonly MoveOut[];
  /** Active attacker statuses shared across every defender matchup. */
  attackerStatuses: readonly StatusOut[];
  attackerLegacyType?: TypeOut | null;
  willpowerActive?: boolean;
}

export default function VsFeaturedTeamsTab({
  attackerMonster,
  attackerTalent,
  attackerPersonality,
  attackerMoves,
  attackerStatuses,
  attackerLegacyType,
  willpowerActive,
}: Props) {
  const { t } = useI18n();

  const { data: teams, isLoading, isError } = useQuery<TeamOut[]>({
    queryKey: QUERY_KEYS.FEATURED_TEAMS,
    queryFn: () => endpoints.getFeaturedTeams().then((r) => r.data as TeamOut[]),
    staleTime: 0,
  });

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

  if (!teams || teams.length === 0) {
    return (
      <PanelCard>
        <div className="text-sm text-zinc-500">{t("analysis.featuredTeamNoTeams")}</div>
      </PanelCard>
    );
  }

  const tabs = teams.map((team) => ({
    key: String(team.id),
    label: team.name ?? `Team ${team.id}`,
    content: (
      <FeaturedTeamView
        team={team}
        attackerMonster={attackerMonster}
        attackerTalent={attackerTalent}
        attackerPersonality={attackerPersonality}
        attackerMoves={attackerMoves}
        attackerStatuses={attackerStatuses}
        attackerLegacyType={attackerLegacyType}
        willpowerActive={willpowerActive}
      />
    ),
  }));

  return <SubTabs tabs={tabs} />;
}
