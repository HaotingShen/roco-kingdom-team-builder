import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { authEndpoints } from "@/lib/api";
import { useAuthStore, hasDeviceRegistered } from "./authStore";
import { useI18n } from "@/i18n";

export default function LoginPage() {
  const navigate = useNavigate();
  const { t, lang, setLang } = useI18n();
  const { setAuth } = useAuthStore();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  // Hide "Continue as Guest" if device has a registered account
  const showGuestOption = !hasDeviceRegistered();

  const loginMutation = useMutation({
    mutationFn: async () => {
      const response = await authEndpoints.login({ email, password, language: lang });
      return response.data;
    },
    onSuccess: (data) => {
      setAuth(data.user, data.access_token);
      // Apply user's stored language preference across devices
      if (!data.user.is_guest && data.user.preferred_language) {
        setLang(data.user.preferred_language as "en" | "zh");
      }
      toast.success(t("auth.loginSuccess"));
      navigate("/build");
    },
    onError: (error: any) => {
      const status = error.response?.status;
      const detail = error.response?.data?.detail;
      // Map known backend error messages to i18n keys
      let message: string;
      if (status === 429) {
        // Rate limited - backend returns localized message, use directly
        message = typeof detail === "string" ? detail : (t("auth.loginRateLimited") || "Too many login attempts. Please wait a few minutes before trying again.");
      } else if (detail === "Invalid email or password") {
        message = t("auth.invalidCredentials") || "Invalid email or password.";
      } else if (status === 403 && typeof detail === "string") {
        // Account locked - backend returns localized message, use directly
        message = detail;
      } else if (typeof detail === "string") {
        message = detail;
      } else {
        message = t("auth.loginFailed") || "Login failed.";
      }
      toast.error(message);
    },
  });

  const guestMutation = useMutation({
    mutationFn: async () => {
      // Device ID is obtained from httpOnly cookie (set by backend middleware)
      const response = await authEndpoints.createGuest();
      return response.data;
    },
    onSuccess: (data) => {
      setAuth(data.user, data.access_token);
      const message = data.is_returning_guest
        ? (t("auth.guestReturned") || "Welcome back!")
        : (t("auth.guestCreated") || "Guest account created!");
      toast.success(message);
      navigate("/build");
    },
    onError: (error: any) => {
      if (error.response?.status === 429) {
        toast.error(
          t("auth.guestRateLimited") ||
          "You have reached the daily guest account limit. Please create a registered account or try again tomorrow."
        );
      } else {
        toast.error(t("auth.guestFailed") || "Failed to create guest account.");
      }
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loginMutation.mutate();
  };

  const handleContinueAsGuest = () => {
    guestMutation.mutate();
  };

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center bg-zinc-50 px-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow-sm border border-zinc-200 p-8 relative">
        {/* Back button */}
        <button
          onClick={() => navigate(-1)}
          className="absolute top-4 left-4 flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-700 transition-colors"
          title={t("auth.backToPrevious")}
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          {t("auth.back")}
        </button>

        <h1 className="text-2xl font-semibold text-zinc-900 mb-6 text-center mt-4">
          {t("auth.loginTitle")}
        </h1>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">
              {t("auth.email")}
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t("auth.emailPlaceholder")}
              required
              className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-sm font-medium text-zinc-700">
                {t("auth.password")}
              </label>
              <Link
                to="/auth/forgot-password"
                className="text-xs text-blue-600 hover:text-blue-700"
              >
                {t("auth.forgotPassword")}
              </Link>
            </div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t("auth.passwordPlaceholder")}
              required
              className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          <button
            type="submit"
            disabled={loginMutation.isPending}
            className="w-full h-10 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed transition-colors"
          >
            {loginMutation.isPending ? t("auth.loggingIn") : t("auth.loginButton")}
          </button>
        </form>

        <div className="mt-6 text-center text-sm text-zinc-600">
          {t("auth.noAccount")}{" "}
          <Link
            to="/auth/register"
            className="text-blue-600 hover:text-blue-700 font-medium"
          >
            {t("auth.signUpLink")}
          </Link>
        </div>

        {/* Continue as Guest section - hidden if device has registered account */}
        {showGuestOption && (
          <div className="mt-6 pt-6 border-t border-zinc-200">
            <button
              onClick={handleContinueAsGuest}
              disabled={guestMutation.isPending}
              className="w-full h-10 bg-zinc-100 text-zinc-700 rounded-md hover:bg-zinc-200 disabled:bg-zinc-100 disabled:cursor-not-allowed transition-colors text-sm font-medium"
            >
              {guestMutation.isPending
                ? (t("auth.processingGuest") || "Processing...")
                : (t("auth.continueAsGuest") || "Continue as Guest")}
            </button>
            <p className="mt-2 text-xs text-center text-zinc-500">
              {t("auth.guestDisclaimer") || "Guest teams expire after 90 days of inactivity."}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
