import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { authEndpoints } from "@/lib/api";
import { useAuthStore } from "./authStore";
import { useI18n } from "@/i18n";

interface EmailVerificationModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Token from registration response (dev mode) */
  initialToken?: string;
}

export default function EmailVerificationModal({
  isOpen,
  onClose,
  initialToken = "",
}: EmailVerificationModalProps) {
  const { t } = useI18n();
  const { user, updateUser } = useAuthStore();
  const [token, setToken] = useState(initialToken);

  const verifyMutation = useMutation({
    mutationFn: async () => {
      const response = await authEndpoints.verifyEmail({ token });
      return response.data;
    },
    onSuccess: () => {
      toast.success(t("auth.verifySuccess"));
      // Update user in store to reflect verified status
      if (user) {
        updateUser({ ...user, email_verified: true });
      }
      onClose();
    },
    onError: (error: any) => {
      const detail = error.response?.data?.detail;
      toast.error(detail || t("auth.verifyFailed"));
    },
  });

  const resendMutation = useMutation({
    mutationFn: async () => {
      const response = await authEndpoints.resendVerification();
      return response.data;
    },
    onSuccess: (data) => {
      toast.success(t("auth.resendSuccess"));
      // In dev mode, auto-fill the token
      if (data.debug_token) {
        setToken(data.debug_token);
      }
    },
    onError: () => {
      toast.error(t("auth.resendFailed"));
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (token.trim()) {
      verifyMutation.mutate();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
        <h2 className="text-xl font-semibold text-zinc-900 mb-2">
          {t("auth.verifyEmailTitle")}
        </h2>

        <p className="text-sm text-zinc-600 mb-4">
          {t("auth.verifyEmailMessage")}
        </p>

        {user?.email && (
          <p className="text-sm text-zinc-500 mb-4">
            Email: <span className="font-medium text-zinc-700">{user.email}</span>
          </p>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">
              {t("auth.verificationCode")}
            </label>
            <input
              type="text"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder={t("auth.verificationCodePlaceholder")}
              className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
              autoFocus
            />
          </div>

          <div className="flex gap-3">
            <button
              type="submit"
              disabled={verifyMutation.isPending || !token.trim()}
              className="flex-1 h-10 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed transition-colors"
            >
              {verifyMutation.isPending ? t("auth.verifying") : t("auth.verifyButton")}
            </button>

            <button
              type="button"
              onClick={() => resendMutation.mutate()}
              disabled={resendMutation.isPending}
              className="px-4 h-10 border border-zinc-300 text-zinc-700 rounded-md hover:bg-zinc-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {resendMutation.isPending ? t("auth.resending") : t("auth.resendCode")}
            </button>
          </div>
        </form>

        <button
          onClick={onClose}
          className="mt-4 w-full text-sm text-zinc-500 hover:text-zinc-700"
        >
          {t("auth.skipForNow")}
        </button>
      </div>
    </div>
  );
}
