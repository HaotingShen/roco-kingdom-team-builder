import { useNavigate } from 'react-router-dom';
import { useI18n } from '@/i18n';
import { authEndpoints } from '@/lib/api';
import { useAuthStore, hasDeviceRegistered } from '@/features/auth/authStore';
import { toast } from 'sonner';
import { useState } from 'react';

interface SaveTeamModalProps {
  isOpen: boolean;
  onClose: () => void;
  onGuestCreated?: () => void;  // Called after guest account created
}

/**
 * Modal shown when anonymous user tries to save a team.
 *
 * Options:
 * 1. Create Account (primary) - redirects to registration
 * 2. Continue as Guest (secondary) - creates guest account, then saves
 * 3. Already have an account? Log in - redirects to login
 */
export default function SaveTeamModal({ isOpen, onClose, onGuestCreated }: SaveTeamModalProps) {
  const navigate = useNavigate();
  const { t } = useI18n();
  const { setAuth } = useAuthStore();
  const [isCreatingGuest, setIsCreatingGuest] = useState(false);

  // Hide "Continue as Guest" if device has a registered account
  const showGuestOption = !hasDeviceRegistered();

  if (!isOpen) return null;

  const handleCreateAccount = () => {
    onClose();
    navigate('/auth/register');
  };

  const handleLogin = () => {
    onClose();
    navigate('/auth/login');
  };

  const handleContinueAsGuest = async () => {
    setIsCreatingGuest(true);

    try {
      // Device ID is obtained from httpOnly cookie (set by backend middleware)
      const response = await authEndpoints.createGuest();
      setAuth(response.data.user, response.data.access_token);

      // Show appropriate message based on whether this is a new or returning guest
      const isReturning = response.data.is_returning_guest;
      const message = isReturning
        ? (t('saveModal.guestReturned') || 'Welcome back! You can now save teams.')
        : (t('saveModal.guestCreated') || 'Guest account created! You can now save teams.');
      toast.success(message);
      onClose();

      // Callback to trigger save after guest created
      if (onGuestCreated) {
        onGuestCreated();
      }
    } catch (error: any) {
      console.error('Failed to create guest account:', error);

      // Check for rate limit error
      if (error.response?.status === 429) {
        toast.error(
          t('saveModal.guestRateLimited') ||
          'You have reached the daily guest account limit. Please create a registered account or try again tomorrow.'
        );
      } else {
        toast.error(t('saveModal.guestFailed') || 'Failed to create guest account. Please try again.');
      }
    } finally {
      setIsCreatingGuest(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-zinc-400 hover:text-zinc-600"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {import.meta.env.VITE_HIDE_AUTH ? (
          <>
            <h2 className="text-xl font-semibold text-zinc-900 mb-4">
              {t('saveModal.title') || 'Save Your Team'}
            </h2>
            <p className="text-sm text-zinc-600">
              {t('saveModal.taptapRedirect') ||
                'Visit rkteambuilder.com to save and share your team.'}
            </p>
          </>
        ) : (
          <>
            {/* Title */}
            <h2 className="text-xl font-semibold text-zinc-900 mb-2">
              {t('saveModal.title') || 'Save Your Team'}
            </h2>

            {/* Description */}
            <p className="text-sm text-zinc-600 mb-6">
              {showGuestOption
                ? (t('saveModal.description') ||
                   'Create an account to sync across devices, or continue as guest (saved on this device only).')
                : (t('saveModal.descriptionNoGuest') ||
                   'Create an account or log in to save your team.')}
            </p>

            {/* Primary: Create Account */}
            <button
              onClick={handleCreateAccount}
              className="w-full h-11 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors mb-3"
            >
              {t('saveModal.createAccount') || 'Create Account'}
            </button>

            {/* Secondary: Continue as Guest - hidden if device has registered account */}
            {showGuestOption && (
              <>
                <button
                  onClick={handleContinueAsGuest}
                  disabled={isCreatingGuest}
                  className="w-full h-11 bg-zinc-100 text-zinc-700 font-medium rounded-lg hover:bg-zinc-200 transition-colors disabled:opacity-50 disabled:cursor-not-allowed mb-2"
                >
                  {isCreatingGuest
                    ? (t('saveModal.creatingGuest') || 'Creating...')
                    : (t('saveModal.continueAsGuest') || 'Continue as Guest')}
                </button>

                {/* Guest disclaimer */}
                <p className="text-xs text-zinc-500 text-center mb-4">
                  {t('saveModal.guestDisclaimer') || 'Guest teams expire after 90 days of inactivity.'}
                </p>
              </>
            )}

            {/* Divider */}
            <div className="border-t border-zinc-200 my-4" />

            {/* Login link */}
            <p className="text-sm text-center text-zinc-600">
              {t('saveModal.haveAccount') || 'Already have an account?'}{' '}
              <button
                onClick={handleLogin}
                className="text-blue-600 hover:text-blue-700 font-medium"
              >
                {t('saveModal.loginLink') || 'Log in'}
              </button>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
