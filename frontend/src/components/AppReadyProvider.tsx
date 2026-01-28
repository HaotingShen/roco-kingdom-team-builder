import { useEffect, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/features/auth/AuthProvider';
import { endpoints } from '@/lib/api';

// Declare the global function for hiding the HTML loading screen
declare global {
  interface Window {
    hideAppLoading?: () => void;
  }
}

/**
 * AppReadyProvider waits for all essential async operations to complete
 * before hiding the loading screen and showing the app.
 *
 * Essential operations:
 * 1. Auth initialization (token refresh, user state)
 * 2. Base data fetch (types - needed for styling/localization)
 */
export function AppReadyProvider({ children }: { children: ReactNode }) {
  const [isAppReady, setIsAppReady] = useState(false);
  const { isLoading: isAuthLoading } = useAuth();

  // Pre-fetch essential data
  const typesQuery = useQuery({
    queryKey: ['types'],
    queryFn: () => endpoints.types().then(r => r.data),
    staleTime: Infinity, // Types rarely change
  });

  // Check if all essential data is ready
  const isDataReady = !typesQuery.isLoading;

  useEffect(() => {
    // Only mark as ready when both auth AND data are ready
    if (!isAuthLoading && isDataReady && !isAppReady) {
      setIsAppReady(true);
      // Hide the HTML loading screen
      window.hideAppLoading?.();
    }
  }, [isAuthLoading, isDataReady, isAppReady]);

  // Always render children - the HTML loading screen covers everything
  // until we call hideAppLoading()
  return <>{children}</>;
}
