import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useBuilderStore } from "./builderStore";
import MonsterCard from "@/components/MonsterCard";
import CustomSelect from "@/components/CustomSelect";
import AnalysisResults from "@/components/AnalysisResults";
import SaveTeamModal from "@/components/SaveTeamModal";
import type { MagicItemOut, UserMonsterCreate, TeamCreate, TeamAnalysisOut, TeamOut, TeamUpdate, FullSavedAnalysisOut } from "@/types";
import { useMemo, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import MonsterInspector from "./MonsterInspector";
import { useI18n, pickName } from "@/i18n";
import { extractErrorMessage } from "@/hooks/useTeamMutation";
import { magicItemImageUrl } from "@/lib/images";
import { QUERY_KEYS } from "@/lib/constants";
import { useAuthStore } from "@/features/auth/authStore";
import { useQuota } from "@/hooks/useQuota";
import { DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors, DragOverlay, type DragEndEvent, type DragStartEvent } from '@dnd-kit/core';
import { useDraggable, useDroppable } from '@dnd-kit/core';

/* --- Animated dots component --- */
function AnimatedDots() {
  const [dots, setDots] = useState(".");

  useEffect(() => {
    const interval = setInterval(() => {
      setDots(prev => {
        if (prev === "...") return ".";
        return prev + ".";
      });
    }, 400);

    return () => clearInterval(interval);
  }, []);

  return <span className="inline-block w-3 text-left">{dots}</span>;
}

type VKey =
  | "v_pickMonster"
  | "v_setPersonality"
  | "v_chooseLegacy"
  | "v_select4Moves"
  | "v_pickTalent"
  | "v_max3";

function boostedCount(t: UserMonsterCreate["talent"]) {
  const vals = [
    t.hp_boost,
    t.phy_atk_boost,
    t.mag_atk_boost,
    t.phy_def_boost,
    t.mag_def_boost,
    t.spd_boost,
  ];
  return vals.filter((v) => (v ?? 0) > 0).length;
}

function validateSlot(slot: UserMonsterCreate): VKey[] {
  const errs: VKey[] = [];
  if (!slot.monster_id) errs.push("v_pickMonster");
  if (!slot.personality_id) errs.push("v_setPersonality");
  if (!slot.legacy_type_id) errs.push("v_chooseLegacy");
  const moves = [slot.move1_id, slot.move2_id, slot.move3_id, slot.move4_id];
  if (moves.some((m) => !m)) errs.push("v_select4Moves");
  const b = boostedCount(slot.talent || ({} as any));
  if (b === 0) errs.push("v_pickTalent");
  if (b > 3) errs.push("v_max3");
  return errs;
}

function validateTeamName(name: string | undefined): string | null {
  const trimmed = name?.trim() || "";
  if (!trimmed) {
    return "builder.v_emptyTeamName";
  }
  if (trimmed.length > 16) {
    return "builder.v_teamNameTooLong";
  }
  return null;
}

// quick helper for clearing a single slot
const zeroTalent = { hp_boost:0, phy_atk_boost:0, mag_atk_boost:0, phy_def_boost:0, mag_def_boost:0, spd_boost:0 } as const;

/* --- Drag Handle Component --- */
function DragHandle({ slotIndex, title }: { slotIndex: number; title: string }) {
  const { attributes, listeners, setNodeRef } = useDraggable({
    id: String(slotIndex),
  });

  return (
    <div
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      className="cursor-grab active:cursor-grabbing inline-flex items-center justify-center w-8 h-8 rounded-lg bg-white border-2 border-zinc-300 shadow-sm hover:bg-zinc-50 hover:border-zinc-400 transition-colors"
      title={title}
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="h-4 w-4 text-zinc-600"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M4 8h16M4 16h16"
        />
      </svg>
    </div>
  );
}

/* --- Draggable Slot Component --- */
function DraggableSlot({
  id,
  isDragging,
  children,
}: {
  id: string;
  isDragging: boolean;
  children: React.ReactNode;
}) {
  const { setNodeRef: setDragRef, transform } = useDraggable({
    id,
    disabled: true, // We use dedicated drag handle instead
  });

  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id,
  });

  const style = transform ? {
    transform: `translate3d(${transform.x}px, ${transform.y}px, 0)`,
  } : undefined;

  // Combine drag and drop refs
  const setRefs = (node: HTMLElement | null) => {
    setDragRef(node);
    setDropRef(node);
  };

  return (
    <div
      ref={setRefs}
      style={style}
      className={`h-full ${isDragging ? 'opacity-50' : ''} ${isOver ? 'ring-2 ring-blue-400' : ''}`}
    >
      {children}
    </div>
  );
}

