import { useMemo, useState, useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useI18n, pickName } from "@/i18n";
import { endpoints } from "@/lib/api";
import { useMonstersByIds } from "@/hooks/useMonstersByIds";
import { useLocalizedPath } from "@/lib/locale";
import { typeIconUrl, monsterImageFallbackChain, monsterPlaceholder, magicItemImageUrl, magicItemPlaceholder } from "@/lib/images";
import MatchupPanel from "@/components/MatchupPanel";
import PanelCard from "@/components/PanelCard";
import type {
  MonsterLiteOut,
  MonsterOut,
  MoveOut,
  PersonalityOut,
  StatusOut,
  TalentUpsert,
  TeamOut,
  TypeOut,
  UserMonsterCreate,
  UserMonsterOut,
} from "@/types";

// ─── TeamCompositionStrip ─────────────────────────────────────────────────────

const TALENT_STAT_LABELS: [string, string, string][] = [
  ["hp_boost",       "生命",  "HP"],
  ["phy_atk_boost",  "物攻",  "P.Atk"],
  ["mag_atk_boost",  "魔攻",  "M.Atk"],
  ["phy_def_boost",  "物防",  "P.Def"],
  ["mag_def_boost",  "魔防",  "M.Def"],
  ["spd_boost",      "速度",  "Spd"],
];

const PERSONALITY_STAT_LABELS: [string, string, string][] = [
  ["hp_mod_pct",      "生命",  "HP"],
  ["phy_atk_mod_pct", "物攻",  "P.Atk"],
  ["mag_atk_mod_pct", "魔攻",  "M.Atk"],
  ["phy_def_mod_pct", "物防",  "P.Def"],
  ["mag_def_mod_pct", "魔防",  "M.Def"],
  ["spd_mod_pct",     "速度",  "Spd"],
];

