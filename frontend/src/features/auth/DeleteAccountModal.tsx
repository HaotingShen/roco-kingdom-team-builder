import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { authEndpoints } from "@/lib/api";
import { useAuthStore, clearDeviceRegistered } from "./authStore";
import { useI18n } from "@/i18n";

interface DeleteAccountModalProps {
  isOpen: boolean;
  onClose: () => void;
}

/**
 * Modal for permanent account deletion.
 *
 * Requires:
 * - Password verification
 * - Typing "DELETE MY ACCOUNT" to confirm
 *
 * WARNING: This action is irreversible. All user data will be deleted.
 */
export default function DeleteAccountModal({
  isOpen,
  onClose,
}: DeleteAccountModalProps) {
  const { t } = useI18n();
  const { clearAuth } = useAuthStore();
  const navigate = useNavigate();

  const [password, setPassword] = useState("");
  const [confirmPhrase, setConfirmPhrase] = useState("");

  const CONFIRM_PHRASE = "DELETE MY ACCOUNT";

  const deleteMutation = useMutation({
    mutationFn: async () => {
      const response = await authEndpoints.deleteAccount({
        password,
        confirm_phrase: confirmPhrase,
      });
      return response.data;
    },
    onSuccess: () => {
      // Clear auth state and allow guest creation again
      clearAuth();
      clearDeviceRegistered();
      toast.success(t("auth.accountDeleted") || "Your account has been permanently deleted.");
      onClose();
      navigate("/");
    },
    onError: (error: any) => {
      const detail = error.response?.data?.detail;
      // Handle Pydantic validation errors (array of objects) vs simple string errors
      let errorMessage: string;
      if (Array.isArray(detail)) {
        // Extract first validation error message
        errorMessage = detail[0]?.msg || t("auth.deleteFailed") || "Failed to delete account.";
      } else if (typeof detail === "string") {
        errorMessage = detail;
      } else {
        errorMessage = t("auth.deleteFailed") || "Failed to delete account.";
      }
      toast.error(errorMessage);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (confirmPhrase !== CONFIRM_PHRASE) {
      toast.error(
        t("auth.deleteConfirmMismatch") ||
          `Please type "${CONFIRM_PHRASE}" to confirm.`
      );
      return;
    }

    deleteMutation.mutate();
  };

  const handleClose = () => {
    // Reset form state
    setPassword("");
    setConfirmPhrase("");
    onClose();
  };

  if (!isOpen) return null;

  const isValid = password.length > 0 && confirmPhrase === CONFIRM_PHRASE;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
        <h2 className="text-xl font-semibold text-red-600 mb-4">
          {t("auth.deleteAccountTitle") || "Delete Account"}
        </h2>

        {/* Warning banner */}
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
          <p className="text-sm text-red-800">
            <strong>{t("auth.warning") || "Warning"}:</strong>{" "}
            {t("auth.deleteWarning") ||
              "This action is permanent and cannot be undone. All your teams and data will be deleted."}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Password field */}
          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">
              {t("auth.password") || "Password"}
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t("auth.enterPassword") || "Enter your password"}
              required
              className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
            />
          </div>

          {/* Confirmation phrase field */}
          <div>
            <label className="block text-sm font-medium text-zinc-700 mb-1">
              {t("auth.confirmDelete") || `Type "${CONFIRM_PHRASE}" to confirm`}
            </label>
            <input
              type="text"
              value={confirmPhrase}
              onChange={(e) => setConfirmPhrase(e.target.value)}
              placeholder={CONFIRM_PHRASE}
              required
              className="w-full h-10 px-3 border border-zinc-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent font-mono"
            />
          </div>

          {/* Action buttons */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={handleClose}
              className="flex-1 h-10 border border-zinc-300 text-zinc-700 rounded-md hover:bg-zinc-50 transition-colors"
            >
              {t("common.cancel") || "Cancel"}
            </button>
            <button
              type="submit"
              disabled={!isValid || deleteMutation.isPending}
              className="flex-1 h-10 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:bg-red-400 disabled:cursor-not-allowed transition-colors"
            >
              {deleteMutation.isPending
                ? t("auth.deleting") || "Deleting..."
                : t("auth.deleteForever") || "Delete Forever"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
