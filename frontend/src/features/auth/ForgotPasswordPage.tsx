import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { authEndpoints } from "@/lib/api";
import { useI18n } from "@/i18n";
import { useLocalizedPath } from "@/lib/locale";
import NoIndex from "@/components/NoIndex";

export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const localized = useLocalizedPath();
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const forgotMutation = useMutation({
    mutationFn: async () => {
      const response = await authEndpoints.forgotPassword({ email });
      return response.data;
    },
    onSuccess: () => {
      setSubmitted(true);
      toast.success(t("auth.forgotPasswordSuccess"));
    },
    onError: (error: any) => {
      // Rate limit error
      if (error.response?.status === 429) {
        toast.error(t("auth.forgotPasswordRateLimited"));
      } else {
        // For security, still show success message even on error
        // to prevent user enumeration
        setSubmitted(true);
        toast.success(t("auth.forgotPasswordSuccess"));
      }
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (email.trim()) {
      forgotMutation.mutate();
    }
  };

  if (submitted) {
    return (
      <>
        <NoIndex nofollow />
        <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center bg-zinc-50 px-4">
        <div className="w-full max-w-md bg-white rounded-lg shadow-sm border border-zinc-200 p-8 text-center">
          <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>

          <h1 className="text-2xl font-semibold text-zinc-900 mb-2">
            {t("auth.checkYourEmail")}
          </h1>

          <p className="text-sm text-zinc-600 mb-6">
            {t("auth.forgotPasswordSent")}
          </p>

          <div className="space-y-3">
            <Link
              to={localized("/auth/reset-password")}
              className="block w-full h-10 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors flex items-center justify-center"
            >
              {t("auth.enterResetCode")}
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

  return (
    <>
      <NoIndex nofollow />
      <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center bg-zinc-50 px-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow-sm border border-zinc-200 p-8">
        <h1 className="text-2xl font-semibold text-zinc-900 mb-2 text-center">
          {t("auth.forgotPasswordTitle")}
        </h1>

        <p className="text-sm text-zinc-600 mb-6 text-center">
          {t("auth.forgotPasswordDescription")}
        </p>

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
              autoFocus
              className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          <button
            type="submit"
            disabled={forgotMutation.isPending || !email.trim()}
            className="w-full h-10 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed transition-colors"
          >
            {forgotMutation.isPending ? t("auth.sending") : t("auth.sendResetLink")}
          </button>
        </form>

        <div className="mt-6 text-center">
          <Link
            to={localized("/auth/login")}
            className="text-sm text-zinc-600 hover:text-zinc-800"
          >
            {t("auth.backToLogin")}
          </Link>
        </div>
      </div>
    </div>
    </>
  );
}
