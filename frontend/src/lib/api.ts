import axios from "axios";
import { useAuthStore } from "@/features/auth/authStore";
import { queryClient } from "@/lib/queryClient";

// Defined in .env.local as VITE_API_BASE_URL
const baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/**
 * Axios instance with:
 * - Base URL from environment
 * - Credentials (httpOnly cookies)
 * - Auth interceptors (access token + CSRF)
 * - Device ID via httpOnly cookie (set by backend middleware)
 * - Auto token refresh on 401
 *
 * NOTE: Device ID is now managed via httpOnly cookie by the backend.
 * No need for X-Device-ID header or localStorage management.
 */
export const api = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
  withCredentials: true,  // REQUIRED for httpOnly cookies
});

// ========== REQUEST INTERCEPTOR ==========

/**
 * Attach access token to all requests.
 * Add CSRF token for cross-site deployments (SameSite=None).
 *
 * NOTE: Device ID is now handled via httpOnly cookie (set by backend middleware).
 * No need for X-Device-ID header.
 */
api.interceptors.request.use(
  (config) => {
    const accessToken = useAuthStore.getState().accessToken;

    if (accessToken) {
      // Add Authorization header
      config.headers.Authorization = `Bearer ${accessToken}`;

      // CSRF token for cross-site deployments (SameSite=None)
      // Only needed if backend COOKIE_SAMESITE=none
      try {
        const tokenPart = accessToken.split('.')[1];
        if (tokenPart) {
          const payload = JSON.parse(atob(tokenPart));
          if (payload.csrf_token) {
            config.headers['X-CSRF-Token'] = payload.csrf_token;
          }
        }
      } catch (_e) {
        // Ignore JWT parse errors
      }
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// ========== RESPONSE INTERCEPTOR ==========

/**
 * Handle 401 errors with automatic token refresh.
 *
 * Flow:
 * 1. Request fails with 401 (token expired)
 * 2. Try to refresh access token using httpOnly cookie
 * 3. If refresh succeeds: Retry original request with new token
 * 4. If refresh fails: Clear auth and create new guest account
 *
 * Race condition handling:
 * - If multiple requests fail simultaneously, only one refresh happens
 * - Other requests wait for refresh to complete, then retry
 */
let isRefreshing = false;
type RefreshCallback = (token: string | null) => void;
let refreshSubscribers: RefreshCallback[] = [];

const onRefreshed = (token: string) => {
  refreshSubscribers.forEach((cb) => cb(token));
  refreshSubscribers = [];
};

const onRefreshFailed = () => {
  refreshSubscribers.forEach((cb) => cb(null));
  refreshSubscribers = [];
};

const addRefreshSubscriber = (callback: RefreshCallback) => {
  refreshSubscribers.push(callback);
};

/**
 * Exported so AuthProvider can coordinate with the interceptor queue.
 *
 * On page reload, AuthProvider calls /auth/refresh to restore the access token.
 * Meanwhile React Query fires queries (user is in localStorage) which get 401s.
 * Without coordination, the interceptor would launch a parallel refresh call,
 * racing with AuthProvider's — potentially invalidating the refresh token.
 *
 * Usage in AuthProvider:
 *   refreshCoordinator.begin()   → queue any 401s, don't start parallel refresh
 *   refreshCoordinator.succeed() → retry all queued requests with new token
 *   refreshCoordinator.fail()    → reject all queued requests (user logged out)
 */
export const refreshCoordinator = {
  begin: () => { isRefreshing = true; },
  succeed: (token: string) => {
    onRefreshed(token);
    isRefreshing = false;
    // Quota returns 200 with anonymous data when token is expired (no 401 to intercept).
    // Force a re-fetch after every successful refresh so it picks up the correct tier data.
    queryClient.invalidateQueries({ queryKey: ['quota'] });
  },
  fail: () => { onRefreshFailed(); isRefreshing = false; },
};

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Handle 401 errors (token expired)
    // Skip for auth endpoints to prevent loops
    // Skip if user is null (anonymous) - don't silently re-authenticate via stale cookies
    const isAuthEndpoint = originalRequest.url?.startsWith('/auth/');
    const currentUser = useAuthStore.getState().user;
    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint && currentUser) {
      originalRequest._retry = true;

      // If already refreshing (either by AuthProvider init or a prior 401),
      // queue this request to be retried once the refresh completes.
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          addRefreshSubscriber((token) => {
            if (!token) {
              reject(error);
              return;
            }
            originalRequest.headers.Authorization = `Bearer ${token}`;
            resolve(api(originalRequest));
          });
        });
      }

      isRefreshing = true;

      try {
        // SECURITY: Refresh token sent automatically via httpOnly cookie
        const response = await authEndpoints.refresh();
        const newAccessToken = response.data.access_token;

        // Update access token in store
        useAuthStore.getState().setAccessToken(newAccessToken);

        // Retry original request with new token
        originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;

        // Notify queued requests and fix stale anonymous quota data
        onRefreshed(newAccessToken);
        isRefreshing = false;
        queryClient.invalidateQueries({ queryKey: ['quota'] });

        return api(originalRequest);
      } catch (refreshError) {
        // Refresh failed — reject all queued requests and clear auth
        onRefreshFailed();
        isRefreshing = false;
        useAuthStore.getState().clearAuth();
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

// ========== AUTH ENDPOINTS ==========

export const authEndpoints = {
  /**
   * Create or retrieve guest account.
   * Only called when user explicitly clicks "Continue as Guest".
   *
   * Device ID is obtained from httpOnly cookie (set by backend middleware).
   * No need to pass device_id in request body.
   */
  createGuest: () =>
    api.post('/auth/guest'),

  /**
   * Register new user or convert guest to registered.
   */
  register: (data: { username: string; email: string; password: string; preferred_language?: string }) =>
    api.post('/auth/register', data),

  /**
   * Login with email and password.
   */
  login: (data: { email: string; password: string; language?: string }) =>
    api.post('/auth/login', data),

  /**
   * Refresh access token using httpOnly cookie.
   * No body parameters - refresh token sent automatically.
   */
  refresh: () => api.post('/auth/refresh'),

  /**
   * Get current user profile.
   */
  getMe: () => api.get('/auth/me'),

  /**
   * Logout current user (revoke refresh token).
   */
  logout: () => api.post('/auth/logout'),

  /**
   * Logout from all devices.
   */
  logoutAll: () => api.post('/auth/logout-all'),

  /**
   * Verify email with token.
   */
  verifyEmail: (data: { token: string }) => api.post('/auth/verify-email', data),

  /**
   * Resend verification email.
   */
  resendVerification: () => api.post('/auth/resend-verification'),

  /**
   * Update the authenticated user's preferred language for transactional emails.
   * Fire-and-forget for registered (non-guest) users only.
   */
  updateLanguagePreference: (preferred_language: "en" | "zh") =>
    api.patch('/auth/update-language-preference', { preferred_language }),

  /**
   * Get quota/usage stats for current user or anonymous.
   * Works for all tiers: anonymous, guest, registered.
   */
  getQuota: () => api.get('/auth/quota'),

  /**
   * Delete user account permanently.
   * Requires password verification and confirmation phrase.
   */
  deleteAccount: (data: { password: string; confirm_phrase: string }) =>
    api.delete('/auth/account', { data }),

  /**
   * Clear guest data by orphaning the current guest account.
   * Called when user wants to "Clear Guest Data" and start fresh.
   * The device_id cookie is preserved so quota history carries over to any new guest account.
   */
  resetDeviceId: () =>
    api.post('/auth/reset-device-id'),

  /**
   * Request password reset email.
   * Always returns success to prevent user enumeration.
   */
  forgotPassword: (data: { email: string }) =>
    api.post('/auth/forgot-password', data),

  /**
   * Reset password using token from email.
   */
  resetPassword: (data: { token: string; new_password: string }) =>
    api.post('/auth/reset-password', data),

  /**
   * Change password (requires current password, must be logged in).
   */
  changePassword: (data: { current_password: string; new_password: string }) =>
    api.post('/auth/change-password', data),

  /**
   * Request email change (sends verification token to new email).
   * Requires current password for verification.
   */
  changeEmail: (data: { new_email: string; password: string }) =>
    api.post('/auth/change-email', data),

  /**
   * Confirm email change using token sent to new email.
   * No auth required - token serves as authentication.
   */
  confirmEmailChange: (data: { token: string }) =>
    api.post('/auth/confirm-email-change', data),
};

// ========== EXISTING ENDPOINTS ==========

// Helpers mapping to FastAPI endpoints
export const endpoints = {
  monsters: (q?: Record<string, string | number | boolean>) => api.get("/monsters", { params: q }),
  monsterById: (id: number | string) => api.get(`/monsters/${id}`),
  moves: (q?: Record<string, string | number | boolean>) => api.get("/moves", { params: q }),
  moveById: (id: number | string) => api.get(`/moves/${id}`),
  personalities: () => api.get("/personalities"),
  types: () => api.get("/types"),
  magicItems: () => api.get("/magic_items"),
  gameTerms: () => api.get("/game_terms"),

  listTeams: (q?: Record<string, string | number | boolean>) => api.get("/teams", { params: q }),
  getTeam: (id: number | string) => api.get(`/teams/${id}`),
  createTeam: (payload: any, lang?: "en" | "zh") => api.post("/teams", payload, { params: { lang: lang || "en" } }),
  updateTeam: (id: number | string, payload: any) => api.put(`/teams/${id}`, payload),
  deleteTeam: (id: number | string) => api.delete(`/teams/${id}`),

  analyzeTeam: (payload: any, language?: "en" | "zh") => api.post("/team/analyze", { team: payload, language: language || "en" }),
  analyzeTeamById: (payload: { team_id: number; language?: "en" | "zh" }) => api.post("/team/analyze_by_id", payload),

  // Saved analysis endpoints
  saveAnalysis: (payload: {
    team_id: number;
    language?: "en" | "zh";
    analysis_data: any;
    is_from_cache: boolean;
  }) => api.post("/analysis/save", payload),

  getSavedAnalysis: (team_id: number, language?: "en" | "zh") =>
    api.get(`/teams/${team_id}/analysis`, { params: { language: language || "en" } }),

  deleteSavedAnalysis: (team_id: number, language?: "en" | "zh") =>
    api.delete(`/teams/${team_id}/analysis`, { params: { language: language || "en" } }),

  forceRefresh: (payload: {
    team_id: number;
    language?: "en" | "zh";
    save_result?: boolean;
  }) => api.post("/team/force_refresh", payload),

  getQuotaStatus: (team_id?: number, language?: "en" | "zh") =>
    api.get("/quota/status", { params: { team_id, language: language || "en" } }),
};


// ========== ADMIN ENDPOINTS (Phase B) ==========

export interface AdminUser {
  id: number;
  username: string;
  email: string | null;
  is_guest: boolean;
  is_system: boolean;
  is_active: boolean;
  email_verified: boolean;
  subscription_tier: string;
  subscription_expires_at: string | null;
  created_at: string;
  last_login_at: string | null;
  last_active_at: string | null;
  failed_login_attempts: number;
  locked_until: string | null;
  device_id: string | null;
  guest_display_id: string | null;  // Unique 4-char ID for guest display
  teams_count: number;
  is_admin: boolean;
}

export interface AdminUserListResponse {
  users: AdminUser[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AdminStats {
  total_users: number;
  total_guests: number;
  total_registered: number;
  total_active: number;
  total_locked: number;
  total_teams: number;
  total_analyses: number;
  users_by_tier: Record<string, number>;
  registrations_today: number;
  registrations_this_week: number;
  registrations_this_month: number;
}

export interface AdminUserListParams {
  page?: number;
  page_size?: number;
  search?: string;
  tier?: string;
  is_guest?: boolean;
  is_active?: boolean;
}

export const adminEndpoints = {
  /**
   * List all users with pagination and filtering.
   * ADMIN ONLY.
   */
  listUsers: (params?: AdminUserListParams) =>
    api.get<AdminUserListResponse>('/admin/users', { params }),

  /**
   * Get detailed information about a specific user.
   * ADMIN ONLY.
   */
  getUser: (userId: number) =>
    api.get<AdminUser>(`/admin/users/${userId}`),

  /**
   * Change a user's subscription tier.
   * ADMIN ONLY.
   */
  changeTier: (userId: number, tier: string) =>
    api.put(`/admin/users/${userId}/tier`, { tier }),

  /**
   * Lock a user account.
   * ADMIN ONLY.
   */
  lockUser: (userId: number, data?: { reason?: string; duration_hours?: number }) =>
    api.post(`/admin/users/${userId}/lock`, data || {}),

  /**
   * Unlock a user account.
   * ADMIN ONLY.
   */
  unlockUser: (userId: number) =>
    api.post(`/admin/users/${userId}/unlock`),

  /**
   * Delete a user account.
   * ADMIN ONLY.
   */
  deleteUser: (userId: number, data?: { reason?: string; add_to_cooldown?: boolean }) =>
    api.delete(`/admin/users/${userId}`, { data: data || {} }),

  /**
   * Get system-wide statistics.
   * ADMIN ONLY.
   */
  getStats: () =>
    api.get<AdminStats>('/admin/stats'),

  /**
   * DEV ONLY: Reset all non-admin users.
   * ADMIN ONLY. Disabled in production.
   */
  resetUsers: () =>
    api.post('/admin/database/reset-users'),
};
