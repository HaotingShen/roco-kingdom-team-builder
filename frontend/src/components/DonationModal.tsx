import { useI18n } from "@/i18n";
import { paymentImageUrl } from "@/lib/images";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export default function DonationModal({ isOpen, onClose }: Props) {
  const { t } = useI18n();

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center pb-16 lg:pb-0">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-amber-50 to-orange-50 border-b border-amber-100 px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xl">❤️</span>
            <h2 className="text-lg font-semibold text-zinc-800">{t("donation.title")}</h2>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-600 transition-colors cursor-pointer p-1 rounded-lg hover:bg-amber-100"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Message */}
        <div className="px-6 py-5 text-center space-y-1">
          <p className="text-zinc-800 font-medium">{t("donation.line1")}</p>
          <p className="text-zinc-600 text-sm">{t("donation.line2")}</p>
          <p className="text-zinc-700 font-medium pt-1">{t("donation.line3")}</p>
          <p className="text-zinc-500 text-sm pt-1">{t("donation.line4")}</p>
        </div>

        {/* QR Codes */}
        <div className="px-6 pb-5 flex flex-col sm:flex-row gap-4 justify-center items-center">
          {/* WeChat Pay */}
          <div className="flex flex-col items-center gap-2">
            <div className="rounded-xl border-2 border-[#07C160] overflow-hidden shadow-sm">
              <div className="bg-[#07C160] px-3 py-1 text-center">
                <span className="text-white text-xs font-medium">{t("donation.wechat")}</span>
              </div>
              <div className="p-2 bg-white">
                <img
                  src={paymentImageUrl("wechat.jpg")}
                  alt={t("donation.wechat") ?? "WeChat Pay"}
                  className="w-28 h-28 sm:w-36 sm:h-36 object-cover"
                />
              </div>
            </div>
          </div>

          {/* Alipay */}
          <div className="flex flex-col items-center gap-2">
            <div className="rounded-xl border-2 border-[#1677FF] overflow-hidden shadow-sm">
              <div className="bg-[#1677FF] px-3 py-1 text-center">
                <span className="text-white text-xs font-medium">{t("donation.alipay")}</span>
              </div>
              <div className="p-2 bg-white">
                <img
                  src={paymentImageUrl("alipay.jpg")}
                  alt={t("donation.alipay") ?? "Alipay"}
                  className="w-28 h-28 sm:w-36 sm:h-36 object-cover"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 pb-5 text-center">
          <p className="text-zinc-400 text-xs">{t("donation.footer")}</p>
        </div>
      </div>
    </div>
  );
}
