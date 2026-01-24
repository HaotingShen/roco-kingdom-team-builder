import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface User {
  id: number;
  username: string;
  email: string | null;
  is_guest: boolean;
  email_verified: boolean;
  subscription_tier: string;
  created_at: string;
  last_login_at: string | null;
  is_admin?: boolean;
}

export interface QuotaInfo {
  tier: string;
  daily_used: number;
  daily_limit: number;
  monthly_used: number;
  monthly_limit: number;
  teams_used: number;
  teams_limit: number;
  is_anonymous: boolean;
  is_guest?: boolean;
  redis_available?: boolean;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;  // SECURITY: Memory ONLY (not persisted)
  isAuthenticated: boolean;
  isGuest: boolean;
  isAnonymous: boolean;  // True when user is null (no account)
  quota: QuotaInfo | null;

  setAuth: (user: User, accessToken: string) => void;
  clearAuth: () => void;
  updateUser: (user: User) => void;
  setAccessToken: (token: string) => void;
  setQuota: (quota: QuotaInfo) => void;
}

/**
 * SECURITY: Auth state management with secure storage.
 *
 * Storage strategy:
 * - user: Persisted to localStorage (non-sensitive profile data)
 * - accessToken: Memory ONLY (not persisted, expires in 15 min)
 * - refreshToken: httpOnly cookie ONLY (never in JavaScript)
 *
 * Why this approach:
 * - XSS cannot steal refresh token (httpOnly cookie)
 * - Access token exposure window is short (15 min, memory-only)
 * - User profile cached for UX (survives page reload)
 *
 * Trade-offs:
 * - Access token lost on page refresh → triggers automatic token refresh
 * - Slight delay on first load (refresh API call)
 * - Worth it for security improvement
 */
export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      isAuthenticated: false,
      isGuest: false,
      isAnonymous: true,  // Start as anonymous
      quota: null,

      setAuth: (user, accessToken) => set({
        user,
        accessToken,
        isAuthenticated: true,
        isGuest: user.is_guest,
        isAnonymous: false,
      }),

      clearAuth: () => set({
        user: null,
        accessToken: null,
        isAuthenticated: false,
        isGuest: false,
        isAnonymous: true,
        quota: null,
      }),

      updateUser: (user) => set({ user }),

      setAccessToken: (token) => set({ accessToken: token }),

      setQuota: (quota) => set({ quota }),
    }),
    {
      name: 'rktb-auth',  // localStorage key
      partialize: (state) => ({
        // SECURITY: Only persist non-sensitive user profile
        user: state.user,
        // Do NOT persist accessToken (memory-only for security)
        // Do NOT persist quota (should be fetched fresh)
      }),
    }
  )
);
