import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { authEndpoints } from "@/lib/api";
import { useI18n } from "@/i18n";
import NoIndex from "@/components/NoIndex";

export default function ConfirmEmailChangePage() {
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";

  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const confirmMutation = useMutation({
    mutationFn: async () => {
      const response = await authEndpoints.confirmEmailChange({ token });
      return response.data;
    },
    onSuccess: () => {
      setConfirmed(true);
    },
    onError: (err: any) => {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : t("settings.emailChangConfirmFailed"));
    },
  });

  useEffect(() => {
    if (token) {
      confirmMutation.mutate();
    } else {
      setError(t("settings.emailChangConfirmFailed"));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <NoIndex nofollow />
      <div className="min-h-[calc(100vh-3.5rem)] flex items-center justify-center bg-zinc-50 px-4">
      <div className="w-full max-w-md bg-white rounded-lg shadow-sm border border-zinc-200 p-8">
        <h1 className="text-2xl font-semibold text-zinc-900 mb-6 text-center">
          {t("settings.confirmEmailChange")}
        </h1>

        {confirmMutation.isPending && (
          <p className="text-sm text-zinc-600 text-center">{t("auth.verifying")}</p>
        )}

        {confirmed && (
          <div className="space-y-4">
            <div className="p-3 rounded-md bg-green-50 border border-green-200 text-sm text-green-700">
              {t("settings.emailChanged")}
            </div>
            <Link
              to="/auth/login"
              className="flex items-center justify-center w-full h-10 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
            >
              {t("auth.loginButton")}
            </Link>
          </div>
        )}

        {error && (
          <div className="space-y-4">
            <div className="p-3 rounded-md bg-red-50 border border-red-200 text-sm text-red-700">
              {error}
            </div>
            <Link
              to="/settings"
              className="flex items-center justify-center w-full h-10 border border-zinc-300 text-zinc-700 rounded-md hover:bg-zinc-50 transition-colors"
            >
              {t("auth.back")}
            </Link>
          </div>
        )}
      </div>
    </div>
    </>
  );
}
