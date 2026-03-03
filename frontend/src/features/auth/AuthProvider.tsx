import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { useAuthStore } from './authStore';
import { api, authEndpoints, refreshCoordinator } from '@/lib/api';
import { useI18n, type Lang } from '@/i18n';

interface AuthContextType {
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType>({ isLoading: true });

export const useAuth = () => useContext(AuthContext);

/**
 * @deprecated Device ID is now managed via httpOnly cookie by the backend.
 * This constant is kept for backward compatibility but is no longer used.
 */
export const DEVICE_ID_KEY = 'rktb-device-id';

/**
 * @deprecated Device ID is now managed via httpOnly cookie by the backend.
 * The cookie is set automatically by DeviceIDMiddleware on first request.
 * This function is kept for backward compatibility but does nothing useful.
 */
export function getOrCreateDeviceId(): string {
  // Device ID is now handled by backend httpOnly cookie
  // This function is deprecated - return empty string
  return '';
}

/**
 * THREE-TIER AUTH SYSTEM:
 *
 * 1. Anonymous (no account):
 *    - user is null
 *    - Can analyze teams (1/day via device_id + IP tracking)
 *    - Cannot save teams
 *    - Shows "Log In" button
 *
 * 2. Guest (explicit "Continue as Guest"):
 *    - user.is_guest = true, subscription_tier = "guest"
 *    - Can analyze (3/day) and save teams (3 max)
 *    - Created when user clicks "Continue as Guest"
 *
 * 3. Registered (full account):
 *    - user.is_guest = false, subscription_tier = "free" or higher
 *    - Full access based on tier
 *
 * KEY CHANGE: We no longer auto-create guest accounts.
 * New users start as Anonymous until they explicitly choose to:
 * - Create an account (→ registered)
 * - Continue as guest (→ guest)
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [isLoading, setIsLoading] = useState(true);
  const { user, setAuth, clearAuth } = useAuthStore();
  // NOTE: AuthProvider is inside I18nProvider in the component tree, so useI18n() is valid here.
  const { setLang } = useI18n();

  useEffect(() => {
    let isCancelled = false;

    const initAuth = async () => {
      // NOTE: Device ID is now handled by backend httpOnly cookie.
      // No need to manage it in frontend anymore.

      // Case 1: User profile exists, try to refresh access token.
      // Signal refresh start BEFORE the async call so any 401s from React Query
      // (which fire immediately since user is in localStorage) are queued here
      // instead of triggering a parallel refresh race.
      if (user) {
        refreshCoordinator.begin();
        try {
          // SECURITY: Refresh endpoint reads httpOnly cookie automatically
          const response = await authEndpoints.refresh();
          const freshToken = response.data.access_token;
          refreshCoordinator.succeed(freshToken);
          if (!isCancelled) {
            // Fetch fresh profile to pick up server-side changes (e.g. email_verified)
            let freshUser = user;
            try {
              const meResponse = await api.get('/auth/me', {
                headers: { Authorization: `Bearer ${freshToken}` },
              });
              freshUser = meResponse.data;
            } catch {
              // Non-critical — fall back to stale user data
            }
            setAuth(freshUser, freshToken);
            if (!freshUser.is_guest && freshUser.preferred_language) {
              setLang(freshUser.preferred_language as Lang);
            }
          }
        } catch (_error) {
          // Reject all queued requests — refresh token invalid/expired
          refreshCoordinator.fail();
          if (!isCancelled) {
            // Clear auth - user is now anonymous
            // They can reclaim their guest account later via "Continue as Guest"
            clearAuth();
          }
        }
      }
      // Case 2: No user profile - stay anonymous
      // DO NOT auto-create guest account
      // User will see "Log In" button and can choose to:
      // - Create account (registration)
      // - Continue as guest (explicit guest creation)

      if (!isCancelled) {
        setIsLoading(false);
      }
    };

    initAuth();

    // Cleanup prevents React Strict Mode double-creation
    return () => {
      isCancelled = true;
    };
  }, []);

  // The HTML loading screen (index.html) stays visible until auth is ready
  // We hide it by calling window.hideAppLoading() after setIsLoading(false)
  // This prevents any blank screen flash during initialization
  return (
    <AuthContext.Provider value={{ isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

