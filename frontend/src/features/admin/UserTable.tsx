import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { adminEndpoints, type AdminUser, type AdminUserListParams } from "@/lib/api";
import { useI18n } from "@/i18n";
import UserModal from "./UserModal";

/**
 * User management table for admin dashboard.
 *
 * Features:
 * - Paginated user list
 * - Search by username/email
 * - Filter by tier, guest status, active status
 * - Actions: view details, change tier, lock/unlock, delete
 */
export default function UserTable() {
  const { t } = useI18n();
  const queryClient = useQueryClient();

  // State
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [search, setSearch] = useState("");
  const [tierFilter, setTierFilter] = useState<string>("");
  const [guestFilter, setGuestFilter] = useState<string>("");
  const [activeFilter, setActiveFilter] = useState<string>("");
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null);

  // Build query params
  const params: AdminUserListParams = {
    page,
    page_size: pageSize,
  };
  if (search) params.search = search;
  if (tierFilter) params.tier = tierFilter;
  if (guestFilter) params.is_guest = guestFilter === "true";
  if (activeFilter) params.is_active = activeFilter === "true";

  // Fetch users
  const usersQuery = useQuery({
    queryKey: ["admin", "users", params],
    queryFn: async () => {
      const response = await adminEndpoints.listUsers(params);
      return response.data;
    },
  });

  // Lock user mutation
  const lockMutation = useMutation({
    mutationFn: (userId: number) => adminEndpoints.lockUser(userId),
    onSuccess: () => {
      toast.success(t("admin.userLocked") || "User locked");
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to lock user");
    },
  });

  // Unlock user mutation
  const unlockMutation = useMutation({
    mutationFn: (userId: number) => adminEndpoints.unlockUser(userId),
    onSuccess: () => {
      toast.success(t("admin.userUnlocked") || "User unlocked");
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to unlock user");
    },
  });

  // Delete user mutation
  const deleteMutation = useMutation({
    mutationFn: (userId: number) => adminEndpoints.deleteUser(userId),
    onSuccess: () => {
      toast.success(t("admin.userDeleted") || "User deleted");
      queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
      queryClient.invalidateQueries({ queryKey: ["admin", "stats"] });
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || "Failed to delete user");
    },
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
  };

  const handleDelete = (user: AdminUser) => {
    if (
      window.confirm(
        `${t("admin.confirmDelete") || "Delete user"} "${user.username}"? ${
          t("admin.cannotUndo") || "This cannot be undone."
        }`
      )
    ) {
      deleteMutation.mutate(user.id);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleDateString();
  };

  // Format guest display name using the unique guest_display_id
  const formatUsername = (user: { username: string; is_guest: boolean; guest_display_id: string | null }) => {
    if (user.is_guest && user.guest_display_id) {
      return `Guest#${user.guest_display_id}`;
    }
    return user.username;
  };

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-end">
        {/* Search */}
        <form onSubmit={handleSearch} className="flex-1 min-w-[200px]">
          <label className="block text-xs text-zinc-500 mb-1">
            {t("admin.search") || "Search"}
          </label>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("admin.searchPlaceholder") || "Username or email..."}
            className="w-full h-9 px-3 border border-zinc-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </form>

        {/* Tier Filter */}
        <div>
          <label className="block text-xs text-zinc-500 mb-1">
            {t("admin.tier") || "Tier"}
          </label>
          <select
            value={tierFilter}
            onChange={(e) => {
              setTierFilter(e.target.value);
              setPage(1);
            }}
            className="h-9 px-2 border border-zinc-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">{t("admin.allTiers") || "All"}</option>
            <option value="anonymous">Anonymous</option>
            <option value="guest">Guest</option>
            <option value="free">Free</option>
            <option value="premium">Premium</option>
            <option value="unlimited">Unlimited</option>
          </select>
        </div>

        {/* Guest Filter */}
        <div>
          <label className="block text-xs text-zinc-500 mb-1">
            {t("admin.accountType") || "Type"}
          </label>
          <select
            value={guestFilter}
            onChange={(e) => {
              setGuestFilter(e.target.value);
              setPage(1);
            }}
            className="h-9 px-2 border border-zinc-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">{t("admin.all") || "All"}</option>
            <option value="true">{t("admin.guests") || "Guests"}</option>
            <option value="false">{t("admin.registered") || "Registered"}</option>
          </select>
        </div>

        {/* Active Filter */}
        <div>
          <label className="block text-xs text-zinc-500 mb-1">
            {t("admin.status") || "Status"}
          </label>
          <select
            value={activeFilter}
            onChange={(e) => {
              setActiveFilter(e.target.value);
              setPage(1);
            }}
            className="h-9 px-2 border border-zinc-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">{t("admin.all") || "All"}</option>
            <option value="true">{t("admin.active") || "Active"}</option>
            <option value="false">{t("admin.locked") || "Locked"}</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="border border-zinc-200 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-zinc-50 border-b border-zinc-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-zinc-700">
                  {t("admin.user") || "User"}
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-700">
                  {t("admin.email") || "Email"}
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-700">
                  {t("admin.tier") || "Tier"}
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-700">
                  {t("admin.status") || "Status"}
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-700">
                  {t("admin.teams") || "Teams"}
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-700">
                  {t("admin.lastActive") || "Last Active"}
                </th>
                <th className="text-left px-4 py-3 font-medium text-zinc-700">
                  {t("admin.created") || "Created"}
                </th>
                <th className="text-right px-4 py-3 font-medium text-zinc-700">
                  {t("admin.actions") || "Actions"}
                </th>
              </tr>
            </thead>
            <tbody>
              {usersQuery.isLoading ? (
                <tr>
                  <td colSpan={8} className="text-center py-8 text-zinc-500">
                    {t("common.loading") || "Loading..."}
                  </td>
                </tr>
              ) : usersQuery.data?.users.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center py-8 text-zinc-500">
                    {t("admin.noUsers") || "No users found"}
                  </td>
                </tr>
              ) : (
                usersQuery.data?.users.map((user) => (
                  <tr
                    key={user.id}
                    className="border-b border-zinc-100 hover:bg-zinc-50"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">
                          {formatUsername(user)}
                        </span>
                        {user.is_admin && (
                          <span className="px-1.5 py-0.5 bg-purple-100 text-purple-700 text-xs rounded">
                            Admin
                          </span>
                        )}
                        {user.is_system && (
                          <span className="px-1.5 py-0.5 bg-zinc-100 text-zinc-600 text-xs rounded">
                            System
                          </span>
                        )}
                        {user.is_guest && (
                          <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 text-xs rounded">
                            Guest
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-zinc-600">
                      {user.email || "-"}
                      {user.email && !user.email_verified && (
                        <span className="ml-1 text-amber-500" title="Not verified">
                          (!)
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded text-xs ${
                          user.subscription_tier === "unlimited"
                            ? "bg-purple-100 text-purple-700"
                            : user.subscription_tier === "premium"
                            ? "bg-blue-100 text-blue-700"
                            : "bg-zinc-100 text-zinc-600"
                        }`}
                      >
                        {user.subscription_tier}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {user.is_active ? (
                        <span className="text-green-600">
                          {t("admin.active") || "Active"}
                        </span>
                      ) : (
                        <span className="text-red-600">
                          {t("admin.locked") || "Locked"}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-zinc-600">{user.teams_count}</td>
                    <td className="px-4 py-3 text-zinc-600">
                      {formatDate(user.last_active_at)}
                    </td>
                    <td className="px-4 py-3 text-zinc-600">
                      {formatDate(user.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1">
                        <button
                          onClick={() => setSelectedUser(user)}
                          className="px-2 py-1 text-xs text-blue-600 hover:bg-blue-50 rounded"
                        >
                          {t("admin.view") || "View"}
                        </button>
                        {!user.is_system && !user.is_admin && (
                          <>
                            {user.is_active ? (
                              <button
                                onClick={() => lockMutation.mutate(user.id)}
                                disabled={lockMutation.isPending}
                                className="px-2 py-1 text-xs text-amber-600 hover:bg-amber-50 rounded disabled:opacity-50"
                              >
                                {t("admin.lock") || "Lock"}
                              </button>
                            ) : (
                              <button
                                onClick={() => unlockMutation.mutate(user.id)}
                                disabled={unlockMutation.isPending}
                                className="px-2 py-1 text-xs text-green-600 hover:bg-green-50 rounded disabled:opacity-50"
                              >
                                {t("admin.unlock") || "Unlock"}
                              </button>
                            )}
                            <button
                              onClick={() => handleDelete(user)}
                              disabled={deleteMutation.isPending}
                              className="px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded disabled:opacity-50"
                            >
                              {t("admin.delete") || "Delete"}
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {usersQuery.data && usersQuery.data.total_pages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <div className="text-zinc-500">
            {t("admin.showingResults") || "Showing"}{" "}
            {(page - 1) * pageSize + 1}-
            {Math.min(page * pageSize, usersQuery.data.total)}{" "}
            {t("admin.of") || "of"} {usersQuery.data.total}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-3 py-1 border border-zinc-300 rounded hover:bg-zinc-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t("admin.previous") || "Previous"}
            </button>
            <span className="px-3 py-1">
              {page} / {usersQuery.data.total_pages}
            </span>
            <button
              onClick={() =>
                setPage((p) => Math.min(usersQuery.data!.total_pages, p + 1))
              }
              disabled={page === usersQuery.data.total_pages}
              className="px-3 py-1 border border-zinc-300 rounded hover:bg-zinc-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {t("admin.next") || "Next"}
            </button>
          </div>
        </div>
      )}

      {/* User Modal */}
      {selectedUser && (
        <UserModal
          user={selectedUser}
          onClose={() => setSelectedUser(null)}
        />
      )}
    </div>
  );
}
