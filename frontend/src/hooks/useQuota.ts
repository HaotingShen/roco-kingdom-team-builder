import { useQuery } from "@tanstack/react-query";
import { authEndpoints } from "@/lib/api";
import { useAuthStore, type QuotaInfo } from "@/features/auth/authStore";
import { QUERY_KEYS } from "@/lib/constants";
import { useEffect } from "react";
import { useAuth } from "@/features/auth/AuthProvider";

export function useQuota() {
  const setQuota = useAuthStore((s) => s.setQuota);
  const userId = useAuthStore((s) => s.user?.id ?? null);
  const { isLoading: authLoading } = useAuth();

  const query = useQuery<QuotaInfo>({
    queryKey: [...QUERY_KEYS.QUOTA, userId],
    queryFn: async () => {
      const res = await authEndpoints.getQuota();
      return res.data as QuotaInfo;
    },
    enabled: !authLoading,  // Wait for auth init before fetching
    staleTime: 60_000,
    refetchOnWindowFocus: true,
    retry: 1,
  });

  // Sync to Zustand store for non-query consumers
  useEffect(() => {
    if (query.data) {
      setQuota(query.data);
    }
  }, [query.data, setQuota]);

  return {
    quota: query.data ?? null,
    isLoading: query.isLoading,
    refetch: query.refetch,
  };
}
