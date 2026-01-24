import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { useAuthStore } from './authStore';
import { authEndpoints } from '@/lib/api';

interface AuthContextType {
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType>({ isLoading: true });

export const useAuth = () => useContext(AuthContext);

export const DEVICE_ID_KEY = 'rktb-device-id';

/**
 * Get or create device ID (exported for use in other components).
 * This is persistent across sessions via localStorage.
 */
export function getOrCreateDeviceId(): string {
  let deviceId = localStorage.getItem(DEVICE_ID_KEY);
  if (!deviceId) {
    deviceId = generateDeviceId();
    localStorage.setItem(DEVICE_ID_KEY, deviceId);
  }
  return deviceId;
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

  useEffect(() => {
    let isCancelled = false;

    const initAuth = async () => {
      // Ensure device_id exists (for anonymous tracking)
      getOrCreateDeviceId();

      // Case 1: User profile exists, try to refresh access token
      if (user) {
        try {
          // SECURITY: Refresh endpoint reads httpOnly cookie automatically
          const response = await authEndpoints.refresh();
          if (!isCancelled) {
            setAuth(user, response.data.access_token);
            console.log('Auth refreshed successfully');
          }
        } catch (error) {
          console.log('Token refresh failed, user becomes anonymous');
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

  // Render app immediately - don't block on auth initialization
  // Components can use useAuth().isLoading to show their own loading states if needed
  return (
    <AuthContext.Provider value={{ isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Generate a unique device identifier.
 *
 * Uses crypto.randomUUID() if available (modern browsers),
 * otherwise falls back to timestamp + random string.
 *
 * Stored in localStorage to persist across sessions.
 */
function generateDeviceId(): string {
  if (crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for older browsers
  return `${Date.now()}-${Math.random().toString(36).substring(2)}`;
}
