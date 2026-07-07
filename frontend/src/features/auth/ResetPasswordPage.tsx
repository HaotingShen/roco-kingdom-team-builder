import { useState } from "react";
import { useNavigate, Link, useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { authEndpoints } from "@/lib/api";
import { useI18n } from "@/i18n";
import { useLocalizedPath } from "@/lib/locale";
import NoIndex from "@/components/NoIndex";

export default function ResetPasswordPage() {
  const navigate = useNavigate();
  const { t } = useI18n();
  const localized = useLocalizedPath();
  const [searchParams] = useSearchParams();

  // Token can come from URL query param (?token=xxx) or manual entry
  const [token, setToken] = useState(searchParams.get("token") || "");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const resetMutation = useMutation({
    mutationFn: async () => {
      const response = await authEndpoints.resetPassword({
        token: token.trim(),
        new_password: newPassword,
      });
      return response.data;
    },
    onSuccess: () => {
      toast.success(t("auth.passwordResetSuccess"));
      navigate(localized("/auth/login"));
    },
    onError: (error: any) => {
      const detail = error.response?.data?.detail;
      if (detail === "Invalid or expired reset token") {
        setError(t("auth.invalidResetToken"));
      } else if (detail === "Reset token has expired") {
        setError(t("auth.resetTokenExpired"));
      } else if (error.response?.status === 429) {
        setError(t("auth.resetPasswordRateLimited"));
      } else {
        setError(detail || t("auth.resetPasswordFailed"));
      }
    },
  });

  const validatePassword = (): boolean => {
    // Clear previous error
    setError(null);

    if (!token.trim()) {
      setError(t("auth.enterResetToken"));
      return false;
    }

    if (newPassword.length < 8) {
      setError(t("auth.passwordTooShort"));
      return false;
    }

    if (!/[A-Z]/.test(newPassword)) {
      setError(t("auth.passwordNeedsUppercase"));
      return false;
    }

    if (!/[a-z]/.test(newPassword)) {
      setError(t("auth.passwordNeedsLowercase"));
      return false;
    }

    if (!/[0-9]/.test(newPassword)) {
      setError(t("auth.passwordNeedsNumber"));
      return false;
    }

    if (newPassword !== confirmPassword) {
      setError(t("auth.passwordMismatch"));
      return false;
    }

    return true;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (validatePassword()) {
      resetMutation.mutate();
    }
  };

  return (
    <>
      <NoIndex nofollow />
      <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center bg-zinc-50 px-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow-sm border border-zinc-200 p-8">
        <h1 className="text-2xl font-semibold text-zinc-900 mb-2 text-center">
          {t("auth.resetPasswordTitle")}
        </h1>

        <p className="text-sm text-zinc-600 mb-6 text-center">
          {t("auth.resetPasswordDescription")}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">
              {t("auth.resetToken")}
            </label>
            <input
              type="text"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              placeholder={t("auth.resetTokenPlaceholder")}
              required
              className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
            />
            <p className="mt-1 text-xs text-zinc-500">
              {t("auth.resetTokenHint")}
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">
              {t("auth.newPassword")}
            </label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder={t("auth.newPasswordPlaceholder")}
              autoComplete="new-password"
              required
              className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">
              {t("auth.confirmNewPassword")}
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder={t("auth.confirmNewPasswordPlaceholder")}
              autoComplete="new-password"
              required
              className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          <p className="text-xs text-zinc-500">
            {t("auth.passwordRequirements")}
          </p>

          {error && (
            <div className="p-3 rounded-md bg-red-50 border border-red-200 text-sm text-red-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={resetMutation.isPending}
            className="w-full h-10 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed transition-colors"
          >
            {resetMutation.isPending ? t("auth.resetting") : t("auth.resetPasswordButton")}
          </button>
        </form>

        <div className="mt-6 text-center space-y-2">
          <Link
            to={localized("/auth/forgot-password")}
            className="block text-sm text-zinc-600 hover:text-zinc-800"
          >
            {t("auth.needNewToken")}
          </Link>
          <Link
            to={localized("/auth/login")}
            className="block text-sm text-zinc-600 hover:text-zinc-800"
          >
            {t("auth.backToLogin")}
          </Link>
        </div>
      </div>
    </div>
    </>
  );
}
