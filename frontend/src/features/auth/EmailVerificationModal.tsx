import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { authEndpoints } from "@/lib/api";
import { useI18n } from "@/i18n";
import { useAuthStore } from "./authStore";

interface EmailVerificationModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function EmailVerificationModal({
  isOpen,
  onClose,
}: EmailVerificationModalProps) {
  const { t } = useI18n();
  const { user } = useAuthStore();

  const resendMutation = useMutation({
    mutationFn: async () => {
      const response = await authEndpoints.resendVerification();
      return response.data;
    },
    onSuccess: () => {
      toast.success(t("auth.resendSuccess"));
    },
    onError: () => {
      toast.error(t("auth.resendFailed"));
    },
  });

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
          <p className="text-sm text-zinc-500 mb-6">
            {t("auth.email")}: <span className="font-medium text-zinc-700">{user.email}</span>
          </p>
        )}

        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => resendMutation.mutate()}
            disabled={resendMutation.isPending}
            className="flex-1 h-10 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {resendMutation.isPending ? t("auth.resending") : t("auth.resendCode")}
          </button>

          <button
            type="button"
            onClick={onClose}
            className="flex-1 h-10 border border-zinc-300 text-zinc-700 rounded-md hover:bg-zinc-50 transition-colors"
          >
            {t("auth.closeModal")}
          </button>
        </div>
      </div>
    </div>
  );
}
