import { useI18n } from "@/i18n";

interface ConfirmDialogProps {
  isOpen: boolean;
  message: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({ isOpen, message, onConfirm, onCancel }: ConfirmDialogProps) {
  const { t } = useI18n();
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="fixed inset-0 bg-black/40" onClick={onCancel} />
      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-sm p-6 flex flex-col gap-4">
        <p className="text-sm text-zinc-700 leading-relaxed">{message}</p>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="h-9 px-4 rounded-lg border-2 border-zinc-300 text-sm font-medium text-zinc-700 hover:bg-zinc-100 transition-colors cursor-pointer"
          >
            {t("common.cancel") ?? "Cancel"}
          </button>
          <button
            onClick={onConfirm}
            className="h-9 px-4 rounded-lg bg-zinc-800 text-sm font-medium text-white hover:bg-zinc-700 transition-colors cursor-pointer"
          >
            {t("common.ok") ?? "OK"}
          </button>
        </div>
      </div>
    </div>
  );
}
