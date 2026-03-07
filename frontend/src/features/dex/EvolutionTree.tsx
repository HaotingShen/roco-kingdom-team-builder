import { Link } from "react-router-dom";
import { Fragment } from "react";
import { useI18n, pickName, pickFormName, type Lang } from "@/i18n";
import { monsterImageFallbackChain } from "@/lib/images";
import type { EvolutionTreeData, EvolutionStageMonster } from "@/types";

interface EvolutionTreeProps {
  treeData: EvolutionTreeData;
  currentMonsterId: number;
  fromTab: string;
  fromBuilder: boolean;
}

export default function EvolutionTree({
  treeData,
  currentMonsterId,
  fromTab,
  fromBuilder
}: EvolutionTreeProps) {
  const { lang } = useI18n();

  if (!treeData || !treeData.stages || treeData.stages.length <= 1) {
    return null;
  }

  return (
    <div className="overflow-x-auto py-4">
      {/* CRITICAL: items-center for vertical centering, justify-center for horizontal centering */}
      <div className="flex items-center justify-center gap-2 sm:gap-3 min-w-min">
        {treeData.stages.map((stage, stageIndex) => (
          <Fragment key={stage.depth}>
            {/* Stage Column - wrapped for vertical centering */}
            <div className="flex flex-col gap-1.5 sm:gap-2 shrink-0">
              {/* Stage monsters stacked vertically */}
              {stage.monsters.map(monster => (
                <MonsterEvolutionCard
                  key={monster.id}
                  monster={monster}
                  isCurrent={monster.id === currentMonsterId}
                  fromTab={fromTab}
                  fromBuilder={fromBuilder}
                  lang={lang}
                />
              ))}
            </div>

            {/* Arrow to next stage */}
            {stageIndex < treeData.stages.length - 1 && (
              <EvolutionArrow
                isLeaderTransition={treeData.stages[stageIndex + 1]?.is_leader_stage}
              />
            )}
          </Fragment>
        ))}
      </div>
    </div>
  );
}

function EvolutionArrow({ isLeaderTransition }: { isLeaderTransition?: boolean }) {
  // Leader icon for transitions TO leader forms
  if (isLeaderTransition) {
    return (
      <div className="flex items-center justify-center shrink-0 px-1 sm:px-2">
        <img
          src="/type-icons/30/leader.png"
          alt="Evolves to Leader"
          className="w-6 h-6 sm:w-7 sm:h-7 drop-shadow-md"
        />
      </div>
    );
  }

  // Styled evolution arrow for normal transitions
  return (
    <div className="flex items-center justify-center shrink-0 px-1 sm:px-2">
      <svg
        className="w-5 h-5 sm:w-7 sm:h-7 opacity-70"
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* Gradient definition */}
        <defs>
          <linearGradient id="arrowGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#a1a1aa" stopOpacity="0.4" />
            <stop offset="50%" stopColor="#71717a" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#52525b" stopOpacity="1" />
          </linearGradient>
        </defs>

        {/* Arrow shape: three chevrons */}
        <path
          d="M 6 12 L 12 16 L 6 20"
          stroke="url(#arrowGradient)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        <path
          d="M 13 12 L 19 16 L 13 20"
          stroke="url(#arrowGradient)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
        <path
          d="M 20 12 L 26 16 L 20 20"
          stroke="url(#arrowGradient)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </svg>
    </div>
  );
}

function MonsterEvolutionCard({
  monster,
  isCurrent,
  fromTab,
  fromBuilder,
  lang
}: {
  monster: EvolutionStageMonster;
  isCurrent: boolean;
  fromTab: string;
  fromBuilder: boolean;
  lang: Lang;
}) {
  const monsterName = pickName(monster as any, lang) || monster.name;

  // CRITICAL: Only show name + form, nothing else!
  // For leader representatives, don't show form name
  const displayName = monster.is_representative
    ? monsterName
    : (monster.form && monster.form !== "default" && monster.form !== "Default")
      ? `${monsterName} (${pickFormName(monster as any, lang) || monster.form})`
      : monsterName;

  const fallbackChain = monsterImageFallbackChain(monster as any, 360);
  const imgSrc = fallbackChain[0] || "/monster-images/placeholder.png";

  // CRITICAL: Leader representatives navigate to first (lowest ID) leader form
  // monster.representative_id will be set to the lowest ID leader form in backend
  const targetId = monster.is_representative && monster.representative_id
    ? monster.representative_id
    : monster.id;

  return (
    <Link
      to={`/dex/monsters/${targetId}?tab=${fromTab}${fromBuilder ? "&from=builder" : ""}`}
      className={`
        block rounded-lg border-2 bg-white p-2 transition-all duration-200 w-20 sm:w-24
        hover:shadow-lg hover:-translate-y-1
        ${isCurrent
          ? "border-blue-500 shadow-md ring-2 ring-blue-200"
          : "border-zinc-200 hover:border-zinc-400"}
      `}
    >
      <div className="space-y-1 sm:space-y-2">
        {/* Image */}
        <div className="relative aspect-square rounded overflow-hidden">
          <img
            src={imgSrc}
            alt={monsterName}
            className="w-full h-full object-contain"
            onError={(e) => {
              const img = e.currentTarget as HTMLImageElement;
              const step = Number(img.dataset.fallbackStep || "0");
              const next = step + 1;
              if (next < fallbackChain.length) {
                img.dataset.fallbackStep = String(next);
                img.src = fallbackChain[next]!;
              } else if (img.src !== "/monster-images/placeholder.png") {
                img.src = "/monster-images/placeholder.png";
              }
            }}
          />

          {/* Current marker (blue dot - no text) */}
          {isCurrent && (
            <div className="absolute bottom-0.5 left-0.5 sm:bottom-1 sm:left-1 w-3 h-3 sm:w-4 sm:h-4 bg-blue-500 rounded-full shadow-sm flex items-center justify-center">
              <div className="w-1 h-1 sm:w-1.5 sm:h-1.5 bg-white rounded-full" />
            </div>
          )}
        </div>

        {/* Name - ONLY name + form, nothing else! */}
        {/* Hidden on mobile (<640px) to save space */}
        <div className="hidden sm:block text-[10px] leading-tight font-medium text-zinc-800 text-center line-clamp-2">
          {displayName}
        </div>
      </div>
    </Link>
  );
}
