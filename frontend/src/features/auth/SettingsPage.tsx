import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { authEndpoints } from "@/lib/api";
import { useAuthStore } from "./authStore";
import { useI18n } from "@/i18n";
import NoIndex from "@/components/NoIndex";

export default function SettingsPage() {
  const navigate = useNavigate();
  const { t, lang, setLang } = useI18n();
  const { user, isGuest, clearAuth, updateUser } = useAuthStore();

  // --- Change Password state ---
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  // --- Change Email state ---
  const [newEmail, setNewEmail] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [emailChangeStep, setEmailChangeStep] = useState<"request" | "sent">("request");

  // --- Change Password mutation ---
  const changePasswordMutation = useMutation({
    mutationFn: async () => {
      const response = await authEndpoints.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      return response.data;
    },
    onSuccess: () => {
      toast.success(t("settings.passwordChanged"));
      clearAuth();
      navigate("/auth/login");
    },
    onError: (error: any) => {
      const detail = error.response?.data?.detail;
      let message: string;
      if (Array.isArray(detail)) {
        message = detail[0]?.msg || t("settings.passwordChangeFailed");
      } else if (typeof detail === "string") {
        message = detail;
      } else {
        message = t("settings.passwordChangeFailed");
      }
      toast.error(message);
    },
  });

  // --- Request Email Change mutation ---
  const requestEmailChangeMutation = useMutation({
    mutationFn: async () => {
      const response = await authEndpoints.changeEmail({
        new_email: newEmail,
        password: emailPassword,
      });
      return response.data;
    },
    onSuccess: () => {
      setEmailChangeStep("sent");
    },
    onError: (error: any) => {
      const detail = error.response?.data?.detail;
      let message: string;
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail)) {
        message = detail[0]?.msg || t("settings.emailChangeFailed");
      } else {
        message = t("settings.emailChangeFailed");
      }
      toast.error(message);
    },
  });

  // --- Update Language Preference mutation ---
  const updateLangMutation = useMutation({
    mutationFn: async (newLang: "en" | "zh") => {
      const response = await authEndpoints.updateLanguagePreference(newLang);
      return { data: response.data, newLang };
    },
    onSuccess: ({ newLang }) => {
      setLang(newLang);
      // Update persisted user object so AuthProvider syncs correctly on reload
      if (user) {
        updateUser({ ...user, preferred_language: newLang });
      }
      toast.success(t("settings.languageChanged"));
    },
    onError: () => {
      toast.error(t("settings.languageChangeFailed"));
    },
  });

  const handleChangePassword = (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      toast.error(t("settings.passwordMismatch"));
      return;
    }
    changePasswordMutation.mutate();
  };

  const handleRequestEmailChange = (e: React.FormEvent) => {
    e.preventDefault();
    requestEmailChangeMutation.mutate();
  };

  // Auth guard: not logged in
  if (!user) {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center bg-zinc-50 px-4">
        <div className="text-center">
          <p className="text-zinc-600 mb-4">{t("settings.loginRequired")}</p>
          <button
            onClick={() => navigate("/auth/login")}
            className="h-10 px-6 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            {t("userMenu.login")}
          </button>
        </div>
      </div>
    );
  }

  // Auth guard: guest users
  if (isGuest) {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center bg-zinc-50 px-4">
        <div className="text-center">
          <p className="text-zinc-600 mb-4">{t("settings.registeredOnly")}</p>
          <button
            onClick={() => navigate("/auth/register")}
            className="h-10 px-6 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
          >
            {t("userMenu.createAccount")}
          </button>
        </div>
      </div>
    );
  }

  const isPasswordValid =
    currentPassword.length > 0 &&
    newPassword.length >= 8 &&
    confirmPassword.length > 0;

  const isEmailRequestValid =
    newEmail.length > 0 &&
    newEmail.includes("@") &&
    newEmail.includes(".") &&
    emailPassword.length > 0;

  return (
    <>
      <NoIndex nofollow />
      <div className="min-h-[calc(100vh-3.5rem)] flex items-start justify-center bg-zinc-50 px-4 py-8">
      <div className="w-full max-w-lg">
        {/* Header */}
        <div className="mb-6 relative">
          <button
            onClick={() => navigate(-1)}
            className="absolute top-0 left-0 flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-700 transition-colors"
            title={t("auth.backToPrevious")}
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            {t("auth.back")}
          </button>
          <h1 className="text-2xl font-semibold text-zinc-900 text-center">
            {t("settings.title")}
          </h1>
        </div>

        {/* Change Password Section */}
        <div className="bg-white rounded-lg shadow-sm border border-zinc-200 p-6 mb-6">
          <h2 className="text-lg font-medium text-zinc-900 mb-4">
            {t("settings.changePassword")}
          </h2>

          <form onSubmit={handleChangePassword} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-zinc-700 mb-1">
                {t("settings.currentPassword")}
              </label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                placeholder={t("settings.currentPasswordPlaceholder")}
                required
                className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-700 mb-1">
                {t("settings.newPassword")}
              </label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder={t("settings.newPasswordPlaceholder")}
                autoComplete="new-password"
                required
                minLength={8}
                className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <p className="text-xs text-zinc-500 mt-1">
                {t("auth.passwordRequirements")}
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-zinc-700 mb-1">
                {t("settings.confirmNewPassword")}
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder={t("settings.confirmNewPasswordPlaceholder")}
                autoComplete="new-password"
                required
                className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            <button
              type="submit"
              disabled={!isPasswordValid || changePasswordMutation.isPending}
              className="w-full h-10 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed transition-colors"
            >
              {changePasswordMutation.isPending
                ? t("settings.changingPassword")
                : t("settings.changePasswordButton")}
            </button>
          </form>
        </div>

        {/* Change Email Section */}
        <div className="bg-white rounded-lg shadow-sm border border-zinc-200 p-6 mb-6">
          <h2 className="text-lg font-medium text-zinc-900 mb-1">
            {t("settings.changeEmail")}
          </h2>
          {user.email && (
            <p className="text-sm text-zinc-500 mb-4">
              {user.email}
            </p>
          )}

          {emailChangeStep === "sent" ? (
            <div className="space-y-4">
              <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                <p className="text-sm text-green-800">
                  {t("settings.confirmEmailDescription")}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setEmailChangeStep("request");
                  setNewEmail("");
                  setEmailPassword("");
                }}
                className="w-full h-10 border border-zinc-300 text-zinc-700 rounded-md hover:bg-zinc-50 transition-colors"
              >
                {t("auth.back")}
              </button>
            </div>
          ) : (
            <form onSubmit={handleRequestEmailChange} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-zinc-700 mb-1">
                  {t("settings.newEmail")}
                </label>
                <input
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder={t("settings.newEmailPlaceholder")}
                  required
                  className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-zinc-700 mb-1">
                  {t("settings.password")}
                </label>
                <input
                  type="password"
                  value={emailPassword}
                  onChange={(e) => setEmailPassword(e.target.value)}
                  placeholder={t("settings.passwordPlaceholder")}
                  required
                  className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                />
              </div>

              <button
                type="submit"
                disabled={!isEmailRequestValid || requestEmailChangeMutation.isPending}
                className="w-full h-10 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed transition-colors"
              >
                {requestEmailChangeMutation.isPending
                  ? t("settings.sendingVerification")
                  : t("settings.sendVerification")}
              </button>
            </form>
          )}
        </div>
        {/* Language Preference Section */}
        <div className="bg-white rounded-lg shadow-sm border border-zinc-200 p-6">
          <h2 className="text-lg font-medium text-zinc-900 mb-4">
            {t("settings.languagePreference")}
          </h2>
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-zinc-700 mb-1">
                {t("settings.selectLanguage")}
              </label>
              <select
                value={lang}
                onChange={(e) => updateLangMutation.mutate(e.target.value as "en" | "zh")}
                disabled={updateLangMutation.isPending}
                className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white disabled:bg-zinc-50 disabled:cursor-not-allowed"
              >
                <option value="en">English</option>
                <option value="zh">中文</option>
              </select>
              <p className="text-xs text-zinc-500 mt-1">
                {t("settings.languageHint")}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
    </>
  );
}
