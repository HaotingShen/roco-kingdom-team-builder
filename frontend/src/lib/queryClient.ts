import { QueryClient } from "@tanstack/react-query";
import { CACHE_TIME } from "./constants";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: CACHE_TIME.SHORT,
      refetchOnWindowFocus: false,
      retry: (failureCount, error: any) => {
        // Don't retry on 404s
        if (error?.response?.status === 404) return false;
        // Don't retry on 400s (client errors)
        if (error?.response?.status >= 400 && error?.response?.status < 500) {
          return false;
        }
        // Retry up to 2 times for server errors
        return failureCount < 2;
      },
    },
    mutations: {
      retry: (failureCount, error: any) => {
        // Don't retry mutations on client errors
        if (error?.response?.status >= 400 && error?.response?.status < 500) {
          return false;
        }
        // Retry once for server errors
        return failureCount < 1;
      },
    },
  },
});