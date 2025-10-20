import { useMutation, useQueryClient, UseMutationOptions } from "@tanstack/react-query";
import { toast } from "sonner";

/**
 * Hook for mutations with optimistic updates
 *
 * @example
 * ```typescript
 * const updateTeamName = useOptimisticMutation({
 *   mutationFn: (newName: string) => api.put(`/teams/${teamId}`, { name: newName }),
 *   queryKey: ['teams', teamId],
 *   optimisticUpdate: (oldData, newName) => ({ ...oldData, name: newName }),
 *   successMessage: "Team name updated!",
 * });
 * ```
 */
interface UseOptimisticMutationOptions<TData, TVariables, TContext = unknown> {
  mutationFn: (variables: TVariables) => Promise<TData>;
  queryKey: readonly unknown[];
  optimisticUpdate?: (oldData: TData | undefined, variables: TVariables) => TData;
  successMessage?: string;
  errorMessage?: string;
  invalidateQueries?: readonly unknown[][];
}

export function useOptimisticMutation<TData = unknown, TVariables = unknown, TContext = unknown>({
  mutationFn,
  queryKey,
  optimisticUpdate,
  successMessage,
  errorMessage = "Operation failed. Please try again.",
  invalidateQueries,
}: UseOptimisticMutationOptions<TData, TVariables, TContext>) {
  const queryClient = useQueryClient();

  return useMutation<TData, Error, TVariables, { previousData: TData | undefined }>({
    mutationFn,

    // Before mutation runs
    onMutate: async (variables) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey });

      // Snapshot current value
      const previousData = queryClient.getQueryData<TData>(queryKey);

      // Optimistically update cache if function provided
      if (optimisticUpdate && previousData !== undefined) {
        queryClient.setQueryData<TData>(queryKey, optimisticUpdate(previousData, variables));
      }

      // Return context with snapshot
      return { previousData };
    },

    // On success
    onSuccess: (data) => {
      if (successMessage) {
        toast.success(successMessage);
      }

      // Invalidate related queries
      if (invalidateQueries) {
        invalidateQueries.forEach((key) => {
          queryClient.invalidateQueries({ queryKey: key });
        });
      }
    },

    // On error, rollback
    onError: (error, variables, context) => {
      if (context?.previousData !== undefined) {
        queryClient.setQueryData<TData>(queryKey, context.previousData);
      }

      const message = error.message || errorMessage;
      toast.error(message);
    },

    // Always refetch after error or success
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey });
    },
  });
}

/**
 * Example usage for updating team name:
 *
 * ```typescript
 * const updateName = useOptimisticMutation({
 *   mutationFn: (newName: string) => endpoints.updateTeam(teamId, { name: newName }),
 *   queryKey: QUERY_KEYS.TEAM_DETAIL(teamId),
 *   optimisticUpdate: (oldTeam, newName) => ({
 *     ...oldTeam,
 *     name: newName,
 *   }),
 *   successMessage: "Team name updated!",
 *   invalidateQueries: [QUERY_KEYS.TEAMS],
 * });
 *
 * // Use it
 * updateName.mutate("New Team Name");
 * ```
 */
