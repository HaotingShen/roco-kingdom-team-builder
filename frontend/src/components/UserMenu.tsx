import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '@/features/auth/authStore';
import { authEndpoints } from '@/lib/api';
import { useI18n } from '@/i18n';
import { useAuth } from '@/features/auth/AuthProvider';
import { useBuilderStore } from '@/features/builder/builderStore';
import DeleteAccountModal from '@/features/auth/DeleteAccountModal';
import EmailVerificationModal from '@/features/auth/EmailVerificationModal';
import ClearGuestDataModal from '@/features/auth/ClearGuestDataModal';
import { useQuota } from '@/hooks/useQuota';
import QuotaDisplay from '@/components/QuotaDisplay';

/**
 * User menu dropdown component for THREE-TIER system.
 *
 * Displays based on user state:
 *
 * 1. ANONYMOUS (user is null):
 *    - Shows "Log In" button (no dropdown)
 *
 * 2. GUEST (user.is_guest = true):
 *    - Avatar + "Guest" display name
 *    - Create Account
 *    - Log In
 *    - Log Out (becomes anonymous)
 *    - Clear Guest Data (new device_id, becomes anonymous)
 *
 * 3. REGISTERED (user.is_guest = false):
 *    - Avatar + username
 *    - Profile
 *    - Settings
 *    - Log Out (becomes anonymous)
 */
