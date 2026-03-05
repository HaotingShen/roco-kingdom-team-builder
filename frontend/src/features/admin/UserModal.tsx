import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { adminEndpoints, type AdminUser } from "@/lib/api";
import { useI18n } from "@/i18n";

interface UserModalProps {
  user: AdminUser;
  onClose: () => void;
}

/**
 * User details modal for admin.
 *
 * Shows detailed user information and allows:
 * - Viewing all user fields
 * - Changing subscription tier
 * - Locking/unlocking with reason and duration
 */
export default function UserModal({ user, onClose }: UserModalProps) {
  const { t } = useI18n();
  const queryClient = useQueryClient();

  // Change tier state
  const [newTier, setNewTier] = useState(user.subscription_tier);
  const [showTierForm, setShowTierForm] = useState(false);

  // Lock state
  const [showLockForm, setShowLockForm] = useState(false);
  const [lockReason, setLockReason] = useState("");
  const [lockDuration, setLockDuration] = useState<number | undefined>(undefined);

  // Change tier mutation
  const tierMutation = useMutation({
    mutationFn: () => adminEndpoints.changeTier(user.id, newTier),
    onSuccess: () => {
      toast.success(t("admin.tierChanged") || "Tier changed successfully");
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      setShowTierForm(false);
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to change tier");
    },
  });

  // Lock mutation
  const lockMutation = useMutation({
    mutationFn: () =>
      adminEndpoints.lockUser(user.id, {
        reason: lockReason || undefined,
        duration_hours: lockDuration,
      }),
    onSuccess: () => {
      toast.success(t("admin.userLocked") || "User locked");
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      setShowLockForm(false);
      onClose();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to lock user");
    },
  });

  // Unlock mutation
  const unlockMutation = useMutation({
    mutationFn: () => adminEndpoints.unlockUser(user.id),
    onSuccess: () => {
      toast.success(t("admin.userUnlocked") || "User unlocked");
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      onClose();
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to unlock user");
    },
  });

  const formatDateTime = (dateStr: string | null) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };

  // Format display name using the unique guest_display_id
  const displayName = user.is_guest && user.guest_display_id
    ? `Guest#${user.guest_display_id}`
    : user.username;

  const canModify = !user.is_system && !user.is_admin;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-200">
          <div>
            <h2 className="text-lg font-semibold text-zinc-900">
              {t("admin.userDetails") || "User Details"}
            </h2>
            <p className="text-sm text-zinc-500">{displayName}</p>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-600"
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="px-6 py-4 space-y-6">
          {/* Badges */}
          <div className="flex flex-wrap gap-2">
            {user.is_admin && (
              <span className="px-2 py-1 bg-purple-100 text-purple-700 text-sm rounded">
                Admin
              </span>
            )}
            {user.is_system && (
              <span className="px-2 py-1 bg-zinc-100 text-zinc-600 text-sm rounded">
                System User
              </span>
            )}
            {user.is_guest && (
              <span className="px-2 py-1 bg-amber-100 text-amber-700 text-sm rounded">
                Guest Account
              </span>
            )}
            {!user.is_active && (
              <span className="px-2 py-1 bg-red-100 text-red-700 text-sm rounded">
                Locked
              </span>
            )}
            {user.email && !user.email_verified && (
              <span className="px-2 py-1 bg-amber-100 text-amber-700 text-sm rounded">
                Email Not Verified
              </span>
            )}
          </div>

          {/* Info Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <InfoRow label={t("admin.userId") || "User ID"} value={user.id} />
            <InfoRow label={t("admin.username") || "Username"} value={displayName} />
            <InfoRow label={t("admin.email") || "Email"} value={user.email || "-"} />
            <InfoRow
              label={t("admin.tier") || "Subscription Tier"}
              value={user.subscription_tier}
            />
            <InfoRow
              label={t("admin.teams") || "Teams"}
              value={user.teams_count}
            />
            <InfoRow
              label={t("admin.failedLogins") || "Failed Logins"}
              value={user.failed_login_attempts}
            />
            <InfoRow
              label={t("admin.created") || "Created"}
              value={formatDateTime(user.created_at)}
            />
            <InfoRow
              label={t("admin.lastLogin") || "Last Login"}
              value={formatDateTime(user.last_login_at)}
            />
            <InfoRow
              label={t("admin.lastActive") || "Last Active"}
              value={formatDateTime(user.last_active_at)}
            />
            <InfoRow
              label={t("admin.lockedUntil") || "Locked Until"}
              value={user.locked_until ? formatDateTime(user.locked_until) : "-"}
            />
            {user.device_id && (
              <InfoRow
                label={t("admin.deviceId") || "Device ID"}
                value={user.device_id}
              />
            )}
          </div>

          {/* Actions */}
          {canModify && (
            <div className="space-y-4 pt-4 border-t border-zinc-200">
              {/* Change Tier */}
              {!showTierForm ? (
                <button
                  onClick={() => setShowTierForm(true)}
                  className="text-sm text-blue-600 hover:underline"
                >
                  {t("admin.changeTier") || "Change Subscription Tier"}
                </button>
              ) : (
                <div className="bg-zinc-50 rounded-lg p-4 space-y-3">
                  <h4 className="font-medium text-zinc-900">
                    {t("admin.changeTier") || "Change Subscription Tier"}
                  </h4>
                  <select
                    value={newTier}
                    onChange={(e) => setNewTier(e.target.value)}
                    className="w-full h-9 px-3 border border-zinc-300 rounded text-sm"
                  >
                    <option value="guest">Guest</option>
                    <option value="free">Free</option>
                    <option value="premium">Premium</option>
                    <option value="unlimited">Unlimited</option>
                  </select>
                  <div className="flex gap-2">
                    <button
                      onClick={() => tierMutation.mutate()}
                      disabled={tierMutation.isPending || newTier === user.subscription_tier}
                      className="px-3 py-1.5 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50"
                    >
                      {tierMutation.isPending
                        ? (t("common.saving") || "Saving...")
                        : (t("common.save") || "Save")}
                    </button>
                    <button
                      onClick={() => {
                        setShowTierForm(false);
                        setNewTier(user.subscription_tier);
                      }}
                      className="px-3 py-1.5 border border-zinc-300 text-sm rounded hover:bg-zinc-50"
                    >
                      {t("common.cancel") || "Cancel"}
                    </button>
                  </div>
                </div>
              )}

              {/* Lock/Unlock */}
              {user.is_active ? (
                !showLockForm ? (
                  <button
                    onClick={() => setShowLockForm(true)}
                    className="text-sm text-amber-600 hover:underline"
                  >
                    {t("admin.lockUser") || "Lock User Account"}
                  </button>
                ) : (
                  <div className="bg-amber-50 rounded-lg p-4 space-y-3">
                    <h4 className="font-medium text-amber-900">
                      {t("admin.lockUser") || "Lock User Account"}
                    </h4>
                    <div>
                      <label className="block text-xs text-zinc-600 mb-1">
                        {t("admin.lockReason") || "Reason (optional)"}
                      </label>
                      <input
                        type="text"
                        value={lockReason}
                        onChange={(e) => setLockReason(e.target.value)}
                        placeholder={t("admin.lockReasonPlaceholder") || "e.g., Terms of service violation"}
                        className="w-full h-9 px-3 border border-zinc-300 rounded text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-zinc-600 mb-1">
                        {t("admin.lockDuration") || "Duration (hours, leave empty for indefinite)"}
                      </label>
                      <input
                        type="number"
                        value={lockDuration || ""}
                        onChange={(e) =>
                          setLockDuration(e.target.value ? parseInt(e.target.value) : undefined)
                        }
                        min={1}
                        max={8760}
                        placeholder={t("admin.indefinite") || "Indefinite"}
                        className="w-full h-9 px-3 border border-zinc-300 rounded text-sm"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={() => lockMutation.mutate()}
                        disabled={lockMutation.isPending}
                        className="px-3 py-1.5 bg-amber-600 text-white text-sm rounded hover:bg-amber-700 disabled:opacity-50"
                      >
                        {lockMutation.isPending
                          ? (t("admin.locking") || "Locking...")
                          : (t("admin.lock") || "Lock")}
                      </button>
                      <button
                        onClick={() => {
                          setShowLockForm(false);
                          setLockReason("");
                          setLockDuration(undefined);
                        }}
                        className="px-3 py-1.5 border border-zinc-300 text-sm rounded hover:bg-zinc-50"
                      >
                        {t("common.cancel") || "Cancel"}
                      </button>
                    </div>
                  </div>
                )
              ) : (
                <button
                  onClick={() => unlockMutation.mutate()}
                  disabled={unlockMutation.isPending}
                  className="text-sm text-green-600 hover:underline disabled:opacity-50"
                >
                  {unlockMutation.isPending
                    ? (t("admin.unlocking") || "Unlocking...")
                    : (t("admin.unlockUser") || "Unlock User Account")}
                </button>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-zinc-200 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 border border-zinc-300 text-zinc-700 rounded hover:bg-zinc-50"
          >
            {t("common.close") || "Close"}
          </button>
        </div>
      </div>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="text-zinc-900">{value}</div>
    </div>
  );
}
