import { useI18n } from "@/i18n";

interface ClearGuestDataModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

/**
 * Confirmation modal for clearing guest data.
 *
 * This action:
 * - Generates a new device_id
 * - Makes the old guest account inaccessible
 * - All saved teams on this guest will be lost
 */
export default function ClearGuestDataModal({
  isOpen,
  onClose,
  onConfirm,
}: ClearGuestDataModalProps) {
  const { t } = useI18n();

  if (!isOpen) return null;

  const handleConfirm = () => {
    onConfirm();
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
        <h2 className="text-xl font-semibold text-red-600 mb-4">
          {t("userMenu.clearGuestData") || "Clear Guest Data"}
        </h2>

        {/* Warning banner */}
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
          <p className="text-sm text-red-800">
            <strong>{t("auth.warning") || "Warning"}:</strong>{" "}
            {t("userMenu.clearGuestWarning") ||
              "This will permanently disconnect you from this guest account. All teams saved to this guest will become inaccessible."}
          </p>
        </div>

        <p className="text-sm text-zinc-600 mb-6">
          {t("userMenu.clearGuestExplanation") ||
            "A new guest account will be created if you continue as guest again."}
        </p>

        {/* Action buttons */}
        <div className="flex gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 h-10 border border-zinc-300 text-zinc-700 rounded-md hover:bg-zinc-50 transition-colors"
          >
            {t("common.cancel") || "Cancel"}
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            className="flex-1 h-10 bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors"
          >
            {t("userMenu.clearGuestConfirm") || "Clear Data"}
          </button>
        </div>
      </div>
    </div>
  );
}