/**
 * Compares two TeamAnalysisOut objects to determine if they represent the same analysis.
 * Checks both team configuration (monsters, moves, talents) AND LLM-generated content
 * (trait synergies, team synergy recommendations).
 */
function analysesMatch(
  current: TeamAnalysisOut | null,
  saved: TeamAnalysisOut | null
): boolean {
  if (!current || !saved) return false;

  // Magic item must match
  if (current.team.magic_item.id !== saved.team.magic_item.id) return false;

  // Must have same number of monsters
  if (current.team.user_monsters.length !== saved.team.user_monsters.length) return false;

  // Each monster in same slot must match exactly
  for (let i = 0; i < current.team.user_monsters.length; i++) {
    const currMon = current.team.user_monsters[i];
    const savedMon = saved.team.user_monsters[i];

    // If either monster is undefined, they don't match
    if (!currMon || !savedMon) return false;

    // Monster, personality, legacy type
    if (currMon.monster?.id !== savedMon.monster?.id) return false;
    if (currMon.personality?.id !== savedMon.personality?.id) return false;
    if (currMon.legacy_type?.id !== savedMon.legacy_type?.id) return false;

    // All 4 moves
    if (currMon.move1?.id !== savedMon.move1?.id) return false;
    if (currMon.move2?.id !== savedMon.move2?.id) return false;
    if (currMon.move3?.id !== savedMon.move3?.id) return false;
    if (currMon.move4?.id !== savedMon.move4?.id) return false;

    // All 6 talents
    if (currMon.talent?.hp_boost !== savedMon.talent?.hp_boost) return false;
    if (currMon.talent?.phy_atk_boost !== savedMon.talent?.phy_atk_boost) return false;
    if (currMon.talent?.mag_atk_boost !== savedMon.talent?.mag_atk_boost) return false;
    if (currMon.talent?.phy_def_boost !== savedMon.talent?.phy_def_boost) return false;
    if (currMon.talent?.mag_def_boost !== savedMon.talent?.mag_def_boost) return false;
    if (currMon.talent?.spd_boost !== savedMon.talent?.spd_boost) return false;
  }

  // CRITICAL: Also compare actual analysis results (LLM-generated content)
  // Team configuration matching is not enough - need to check if the analysis itself matches

  // Compare team synergy recommendations (LLM-generated)
  const currSynergy = current.team_synergy;
  const savedSynergy = saved.team_synergy;

  // If one has synergy and the other doesn't, they don't match
  if ((currSynergy && !savedSynergy) || (!currSynergy && savedSynergy)) return false;

  if (currSynergy && savedSynergy) {
    // Compare team synergy recommendations (simple string comparison)
    if (JSON.stringify(currSynergy.team_archetype) !== JSON.stringify(savedSynergy.team_archetype)) return false;
    if (JSON.stringify(currSynergy.action_priority) !== JSON.stringify(savedSynergy.action_priority)) return false;
    if (JSON.stringify(currSynergy.switching_strategy) !== JSON.stringify(savedSynergy.switching_strategy)) return false;
  }

  // Compare per-monster trait synergies (LLM-generated)
  for (let i = 0; i < current.per_monster.length; i++) {
    const currMonAnalysis = current.per_monster[i];
    const savedMonAnalysis = saved.per_monster[i];

    // If either analysis is undefined, they don't match
    if (!currMonAnalysis || !savedMonAnalysis) return false;

    // Compare trait synergy findings
    if (!currMonAnalysis.trait_synergies || !savedMonAnalysis.trait_synergies) return false;
    if (currMonAnalysis.trait_synergies.length !== savedMonAnalysis.trait_synergies.length) return false;

    for (let j = 0; j < currMonAnalysis.trait_synergies.length; j++) {
      const currSyn = currMonAnalysis.trait_synergies[j];
      const savedSyn = savedMonAnalysis.trait_synergies[j];

      // If either synergy is undefined, they don't match
      if (!currSyn || !savedSyn) return false;

      // Compare synergy moves and recommendations
      if (JSON.stringify(currSyn.synergy_moves) !== JSON.stringify(savedSyn.synergy_moves)) return false;
      if (JSON.stringify(currSyn.recommendation) !== JSON.stringify(savedSyn.recommendation)) return false;
    }
  }

  return true;
}

