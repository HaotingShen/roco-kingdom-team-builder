import { useI18n } from "@/i18n";
import SubTabs from "@/components/SubTabs";
import PanelCard from "@/components/PanelCard";
import FeaturedTeamView from "./FeaturedTeamView";
import { MOCK_FEATURED_TEAMS } from "./featuredTeamsMock";
import type {
  MonsterOut,
  MoveOut,
  PersonalityOut,
  TalentUpsert,
} from "@/types";

/**
 * Content of the "vs Featured Teams" tab on MonsterAnalysisPage.
 *
 * V2 scope (this PR):
 *   - Sub-tab strip below the top tab — one tab per featured team
 *   - The active sub-tab renders a `FeaturedTeamView` showing a placeholder
 *     team-info panel + N stacked MatchupPanels (one per defender)
 *   - Still using mock data — the next PR replaces `MOCK_FEATURED_TEAMS`
 *     with `useQuery({ queryFn: endpoints.getFeaturedTeams })`
 *
 * Data-ownership model: this tab is purely structural — sub-tab navigation
 * + per-team component fan-out. The actual defender hydration happens
 * inside `FeaturedTeamView`, which only mounts for the active sub-tab so
 * inactive teams don't fetch. Switching tabs unmounts and remounts the
 * view, but react-query keeps the previously fetched data warm so going
 * back to a previously-visited team is instant.
 *
 * The attacker bundle (monster, talent, personality, moves) is forwarded
 * unchanged from `MonsterAnalysisPage`. The Props interface here matches
 * exactly what the parent already passes — no parent changes required.
 */

interface Props {
  /** The user's slot's already-fetched monster (attacker). */
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

  // Defensive empty-state — the constant is non-empty by construction, but
  // this keeps the swap-to-real-data path safe (real /teams/featured could
  // legitimately return an empty list during a content rebuild).
  if (MOCK_FEATURED_TEAMS.length === 0) {
    return (
      <PanelCard>
        <div className="text-sm text-zinc-500">
          {t("analysis.featuredTeamNoTeams")}
        </div>
      </PanelCard>
    );
  }

  // Build the sub-tab list. Each `content` JSX expression is just a React
  // element description (cheap to construct); SubTabs only mounts the active
  // tab's content, so the hooks inside FeaturedTeamView only run for the
  // currently-selected team.
  const tabs = MOCK_FEATURED_TEAMS.map((team) => ({
    key: String(team.id),
    label: team.name,
    content: (
      <FeaturedTeamView
        team={team}
        attackerMonster={attackerMonster}
        attackerTalent={attackerTalent}
        attackerPersonality={attackerPersonality}
        attackerMoves={attackerMoves}
      />
    ),
  }));

  return <SubTabs tabs={tabs} />;
}