function MonsterMiniCard({ um }: { um: UserMonsterOut }) {
  const { lang, t } = useI18n();
  const location = useLocation();
  const localized = useLocalizedPath();
  const matchupBack = encodeURIComponent(location.pathname + "?tab=vsFeatured");
  const images = useMemo(() => monsterImageFallbackChain(um.monster, 180), [um.monster]);
  const [imgSrc, setImgSrc] = useState(images[0] ?? monsterPlaceholder);
  const [fallIdx, setFallIdx] = useState(0);

  useEffect(() => {
    setImgSrc(images[0] ?? monsterPlaceholder);
    setFallIdx(0);
  }, [images]);

  const name = pickName(um.monster, lang) || um.monster.name;
  const legacyType = um.legacy_type;
  const legacyIcon = typeIconUrl(legacyType.name, 30);
  const moves = [um.move1, um.move2, um.move3, um.move4];

  const personalityRec = um.personality as unknown as Record<string, number>;
  const talentRec = um.talent as unknown as Record<string, number>;

  const personalityEffects = PERSONALITY_STAT_LABELS.filter(([k]) => personalityRec[k] !== 0);
  const activeTalents = TALENT_STAT_LABELS.filter(([k]) => (talentRec[k] ?? 0) > 0);

  return (
    <div className="flex-none w-32 sm:w-36 rounded-lg border border-zinc-200 bg-white p-2 space-y-1.5 overflow-hidden">
      {/* Avatar */}
      <Link
        to={localized(`/dex/monsters/${um.monster.id}`) + `?from=analysis&back=${matchupBack}`}
        className="block w-14 h-14 mx-auto rounded-lg overflow-hidden bg-zinc-100 border border-zinc-100 hover:opacity-80 transition-opacity"
      >
        <img
          src={imgSrc}
          alt={name}
          className="w-full h-full object-contain"
          onError={() => {
            const next = fallIdx + 1;
            const url = images[next];
            if (next < images.length && url) { setImgSrc(url); setFallIdx(next); }
          }}
        />
      </Link>

      {/* Name */}
      <p className="text-sm font-semibold text-zinc-800 truncate text-center leading-tight">{name}</p>

      {/* Legacy type */}
      <div className="flex items-center justify-center gap-1">
        <span className="text-xs font-medium text-zinc-600 shrink-0">
          {t("labels.legacy")}
        </span>
        <span className="inline-flex items-center gap-0.5 rounded-full bg-zinc-100 px-1.5 py-0.5 text-xs font-medium text-zinc-600 min-w-0">
          {legacyIcon && <img src={legacyIcon} alt={legacyType.name} className="w-4 h-4 shrink-0" />}
          <span className="truncate">{pickName(legacyType, lang) || legacyType.name}</span>
        </span>
      </div>

      {/* Personality effects — boosts first, then penalties */}
      {personalityEffects.length > 0 && (
        <div className="flex items-center justify-center gap-1.5 flex-wrap">
          {[...personalityEffects]
            .sort(([ka], [kb]) => (personalityRec[kb] ?? 0) - (personalityRec[ka] ?? 0))
            .map(([k, zhLabel, enLabel]) => {
              const val = personalityRec[k] ?? 0;
              const up = val > 0;
              return (
                <span
                  key={k}
                  className={`text-xs font-semibold ${up ? "text-emerald-600" : "text-rose-500"}`}
                >
                  {lang === "zh" ? zhLabel : enLabel}{up ? "↑" : "↓"}
                </span>
              );
            })}
        </div>
      )}

      {/* Moves */}
      <ul className="space-y-0.5">
        {moves.map((move, i) => {
          const moveName = pickName(move, lang) || move.name;
          const moveTypeName = move.move_type?.name ?? move.type?.name;
          const icon = moveTypeName ? typeIconUrl(moveTypeName, 30) : null;
          return (
            <li key={i} className="flex items-center gap-1 min-w-0">
              {icon
                ? <img src={icon} alt={moveTypeName} className="w-4 h-4 shrink-0" />
                : <div className="w-4 h-4 shrink-0" />}
              <span className="text-xs font-medium text-zinc-600 truncate">{moveName}</span>
            </li>
          );
        })}
      </ul>

      {/* Talents — only non-zero boosts */}
      {activeTalents.length > 0 && (
        <div className="border-t border-zinc-100 pt-1.5 flex flex-wrap gap-x-1.5 gap-y-0.5">
          {activeTalents.map(([k, zhLabel, enLabel]) => (
            <span key={k} className="text-xs text-zinc-500 font-medium whitespace-nowrap">
              {lang === "zh" ? zhLabel : enLabel}+{talentRec[k]}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function TeamCompositionStrip({ team }: { team: TeamOut }) {
  const { t, lang } = useI18n();
  const itemName = pickName(team.magic_item, lang);
  const itemImg = magicItemImageUrl(team.magic_item) ?? magicItemPlaceholder;
  return (
    <div className="rounded-lg border border-zinc-200 bg-zinc-50 p-3">
      <div className="flex items-center justify-between gap-3 mb-2">
        <p className="text-xs font-semibold text-zinc-500 uppercase tracking-wider shrink-0">
          {t("analysis.featuredTeamComposition")}
        </p>
        {team.magic_item && (
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-xs text-zinc-600">{t("analysis.magicItem")}</span>
            <img
              src={itemImg}
              alt={itemName}
              width={20}
              height={20}
            />
          </div>
        )}
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1 -mb-1">
        {team.user_monsters.map((um) => (
          <MonsterMiniCard key={um.id} um={um} />
        ))}
      </div>
    </div>
  );
}

// ─── toCreate ─────────────────────────────────────────────────────────────────

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
  attackerLegacyType?: TypeOut | null;
  willpowerActive?: boolean;
}

export default function FeaturedTeamView({
  team,
  attackerMonster,
  attackerTalent,
  attackerPersonality,
  attackerMoves,
  attackerStatuses,
  attackerLegacyType,
  willpowerActive,
}: Props) {
  const { t } = useI18n();

  const allMonsterIds = useMemo(
    () => team.user_monsters.map((um) => um.monster.id),
    [team],
  );

  const monstersResult = useMonstersByIds(allMonsterIds);

  // ── Defender leader form pre-fetching ────────────────────────────────────────
  // Identify defenders that have leader_potential AND selected the Leader legacy
  // type. Eagerly fetch their leader forms in the background so the toggle in
  // MatchupPanel is instant when the user clicks it.

  const leaderCandidateIds = useMemo(
    () =>
      team.user_monsters
        .filter((um) => !!um.monster.leader_potential && um.legacy_type.name === "Leader")
        .map((um) => um.monster.id),
    [team],
  );

  // Step 1: find each candidate's leader-form MonsterLiteOut (by evolves_from_id).
  const leaderInfosQ = useQuery({
    queryKey: ["leader_infos_batch", leaderCandidateIds],
    queryFn: async () => {
      const results = await Promise.all(
        leaderCandidateIds.map((id) =>
          endpoints
            .monsters({ evolves_from_id: id, is_leader_form: true })
            .then((r) => ({
              regularId: id,
              leaderInfo: (r.data as MonsterLiteOut[])[0] ?? null,
            })),
        ),
      );
      return results;
    },
    enabled: leaderCandidateIds.length > 0,
    staleTime: Infinity,
  });

  // Step 2: batch-fetch full MonsterOut for each discovered leader-form ID.
  const leaderFormIdsToFetch = useMemo(
    () =>
      (leaderInfosQ.data ?? [])
        .filter((r) => r.leaderInfo !== null)
        .map((r) => r.leaderInfo!.id),
    [leaderInfosQ.data],
  );
  const leaderDetailResults = useMonstersByIds(leaderFormIdsToFetch);

  // Map: regular monster ID → leader-form MonsterOut (only when fully loaded).
  const leaderFormMap = useMemo(() => {
    const map = new Map<number, MonsterOut>();
    for (const result of leaderInfosQ.data ?? []) {
      if (!result.leaderInfo) continue;
      const leaderMonster = leaderDetailResults.monsters.get(result.leaderInfo.id);
      if (leaderMonster) map.set(result.regularId, leaderMonster);
    }
    return map;
  }, [leaderInfosQ.data, leaderDetailResults.monsters]);

  // ─────────────────────────────────────────────────────────────────────────────

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
        leaderMonster: leaderFormMap.get(um.monster.id),
      };
    });
  }, [team, monstersResult.monsters, leaderFormMap]);

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
      <TeamCompositionStrip team={team} />
      {defenderRows.map((row) =>
        row.monster ? (
          <MatchupPanel
            key={row.key}
            attackerMonster={attackerMonster}
            attackerTalent={attackerTalent}
            attackerPersonality={attackerPersonality}
            attackerMoves={attackerMoves}
            attackerStatuses={attackerStatuses}
            attackerLegacyType={attackerLegacyType}
            willpowerActive={willpowerActive}
            defender={row.defender}
            defenderMonster={row.monster}
            defenderPersonality={row.personality}
            defenderMoves={row.moves}
            defenderLeaderMonster={row.leaderMonster}
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
