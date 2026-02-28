import { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { authEndpoints } from "@/lib/api";
import { useI18n } from "@/i18n";

export default function VerifyEmailPage() {
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  const tokenFromUrl = searchParams.get("token") || "";

  const [token, setToken] = useState(tokenFromUrl);
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resendSuccess, setResendSuccess] = useState(false);

  const verifyMutation = useMutation({
    mutationFn: async (t: string) => {
      const response = await authEndpoints.verifyEmail({ token: t.trim() });
      return response.data;
    },
    onSuccess: () => {
      setVerified(true);
      setError(null);
    },
    onError: (err: any) => {
      const detail = err.response?.data?.detail;
      setError(detail || t("auth.verifyFailed"));
    },
  });

  const resendMutation = useMutation({
    mutationFn: async () => {
      const response = await authEndpoints.resendVerification();
      return response.data;
    },
    onSuccess: () => {
      setResendSuccess(true);
      setError(null);
    },
    onError: (err: any) => {
      const detail = err.response?.data?.detail;
      setError(detail || t("auth.resendFailed"));
    },
  });

  // Auto-verify if token is in the URL
  useEffect(() => {
    if (tokenFromUrl) {
      verifyMutation.mutate(tokenFromUrl);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    verifyMutation.mutate(token);
  };

  return (
    <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center bg-zinc-50 px-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow-sm border border-zinc-200 p-8">
        <h1 className="text-2xl font-semibold text-zinc-900 mb-2 text-center">
          {t("auth.verifyEmailTitle")}
        </h1>

        {verified ? (
          <div className="text-center space-y-4">
            <div className="p-3 rounded-md bg-green-50 border border-green-200 text-sm text-green-700">
              {t("auth.verifySuccess")}
            </div>
            <Link
              to="/auth/login"
              className="block w-full h-10 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors flex items-center justify-center"
            >
              {t("auth.loginButton")}
            </Link>
          </div>
        ) : (
          <>
            {verifyMutation.isPending ? (
              <p className="text-sm text-zinc-600 text-center mb-6">
                {t("auth.verifying")}
              </p>
            ) : (
              <p className="text-sm text-zinc-600 mb-6 text-center">
                {t("auth.verifyEmailMessage")}
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
                  required
                  className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
                />
              </div>

              {error && (
                <div className="p-3 rounded-md bg-red-50 border border-red-200 text-sm text-red-700">
                  {error}
                </div>
              )}

              {resendSuccess && (
                <div className="p-3 rounded-md bg-green-50 border border-green-200 text-sm text-green-700">
                  {t("auth.resendSuccess")}
                </div>
              )}

              <button
                type="submit"
                disabled={verifyMutation.isPending || !token.trim()}
                className="w-full h-10 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed transition-colors"
              >
                {verifyMutation.isPending ? t("auth.verifying") : t("auth.verifyButton")}
              </button>
            </form>

            <div className="mt-6 text-center space-y-2">
              <button
                onClick={() => resendMutation.mutate()}
                disabled={resendMutation.isPending}
                className="block w-full text-sm text-zinc-600 hover:text-zinc-800 disabled:opacity-50"
              >
                {resendMutation.isPending ? t("auth.resending") : t("auth.resendCode")}
              </button>
              <Link
                to="/"
                className="block text-sm text-zinc-600 hover:text-zinc-800"
              >
                {t("auth.skipForNow")}
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