export default function UserMenu() {
  const [isOpen, setIsOpen] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showVerifyModal, setShowVerifyModal] = useState(false);
  const [showClearGuestModal, setShowClearGuestModal] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const { user, isGuest, clearAuth } = useAuthStore();
  const { isLoading } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const clearTeamId = useBuilderStore(s => s.clearTeamId);
  const setAnalysis = useBuilderStore(s => s.setAnalysis);
  const { quota } = useQuota();

  // Check if email needs verification (registered user with unverified email)
  const needsEmailVerification = !isGuest && user?.email && !user.email_verified;

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  /**
   * Handle logout for registered users.
   * - Logs out all devices (invalidates all sessions immediately)
   * - Becomes anonymous (no auto guest creation)
   */
  const handleLogout = async () => {
    setIsOpen(false);

    try {
      // IMPORTANT: Call logout BEFORE clearing auth state
      // Otherwise the access token is null and logout API returns 401,
      // leaving the refresh token cookie valid (user can still refresh)
      // logoutAll increments token_version → invalidates all sessions on all devices
      await authEndpoints.logoutAll();
    } catch (error) {
      // Ignore logout errors - user might already be logged out
      console.error('Logout API failed (continuing anyway):', error);
    }

    // Clear local auth state AFTER logout API call
    clearAuth();
    // Clear cached data (teams, etc.) so next user doesn't see old data
    queryClient.clear();
    // Clear teamId and analysis (keep local draft: slots, name, magic item)
    clearTeamId();
    setAnalysis(null);

    // User is now anonymous - do NOT create guest
    navigate('/build');
  };

  /**
   * Handle "Log Out" for guest users.
   * - Logs out and becomes anonymous
   * - Guest account persists in DB, can reclaim via "Continue as Guest"
   */
  const handleGuestLogout = async () => {
    setIsOpen(false);

    try {
      // IMPORTANT: Call logout BEFORE clearing auth state
      // Otherwise the access token is null and logout API returns 401,
      // leaving the refresh token cookie valid
      await authEndpoints.logout();
    } catch (error) {
      // Ignore logout errors
      console.error('Logout API failed (continuing anyway):', error);
    }

    // Clear local auth state AFTER logout API call
    clearAuth();
    // Clear cached data (teams, etc.) so next user doesn't see old data
    queryClient.clear();
    // Clear teamId and analysis (keep local draft: slots, name, magic item)
    clearTeamId();
    setAnalysis(null);

    // User is now anonymous - guest account persists for later reclaim
    navigate('/build');
  };

  /**
   * Handle "Clear Guest Data" for guest users.
   * - Orphans the current guest account (makes it inaccessible)
   * - User becomes anonymous on the same device_id (quota history preserved)
   * - Old guest data remains in DB but cannot be reclaimed
   */
  const handleClearGuestData = async () => {
    try {
      // IMPORTANT: Call logout BEFORE clearing auth state
      await authEndpoints.logout();
    } catch (error) {
      // Ignore logout errors
      console.error('Logout API failed (continuing anyway):', error);
    }

    try {
      // Orphan the guest account via backend (device_id cookie is kept intact)
      await authEndpoints.resetDeviceId();
    } catch (error) {
      // Continue even if reset fails
      console.error('Reset device ID failed (continuing anyway):', error);
    }

    // Clear local auth state AFTER logout API call
    clearAuth();
    // Clear cached data (teams, etc.) so next user doesn't see old data
    queryClient.clear();
    // Clear teamId and analysis (keep local draft: slots, name, magic item)
    clearTeamId();
    setAnalysis(null);

    // User is now anonymous on the same device_id
    // Do NOT auto-create guest - user must explicitly choose
    navigate('/build');
  };

  // Still loading auth state
  if (isLoading) {
    return (
      <div className="h-9 px-3 flex items-center">
        <div className="w-5 h-5 border-2 border-zinc-300 border-t-zinc-600 rounded-full animate-spin" />
      </div>
    );
  }

  // ANONYMOUS: No user - show "Log In" button
  if (!user) {
    return (
      <button
        onClick={() => navigate('/auth/login')}
        className="h-9 px-4 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
      >
        {t('userMenu.login') || 'Log In'}
      </button>
    );
  }

  // Display username (show "Guest#XXXX" for guests using the unique display ID)
  const displayName = user.is_guest && user.guest_display_id
    ? `${t('userMenu.guest') || 'Guest'}#${user.guest_display_id}`
    : user.username;

  // First letter of display name for avatar
  const avatarLetter = displayName.charAt(0).toUpperCase();

  // Avatar background color based on guest status
  const avatarBg = isGuest
    ? 'bg-zinc-400'
    : 'bg-blue-600';

  return (
    <div className="relative" ref={menuRef}>
      {/* User button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 h-9 px-2 rounded-lg border-2 border-zinc-300 hover:bg-zinc-100 transition-colors cursor-pointer"
      >
        {/* Avatar with warning indicator for unverified email */}
        <div className="relative">
          <div className={`w-7 h-7 rounded-full ${avatarBg} text-white flex items-center justify-center text-sm font-medium`}>
            {avatarLetter}
          </div>
          {needsEmailVerification && (
            <div className="absolute -top-1 -right-1 w-3.5 h-3.5 bg-amber-500 rounded-full flex items-center justify-center" title={t('auth.emailNotVerified')}>
              <span className="text-white text-[9px] font-bold">!</span>
            </div>
          )}
        </div>

        {/* Username — hidden on mobile to keep topbar compact */}
        <span className="hidden sm:inline text-sm text-zinc-700 max-w-[100px] truncate">
          {displayName}
        </span>

        {/* Dropdown arrow */}
        <svg className="w-4 h-4 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown menu */}
      {isOpen && (
        <div className="absolute right-0 mt-1 w-48 max-w-[calc(100vw-1rem)] bg-white border border-zinc-200 rounded-lg shadow-lg py-1 z-50">
          {isGuest ? (
            <>
              {/* Guest menu items */}
              <div className="px-3 py-2 border-b border-zinc-100">
                <p className="text-xs text-zinc-500">
                  {t('userMenu.guestInfo') || 'Create an account to sync across devices.'}
                </p>
              </div>

              <QuotaDisplay quota={quota} variant="menu" />

              <button
                onClick={() => {
                  setIsOpen(false);
                  navigate('/auth/register');
                }}
                className="w-full text-left px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
              >
                {t('userMenu.createAccount') || 'Create Account'}
              </button>

              <button
                onClick={() => {
                  setIsOpen(false);
                  navigate('/auth/login');
                }}
                className="w-full text-left px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
              >
                {t('userMenu.login') || 'Log In'}
              </button>

              <div className="border-t border-zinc-100 my-1" />

              <button
                onClick={handleGuestLogout}
                className="w-full text-left px-3 py-2 text-sm text-zinc-500 hover:bg-zinc-50"
              >
                {t('userMenu.logout') || 'Log Out'}
              </button>

              <button
                onClick={() => {
                  setIsOpen(false);
                  setShowClearGuestModal(true);
                }}
                className="w-full text-left px-3 py-2 text-sm text-red-600 hover:bg-zinc-50"
              >
                {t('userMenu.clearGuestData') || 'Clear Guest Data'}
              </button>
            </>
          ) : (
            <>
              {/* Registered user menu items */}
              <div className="px-3 py-2 border-b border-zinc-100">
                <p className="text-sm font-medium text-zinc-800 truncate">{user.username}</p>
                {user.email && (
                  <p className="text-xs text-zinc-500 truncate">{user.email}</p>
                )}
              </div>

              {/* Email verification banner - only for registered users with unverified email */}
              {needsEmailVerification && (
                <div className="px-3 py-2 bg-amber-50 border-b border-amber-200">
                  <p className="text-xs text-amber-700 mb-1.5">
                    {t('auth.emailNotVerifiedBanner')}
                  </p>
                  <button
                    onClick={() => {
                      setIsOpen(false);
                      setShowVerifyModal(true);
                    }}
                    className="text-xs font-medium text-amber-800 hover:text-amber-900 underline"
                  >
                    {t('auth.verifyNow')}
                  </button>
                </div>
              )}

              <QuotaDisplay quota={quota} variant="menu" />

              {/* TODO: Profile page not yet implemented */}

              <button
                onClick={() => {
                  setIsOpen(false);
                  navigate('/settings');
                }}
                className="w-full text-left px-3 py-2 text-sm text-zinc-700 hover:bg-zinc-50"
              >
                {t('userMenu.settings') || 'Settings'}
              </button>

              <div className="border-t border-zinc-100 my-1" />

              <button
                onClick={handleLogout}
                className="w-full text-left px-3 py-2 text-sm text-zinc-500 hover:bg-zinc-50"
              >
                {t('userMenu.logout') || 'Log Out'}
              </button>

              <button
                onClick={() => {
                  setIsOpen(false);
                  setShowDeleteModal(true);
                }}
                className="w-full text-left px-3 py-2 text-sm text-red-600 hover:bg-zinc-50"
              >
                {t('userMenu.deleteAccount') || 'Delete Account'}
              </button>
            </>
          )}
        </div>
      )}

      {/* Delete Account Modal */}
      <DeleteAccountModal
        isOpen={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
      />

      {/* Email Verification Modal */}
      <EmailVerificationModal
        isOpen={showVerifyModal}
        onClose={() => setShowVerifyModal(false)}
      />

      {/* Clear Guest Data Modal */}
      <ClearGuestDataModal
        isOpen={showClearGuestModal}
        onClose={() => setShowClearGuestModal(false)}
        onConfirm={handleClearGuestData}
      />
    </div>
  );
}