export default function BuilderPage() {
  const {
    teamId,
    name,
    setName,
    slots,
    setSlot,
    moveSlot,
    magic_item_id,
    setMagicItem,
    toPayload,
    toUpdatePayload,
    analysis,
    setAnalysis,
    isAnalyzing,
    setIsAnalyzing,
  } = useBuilderStore();

  const [activeIdx, setActiveIdx] = useState<number>(0);
  const [serverErr, setServerErr] = useState<string | null>(null);
  const [serverOk, setServerOk] = useState<string | null>(null);
  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [attemptedAction, setAttemptedAction] = useState<'analyze' | 'save' | null>(null);
  const showFieldErrors = attemptedAction !== null;
  const { lang, t } = useI18n();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { quota } = useQuota();

  const isAtTeamLimit = quota
    ? quota.teams_limit !== -1 && quota.teams_used >= quota.teams_limit
    : false;

  const isAtAnalysisLimit = quota
    ? quota.daily_limit !== -1 && quota.daily_used >= quota.daily_limit
    : false;

  // Setup DnD sensors
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // 8px movement required before drag starts
      },
    }),
    useSensor(KeyboardSensor)
  );

  const handleDragStart = (event: DragStartEvent) => {
    setActiveDragId(event.active.id as string);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveDragId(null);

    if (!over || active.id === over.id) return;

    const fromIdx = parseInt(active.id as string);
    const toIdx = parseInt(over.id as string);

    moveSlot(fromIdx, toIdx);

    // Update focus to follow the monster being viewed
    if (activeIdx === fromIdx) {
      // User was viewing the dragged monster - follow it to new position
      setActiveIdx(toIdx);
    } else if (activeIdx === toIdx) {
      // User was viewing the target slot - it swapped to source position
      setActiveIdx(fromIdx);
    }
    // Otherwise, keep activeIdx unchanged (viewing a different slot)
  };

  const magicItems = useQuery<MagicItemOut[]>({
    queryKey: QUERY_KEYS.MAGIC_ITEMS,
    queryFn: () => endpoints.magicItems().then((r) => r.data as MagicItemOut[]),
  });
  const qc = useQueryClient();

  // Query for saved analysis (only when teamId exists)
  const savedAnalysisQuery = useQuery<FullSavedAnalysisOut>({
    queryKey: ["savedAnalysis", teamId, lang],
    queryFn: () => endpoints.getSavedAnalysis(teamId!, lang).then(r => r.data),
    enabled: !!teamId && Number.isFinite(teamId),
    retry: false, // 404 is expected when no saved analysis exists
    staleTime: 30000, // Cache for 30 seconds
  });

  // Compute if current analysis matches saved analysis
  const isAnalysisAlreadySaved = useMemo(() => {
    if (!analysis || !savedAnalysisQuery.data?.analysis_data) return false;
    return analysesMatch(analysis, savedAnalysisQuery.data.analysis_data);
  }, [analysis, savedAnalysisQuery.data]);

  const allErrors = useMemo<VKey[][]>(() => slots.map(validateSlot), [slots]);
  const canAnalyze = allErrors.every((list) => list.length === 0) && !!magic_item_id;

  // Auto-reset field error highlights once the attempted action's conditions are fully met
  useEffect(() => {
    if (attemptedAction === 'analyze' && canAnalyze) setAttemptedAction(null);
    if (attemptedAction === 'save' && canAnalyze && !validateTeamName(name)) setAttemptedAction(null);
  }, [attemptedAction, canAnalyze, name]);

  /* ---------- analyze ---------- */
  const analyze = useMutation({
    mutationFn: (payload: TeamCreate) =>
      endpoints.analyzeTeam(payload, lang).then((r) => r.data as TeamAnalysisOut),
    onMutate: () => {
      setIsAnalyzing(true);
    },
    onError: (err) => {
      setServerErr(extractErrorMessage(err));
      setIsAnalyzing(false);
    },
    onSuccess: (data) => {
      setServerErr(null);
      setAnalysis(data);
      setIsAnalyzing(false);
      qc.invalidateQueries({ queryKey: QUERY_KEYS.QUOTA });
      // Scroll to analysis section, with longer delay if navigating back from another page
      const scrollDelay = window.location.pathname !== "/build" ? 300 : 100;
      if (window.location.pathname !== "/build") {
        navigate("/build");
      }
      setTimeout(() => {
        const element = document.getElementById("analysis-results");
        if (element) {
          element.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }, scrollDelay);
    },
    onSettled: () => {
      setIsAnalyzing(false);
    },
  });

  /* ---------- save analysis mutation ---------- */
  const saveAnalysis = useMutation({
    mutationFn: async () => {
      if (!teamId || !analysis) throw new Error("No team or analysis");
      return endpoints.saveAnalysis({
        team_id: teamId,
        language: lang,
        analysis_data: analysis,
        is_from_cache: false,
      }).then((r) => r.data);
    },
    onSuccess: () => {
      setServerOk(t("builder.analysisSaved"));
      // Invalidate to refresh "Already Saved" state
      qc.invalidateQueries({ queryKey: ["savedAnalysis", teamId, lang] });
    },
    onError: (err: any) => {
      setServerErr(err?.response?.data?.detail || t("builder.failedToSave"));
    },
  });

  const onAnalyze = () => {
    if (isAnalyzing) {
      setServerErr(t("builder.analysisInProgress"));
      return;
    }
    if (!canAnalyze) {
      setAttemptedAction('analyze');
      setServerErr(!magic_item_id ? t("builder.v_pickMagicItem") : t("builder.incompleteTeamMsg"));
      return;
    }
    try {
      // Clear previous analysis results immediately when user clicks analyze
      setAttemptedAction(null);
      setAnalysis(null);
      setServerErr(null);
      analyze.mutate(toPayload());
    } catch (e: any) {
      setServerErr(e?.message || t("builder.incompleteTeamMsg"));
    }
  };

  /* ---------- save (create new) / update (modify existing) ---------- */
  const createTeam = useMutation({
    mutationFn: (payload: TeamCreate) =>
      endpoints.createTeam(payload, lang).then((r) => r.data as TeamOut),
    onError: (err: any) => {
      setServerOk(null);
      // Check if it's a 401 error (user not authenticated)
      if (err?.response?.status === 401) {
        // Show the save modal instead of raw error message
        setShowSaveModal(true);
        setServerErr(null);  // Clear any existing error
      } else {
        setServerErr(extractErrorMessage(err));
      }
    },
    onSuccess: (team) => {
      setServerErr(null);
      setServerOk(t("builder.savedMsg"));           // persistent until closed
      useBuilderStore.setState({ teamId: team.id }); // keep id for future updates
      qc.invalidateQueries({ queryKey: QUERY_KEYS.TEAMS });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.TEAM_DETAIL(team.id) });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.QUOTA });
    },
  });

  const updateTeam = useMutation({
    mutationFn: ({ id, body }: { id: number; body: TeamUpdate }) =>
      endpoints.updateTeam(id, body).then((r) => r.data as TeamOut),
    onError: (err) => {
      setServerOk(null);
      setServerErr(extractErrorMessage(err));
    },
    onSuccess: (_updatedTeam, variables) => {
      setServerErr(null);
      setServerOk(t("builder.updatedMsg"));         // persistent until closed
      qc.invalidateQueries({ queryKey: QUERY_KEYS.TEAMS });
      qc.invalidateQueries({ queryKey: QUERY_KEYS.TEAM_DETAIL(variables.id) });
    },
  });

  const onSaveNew = async () => {
    // If user is not logged in, show the save modal first
    if (!user) {
      setShowSaveModal(true);
      return;
    }

    // Validate team name
    const nameError = validateTeamName(name);
    if (nameError) {
      setAttemptedAction('save');
      setServerErr(t(nameError));
      return;
    }

    if (!magic_item_id || !canAnalyze) {
      setAttemptedAction('save');
      setServerErr(t("builder.incompleteTeamMsg"));
      return;
    }

    setAttemptedAction(null);

    // Check team limit before attempting save
    if (isAtTeamLimit) {
      setServerErr(t("quota.teamLimitReached", { limit: quota?.teams_limit ?? 0 }));
      return;
    }

    try {
      // Check for duplicate names (case-sensitive)
      const existingTeams = await qc.fetchQuery({
        queryKey: QUERY_KEYS.TEAMS,
        queryFn: () => endpoints.listTeams().then((r) => r.data as TeamOut[]),
      });

      const trimmedName = name?.trim();
      const duplicate = existingTeams.find(
        (team) => team.name === trimmedName
      );

      if (duplicate) {
        setServerErr(t("builder.v_duplicateTeamName", { name: trimmedName }));
        return;
      }

      createTeam.mutate(toPayload());
    } catch (e: any) {
      // 401 errors from fetchQuery (listTeams) should show modal
      if (e?.response?.status === 401) {
        setShowSaveModal(true);
      } else {
        setServerErr(e?.message || t("builder.incompleteTeamMsg"));
      }
    }
  };

  const onUpdateExisting = async () => {
    if (!teamId) return; // hidden if no teamId anyway

    // Validate team name
    const nameError = validateTeamName(name);
    if (nameError) {
      setAttemptedAction('save');
      setServerErr(t(nameError));
      return;
    }

    if (!magic_item_id || !canAnalyze) {
      setAttemptedAction('save');
      setServerErr(t("builder.incompleteTeamMsg"));
      return;
    }

    setAttemptedAction(null);

    try {
      // Check for duplicate names EXCLUDING current team
      const existingTeams = await qc.fetchQuery({
        queryKey: QUERY_KEYS.TEAMS,
        queryFn: () => endpoints.listTeams().then((r) => r.data as TeamOut[]),
      });

      const trimmedName = name?.trim();
      const duplicate = existingTeams.find(
        (team) => team.id !== teamId && team.name === trimmedName
      );

      if (duplicate) {
        setServerErr(t("builder.v_duplicateTeamName", { name: trimmedName }));
        return;
      }

      const body = toUpdatePayload();
      if (!body) {
        setServerErr(t("builder.incompleteTeamMsg"));
        return;
      }
      updateTeam.mutate({ id: teamId, body });
    } catch (e: any) {
      setServerErr(e?.message || t("builder.incompleteTeamMsg"));
    }
  };

  // Check if user has any work in progress
  const hasWorkInProgress = useMemo(() => {
    const anyFilledSlot = slots.some(um =>
      um.monster_id ||
      um.personality_id ||
      um.legacy_type_id ||
      um.move1_id || um.move2_id || um.move3_id || um.move4_id ||
      Object.values(um.talent || {}).some(v => (v ?? 0) > 0)
    );
    return anyFilledSlot || !!magic_item_id || !!(name?.trim());
  }, [slots, magic_item_id, name]);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="space-y-4">
        {/* Anonymous user warning banner */}
        {!user && hasWorkInProgress && (
          <div className="rounded-lg border-2 border-amber-300 bg-gradient-to-r from-amber-50 to-amber-100 p-4 flex items-center gap-3 shadow-sm">
            <span className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-amber-500 text-white text-sm font-bold shrink-0">
              !
            </span>
            <div className="flex-1">
              <p className="text-sm font-medium text-amber-800">
                {t("builder.unsavedWorkWarning")}
              </p>
              <p className="text-xs text-amber-700 mt-0.5">
                {t("builder.unsavedWorkHint")}
              </p>
            </div>
            <button
              onClick={() => navigate('/auth/login')}
              className="h-9 px-4 bg-amber-600 text-white text-sm font-medium rounded-lg hover:bg-amber-700 transition-colors shrink-0"
            >
              {t("userMenu.login")}
            </button>
          </div>
        )}

        {/* Row 1: Team Builder + Team Settings + Inspector Grid */}
        <div className="grid gap-4 grid-cols-1 lg:grid-cols-[1fr_380px] xl:grid-cols-[1fr_420px]">
          {/* Left: Monster Slots + Team Settings */}
          <section className="space-y-4">
            {/* Section header */}
            <div className="flex items-center gap-2 px-1">
              <div className="h-6 w-1 bg-gradient-to-b from-zinc-800 to-zinc-600 rounded-full" />
              <h2 className="text-lg font-semibold text-zinc-800">{t("builder.teamComposition") || "Team Composition"}</h2>
            </div>

            {/* grid */}
            <div className="grid grid-cols-3 gap-3">
            {slots.map((slot, i) => {
              const errs = allErrors?.[i] ?? [];
              const hasMonster = !!slot.monster_id;
              const isComplete = hasMonster && errs.length === 0;

              const statusKey = !hasMonster
                ? "status_empty"
                : isComplete
                ? "status_complete"
                : "status_incomplete";
              const statusText = t(`builder.${statusKey}`);

              const dotClass = !hasMonster
                ? "bg-zinc-300"
                : isComplete
                ? "bg-emerald-500"
                : "bg-amber-500";

              const chipClass = !hasMonster
                ? "border-zinc-300 bg-zinc-50 text-zinc-600"
                : isComplete
                ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                : "border-amber-300 bg-amber-50 text-amber-700";

              const isDragging = activeDragId === String(i);

              return (
                <DraggableSlot
                  key={i}
                  id={String(i)}
                  isDragging={isDragging}
                >
                  <div
                    className={`
                      h-full rounded-lg border-2 p-3 space-y-2 cursor-pointer
                      transition-all duration-200
                      ${showFieldErrors && errs.length > 0 ? "ring-2 ring-amber-400" : i === activeIdx ? "ring-2 ring-zinc-200" : ""}
                      ${i === activeIdx
                        ? "border-zinc-800 bg-gradient-to-br from-zinc-50 via-white to-zinc-50 shadow-lg"
                        : "border-zinc-200 bg-white shadow-sm hover:shadow-md hover:border-zinc-300 hover:-translate-y-0.5"
                      }
                    `}
                    onClick={() => setActiveIdx(i)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setActiveIdx(i)}
                  >
                  <div className="flex items-center justify-between">
                    {hasMonster ? (
                      <DragHandle slotIndex={i} title={t("builder.dragToReorder")} />
                    ) : (
                      <div className="text-sm font-medium text-zinc-700">{t("builder.slot", { n: i + 1 })}</div>
                    )}
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium shadow-sm ${chipClass}`}
                      title={statusText}
                      aria-label={statusText}
                    >
                      <span className={`h-2.5 w-2.5 rounded-full ${dotClass} animate-pulse`} />
                      <span className="hidden sm:inline">{statusText}</span>
                    </span>
                  </div>

                  <MonsterCard
                    monsterId={slot.monster_id || undefined}
                    personalityId={slot.personality_id || null}
                    legacyTypeId={slot.legacy_type_id || null}
                    moveIds={[slot.move1_id, slot.move2_id, slot.move3_id, slot.move4_id]}
                    talent={slot.talent}
                    onClick={() => setActiveIdx(i)}
                    // quick delete only when a monster is present
                    onDelete={
                      hasMonster
                        ? () => {
                            setSlot(i, {
                              monster_id: 0,
                              personality_id: 0,
                              legacy_type_id: 0,
                              move1_id: 0,
                              move2_id: 0,
                              move3_id: 0,
                              move4_id: 0,
                              talent: { ...zeroTalent },
                            });
                          }
                        : undefined
                    }
                  />

                  {errs.length > 0 && (
                    <ul className="text-[11px] text-red-600 list-disc pl-4">
                      {errs.map((k, j) => (
                        <li key={`${i}-${j}`}>{t(`builder.${k}`)}</li>
                      ))}
                    </ul>
                  )}
                  </div>
                </DraggableSlot>
              );
            })}
          </div>

          {/* Team Configuration Section */}
          <div className="flex items-center gap-2 px-1 mt-6">
            <div className="h-6 w-1 bg-gradient-to-b from-zinc-800 to-zinc-600 rounded-full" />
            <h2 className="text-lg font-semibold text-zinc-800">{t("builder.teamSettings") || "Team Settings"}</h2>
          </div>

          {/* bottom bar */}
          <div className="flex flex-wrap items-center gap-3 bg-gradient-to-br from-white via-zinc-50 to-white border-2 border-zinc-200 rounded-lg shadow-md p-4">
            {/* team name */}
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-zinc-700">{t("builder.teamName") ?? "Team name"}</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("builder.teamNamePlaceholder") ?? "My Team"}
                className={`h-10 rounded-lg border-2 px-3 text-sm w-[160px] focus:outline-none focus:ring-2 focus:ring-zinc-400 focus:border-transparent transition-all shadow-sm ${showFieldErrors && attemptedAction === 'save' && !name?.trim() ? 'border-amber-400' : 'border-zinc-300'}`}
              />
            </div>

            {/* magic item */}
            <div className="flex items-center gap-2">
              <div className="text-sm font-medium text-zinc-700">{t("builder.magicItem")}</div>
              <div className={`rounded-lg transition-all ${showFieldErrors && !magic_item_id ? 'ring-2 ring-amber-400' : ''}`}>
                <CustomSelect
                  value={magic_item_id ?? null}
                  options={[
                    { value: 0, label: t("common.select"), leftIconUrl: null },
                    ...(magicItems.data ?? []).map((mi) => ({
                      value: mi.id,
                      label: pickName(mi as any, lang) || mi.name,
                      leftIconUrl: magicItemImageUrl(mi),
                    })),
                  ]}
                  placeholder={t("common.select")}
                  onChange={(v) => setMagicItem(v ? v : null)}
                  buttonClassName="min-w-[160px]"
                />
              </div>
            </div>

            <div className="flex-1" />

            {/* Action buttons */}
            <button
              onClick={onSaveNew}
              disabled={createTeam.isPending}
              data-testid="create-team-btn"
              className={`
                h-10 px-5 rounded-lg font-medium text-sm
                transition-all duration-200
                ${canAnalyze
                  ? "bg-white border-2 border-zinc-700 text-zinc-800 cursor-pointer shadow-sm hover:bg-zinc-50 hover:shadow-md hover:-translate-y-0.5"
                  : "bg-zinc-200 text-zinc-500 cursor-not-allowed border-2 border-zinc-300"
                }
              `}
              title={
                !canAnalyze
                  ? t("builder.incompleteTeamMsg")
                  : ""
              }
            >
              {createTeam.isPending ? (
                <span className="inline-flex items-center justify-center">
                  {t("builder.saving").replace("…", "").replace("...", "")}
                  <AnimatedDots />
                </span>
              ) : (
                t("builder.saveTeam") ?? "Save"
              )}
            </button>

            {teamId ? (
              <button
                onClick={onUpdateExisting}
                disabled={updateTeam.isPending}
                className={`
                  h-10 px-5 rounded-lg font-medium text-sm
                  transition-all duration-200
                  ${canAnalyze
                    ? "bg-gradient-to-r from-blue-400 to-blue-500 text-white cursor-pointer shadow-md hover:from-blue-500 hover:to-blue-600 hover:shadow-lg hover:-translate-y-0.5"
                    : "bg-zinc-200 text-zinc-500 cursor-not-allowed border-2 border-zinc-300"
                  }
                `}
                title={!canAnalyze ? t("builder.incompleteTeamMsg") : ""}
              >
                {updateTeam.isPending ? (
                  <span className="inline-flex items-center justify-center">
                    {t("builder.updating").replace("…", "").replace("...", "")}
                    <AnimatedDots />
                  </span>
                ) : (
                  t("builder.updateTeam") ?? "Update"
                )}
              </button>
            ) : null}

            {/* analyze */}
            <button
              onClick={onAnalyze}
              disabled={analyze.isPending || isAnalyzing}
              title={
                analysis?.has_partial_errors
                  ? t("builder.reanalyzeFree")
                  : isAtAnalysisLimit && !analysis
                    ? t("quota.analysisLimitReached")
                    : isAtAnalysisLimit && analysis
                      ? t("builder.reanalyzeFree")
                      : !canAnalyze
                        ? t("builder.incompleteTeamMsg")
                        : ""
              }
              className={`
                h-10 px-6 rounded-lg font-semibold text-sm
                transition-all duration-200
                ${canAnalyze && !isAnalyzing
                  ? "bg-gradient-to-r from-zinc-800 to-zinc-900 text-white cursor-pointer shadow-md hover:from-zinc-900 hover:to-black hover:shadow-lg hover:-translate-y-0.5"
                  : "bg-zinc-300 text-zinc-500 cursor-not-allowed"
                }
              `}
            >
              {analyze.isPending || isAnalyzing ? (
                <span className="inline-flex items-center justify-center">
                  {t("builder.analyzing").replace("…", "").replace("...", "")}
                  <AnimatedDots />
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5">
                  {analysis?.has_partial_errors ? t("builder.retryFree") : t("builder.analyze")}
                  {quota && quota.daily_limit !== -1 && (
                    <span className={`text-xs opacity-70 ${isAtAnalysisLimit ? "text-red-300" : ""}`}>
                      ({quota.daily_used}/{quota.daily_limit})
                    </span>
                  )}
                </span>
              )}
            </button>
          </div>

          {/* Analyzing tip */}
          {isAnalyzing && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700 flex items-start gap-2.5 animate-in slide-in-from-top duration-300">
              <span className="shrink-0 mt-0.5">ℹ️</span>
              <span>{t("builder.analyzingTip")}</span>
            </div>
          )}

          {/* closable messages */}
          {serverErr && (
            <div className="rounded-lg border-2 border-red-300 bg-gradient-to-r from-red-50 to-red-100 text-red-700 p-4 text-sm flex items-start justify-between shadow-md animate-in slide-in-from-top duration-300">
              <div className="flex items-start gap-3">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-red-500 text-white text-xs font-bold shrink-0 mt-[1px]">!</span>
                <div className="pr-4">{serverErr}</div>
              </div>
              <button
                onClick={() => setServerErr(null)}
                className="inline-flex items-center justify-center w-6 h-6 rounded-full text-red-700 hover:bg-red-200 hover:text-red-900 cursor-pointer transition-colors"
                aria-label="Close"
                title="Close"
              >
                ×
              </button>
            </div>
          )}
          {serverOk && (
            <div className="rounded-lg border-2 border-emerald-300 bg-gradient-to-r from-emerald-50 to-emerald-100 text-emerald-700 p-4 text-sm flex items-start justify-between shadow-md animate-in slide-in-from-top duration-300">
              <div className="flex items-start gap-3">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-emerald-500 text-white text-xs font-bold shrink-0 mt-[1px]">✓</span>
                <div className="pr-4">{serverOk}</div>
              </div>
              <button
                onClick={() => setServerOk(null)}
                className="inline-flex items-center justify-center w-6 h-6 rounded-full text-emerald-700 hover:bg-emerald-200 hover:text-emerald-900 cursor-pointer transition-colors"
                aria-label="Close"
                title="Close"
              >
                ×
              </button>
            </div>
          )}
          </section>

          {/* Right: Monster Inspector */}
          <MonsterInspector activeIdx={activeIdx} />
        </div>

        {/* Row 2: Analysis Results (Full Width, Conditional) */}
        {analysis && (
          <AnalysisResults
            analysis={analysis}
            teamId={teamId}
            onSaveAnalysis={() => saveAnalysis.mutate()}
            isSaving={saveAnalysis.isPending}
            isAlreadySaved={isAnalysisAlreadySaved}
            isLoggedIn={!!user}
          />
        )}
      </div>

    <DragOverlay>
      {activeDragId !== null ? (
        <div className="rounded-lg border-2 border-zinc-800 bg-gradient-to-br from-zinc-50 via-white to-zinc-50 shadow-2xl p-3 opacity-90 rotate-3 scale-105">
          <div className="text-sm font-medium text-zinc-700">
            {t("builder.slot", { n: parseInt(activeDragId) + 1 })}
          </div>
          <div className="text-xs text-zinc-500 mt-1">
            {t("builder.dragging")}
          </div>
        </div>
      ) : null}
    </DragOverlay>

    {/* Save Team Modal - shown when anonymous user tries to save */}
    <SaveTeamModal
      isOpen={showSaveModal}
      onClose={() => setShowSaveModal(false)}
      onGuestCreated={() => {
        // After guest account created, retry saving the team
        // Small delay to ensure auth state is updated
        setTimeout(() => {
          if (canAnalyze && magic_item_id) {
            createTeam.mutate(toPayload());
          }
        }, 100);
      }}
    />
  </DndContext>
  );
}