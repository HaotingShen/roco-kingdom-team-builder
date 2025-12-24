import { useState, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { pickName, type Lang } from "@/i18n";
import type { MonsterOut } from "@/types";

export function useMonsterNavigation(
  currentMonster: MonsterOut | undefined,
  lang: Lang
) {
  const queryClient = useQueryClient();
  const [prevMonsterId, setPrevMonsterId] = useState<number | null>(null);
  const [nextMonsterId, setNextMonsterId] = useState<number | null>(null);
  const [isLoadingPrev, setIsLoadingPrev] = useState(false);
  const [isLoadingNext, setIsLoadingNext] = useState(false);

  useEffect(() => {
    if (!currentMonster) return;

    const currentId = currentMonster.id; // Store ID to avoid TS undefined errors
    const isLeaderForm = currentMonster.is_leader_form === true;

    // For non-leader monsters, check if target is a leader form
    if (!isLeaderForm) {
      async function checkSimpleNext() {
        if (currentId >= 503) {
          setNextMonsterId(null);
          setIsLoadingNext(false);
          return;
        }

        setIsLoadingNext(true);
        try {
          const nextCandidate = await queryClient.fetchQuery({
            queryKey: ["monster", currentId + 1],
            queryFn: () => endpoints.monsterById(String(currentId + 1)).then(r => r.data),
            staleTime: 5 * 60 * 1000,
          });

          // If next monster is a leader form, find its first form
          if (nextCandidate.is_leader_form) {
            const nextSpeciesName = pickName(nextCandidate, lang) || nextCandidate.name;
            let firstFormId = currentId + 1;

            for (let checkId = currentId; checkId >= 1; checkId--) {
              try {
                const checkCandidate = await queryClient.fetchQuery({
                  queryKey: ["monster", checkId],
                  queryFn: () => endpoints.monsterById(String(checkId)).then(r => r.data),
                  staleTime: 5 * 60 * 1000,
                });
                const checkSpeciesName = pickName(checkCandidate, lang) || checkCandidate.name;
                if (checkSpeciesName === nextSpeciesName) {
                  firstFormId = checkId;
                } else {
                  break;
                }
              } catch {
                break;
              }
            }
            setNextMonsterId(firstFormId);
          } else {
            setNextMonsterId(currentId + 1);
          }
        } catch {
          setNextMonsterId(null);
        }
        setIsLoadingNext(false);
      }

      async function checkSimplePrev() {
        if (currentId <= 1) {
          setPrevMonsterId(null);
          setIsLoadingPrev(false);
          return;
        }

        setIsLoadingPrev(true);
        try {
          const prevCandidate = await queryClient.fetchQuery({
            queryKey: ["monster", currentId - 1],
            queryFn: () => endpoints.monsterById(String(currentId - 1)).then(r => r.data),
            staleTime: 5 * 60 * 1000,
          });

          // If prev monster is a leader form, find its first form
          if (prevCandidate.is_leader_form) {
            const prevSpeciesName = pickName(prevCandidate, lang) || prevCandidate.name;
            let firstFormId = currentId - 1;

            for (let checkId = currentId - 2; checkId >= 1; checkId--) {
              try {
                const checkCandidate = await queryClient.fetchQuery({
                  queryKey: ["monster", checkId],
                  queryFn: () => endpoints.monsterById(String(checkId)).then(r => r.data),
                  staleTime: 5 * 60 * 1000,
                });
                const checkSpeciesName = pickName(checkCandidate, lang) || checkCandidate.name;
                if (checkSpeciesName === prevSpeciesName) {
                  firstFormId = checkId;
                } else {
                  break;
                }
              } catch {
                break;
              }
            }
            setPrevMonsterId(firstFormId);
          } else {
            setPrevMonsterId(currentId - 1);
          }
        } catch {
          setPrevMonsterId(null);
        }
        setIsLoadingPrev(false);
      }

      checkSimpleNext();
      checkSimplePrev();
      return;
    }

    // For leader monsters, skip to different species
    const currentSpeciesName = pickName(currentMonster, lang) || currentMonster.name;
    const MAX_ID = 503; // Total monsters in database
    const MAX_ATTEMPTS = 10; // Prevent infinite loops
    const MAX_CONSECUTIVE_404s = 3; // Stop if hit end of list

    // Find next monster with different species name
    async function findNext() {
      setIsLoadingNext(true);
      let candidateId = currentId + 1;
      let attempts = 0;
      let consecutive404s = 0;

      while (candidateId <= MAX_ID && attempts < MAX_ATTEMPTS) {
        try {
          const candidate = await queryClient.fetchQuery({
            queryKey: ["monster", candidateId],
            queryFn: () => endpoints.monsterById(String(candidateId)).then(r => r.data),
            staleTime: 5 * 60 * 1000, // Cache for 5 minutes
          });

          const candidateSpeciesName = pickName(candidate, lang) || candidate.name;

          // Found different species!
          if (candidateSpeciesName !== currentSpeciesName) {
            // If it's a leader form, find the FIRST form (lowest ID) of this leader
            if (candidate.is_leader_form) {
              let firstFormId = candidateId;
              // Search backwards to find the first form
              for (let checkId = candidateId - 1; checkId >= 1; checkId--) {
                try {
                  const checkCandidate = await queryClient.fetchQuery({
                    queryKey: ["monster", checkId],
                    queryFn: () => endpoints.monsterById(String(checkId)).then(r => r.data),
                    staleTime: 5 * 60 * 1000,
                  });
                  const checkSpeciesName = pickName(checkCandidate, lang) || checkCandidate.name;
                  if (checkSpeciesName === candidateSpeciesName) {
                    firstFormId = checkId;
                  } else {
                    break; // Different species, stop searching
                  }
                } catch {
                  break; // Error or 404, stop searching
                }
              }
              setNextMonsterId(firstFormId);
            } else {
              setNextMonsterId(candidateId);
            }
            setIsLoadingNext(false);
            return;
          }

          // Same species, keep searching
          candidateId++;
          consecutive404s = 0;
          attempts++;
        } catch (error: any) {
          // Handle 404 (ID gap in database)
          if (error?.response?.status === 404) {
            consecutive404s++;
            if (consecutive404s >= MAX_CONSECUTIVE_404s) {
              // Reached end of list
              setNextMonsterId(null);
              setIsLoadingNext(false);
              return;
            }
            candidateId++;
            attempts++;
          } else {
            // Network error or other issue
            console.error("Error fetching next monster:", error);
            setNextMonsterId(null);
            setIsLoadingNext(false);
            return;
          }
        }
      }

      // Max attempts reached
      setNextMonsterId(null);
      setIsLoadingNext(false);
    }

    // Find previous monster with different species name (mirror logic)
    async function findPrev() {
      setIsLoadingPrev(true);
      let candidateId = currentId - 1;
      let attempts = 0;
      let consecutive404s = 0;

      while (candidateId >= 1 && attempts < MAX_ATTEMPTS) {
        try {
          const candidate = await queryClient.fetchQuery({
            queryKey: ["monster", candidateId],
            queryFn: () => endpoints.monsterById(String(candidateId)).then(r => r.data),
            staleTime: 5 * 60 * 1000,
          });

          const candidateSpeciesName = pickName(candidate, lang) || candidate.name;

          if (candidateSpeciesName !== currentSpeciesName) {
            // If it's a leader form, find the FIRST form (lowest ID) of this leader
            if (candidate.is_leader_form) {
              let firstFormId = candidateId;
              // Search backwards to find the first form
              for (let checkId = candidateId - 1; checkId >= 1; checkId--) {
                try {
                  const checkCandidate = await queryClient.fetchQuery({
                    queryKey: ["monster", checkId],
                    queryFn: () => endpoints.monsterById(String(checkId)).then(r => r.data),
                    staleTime: 5 * 60 * 1000,
                  });
                  const checkSpeciesName = pickName(checkCandidate, lang) || checkCandidate.name;
                  if (checkSpeciesName === candidateSpeciesName) {
                    firstFormId = checkId;
                  } else {
                    break; // Different species, stop searching
                  }
                } catch {
                  break; // Error or 404, stop searching
                }
              }
              setPrevMonsterId(firstFormId);
            } else {
              setPrevMonsterId(candidateId);
            }
            setIsLoadingPrev(false);
            return;
          }

          candidateId--;
          consecutive404s = 0;
          attempts++;
        } catch (error: any) {
          if (error?.response?.status === 404) {
            consecutive404s++;
            if (consecutive404s >= MAX_CONSECUTIVE_404s) {
              setPrevMonsterId(null);
              setIsLoadingPrev(false);
              return;
            }
            candidateId--;
            attempts++;
          } else {
            console.error("Error fetching prev monster:", error);
            setPrevMonsterId(null);
            setIsLoadingPrev(false);
            return;
          }
        }
      }

      setPrevMonsterId(null);
      setIsLoadingPrev(false);
    }

    findNext();
    findPrev();
  }, [currentMonster?.id, lang, queryClient]);

  return { prevMonsterId, nextMonsterId, isLoadingPrev, isLoadingNext };
}
