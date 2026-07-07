import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Navigate } from "react-router-dom";
import { useAuthStore } from "@/features/auth/authStore";
import { adminEndpoints, type AdminStats } from "@/lib/api";
import { useI18n } from "@/i18n";
import { useLocalizedPath } from "@/lib/locale";
import UserTable from "./UserTable";
import FeaturedTeamsTab from "./FeaturedTeamsTab";
import NoIndex from "@/components/NoIndex";

/**
 * Admin Dashboard Page
 *
 * Features:
 * - System statistics overview
 * - User management table with search/filter
 * - Actions: view, change tier, lock/unlock, delete
 *
 * Access: Admin users only (identified by ADMIN_EMAILS env var)
 */
export default function AdminPage() {
  const { t } = useI18n();
  const localized = useLocalizedPath();
  const { user } = useAuthStore();
  const [activeTab, setActiveTab] = useState<"stats" | "users" | "featured">("stats");

  // Check if user is admin (backend will verify, this is just for UI)
  const statsQuery = useQuery({
    queryKey: ["admin", "stats"],
    queryFn: async () => {
      const response = await adminEndpoints.getStats();
      return response.data;
    },
    retry: false,
  });

  // If not logged in, redirect to home
  if (!user) {
    return <Navigate to={localized("/")} replace />;
  }

  // If query failed with 403, user is not admin
  if (statsQuery.error) {
    const errorMessage = (statsQuery.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
    if (errorMessage?.includes("Admin")) {
      return (
        <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
          <div className="text-6xl mb-4">403</div>
          <h1 className="text-2xl font-semibold text-zinc-900 mb-2">
            {t("admin.accessDenied") || "Access Denied"}
          </h1>
          <p className="text-zinc-600 max-w-md">
            {t("admin.notAdmin") || "You do not have admin privileges. This page is restricted to administrators."}
          </p>
        </div>
      );
    }
  }

  return (
    <>
      <NoIndex nofollow />
      <div className="max-w-7xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-zinc-900">
          {t("admin.title") || "Admin Dashboard"}
        </h1>
        <p className="text-zinc-500 mt-1">
          {t("admin.subtitle") || "Manage users and view system statistics"}
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 mb-6 border-b border-zinc-200">
        <button
          onClick={() => setActiveTab("stats")}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
            activeTab === "stats"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-zinc-500 hover:text-zinc-700"
          }`}
        >
          {t("admin.statsTab") || "Statistics"}
        </button>
        <button
          onClick={() => setActiveTab("users")}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
            activeTab === "users"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-zinc-500 hover:text-zinc-700"
          }`}
        >
          {t("admin.usersTab") || "Users"}
        </button>
        <button
          onClick={() => setActiveTab("featured")}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
            activeTab === "featured"
              ? "border-purple-600 text-purple-600"
              : "border-transparent text-zinc-500 hover:text-zinc-700"
          }`}
        >
          {t("admin.featuredTeamsTab") || "Featured Teams"}
        </button>
      </div>

      {/* Content */}
      {activeTab === "stats" && (
        <StatsPanel stats={statsQuery.data} isLoading={statsQuery.isLoading} />
      )}
      {activeTab === "users" && <UserTable />}
      {activeTab === "featured" && <FeaturedTeamsTab />}
    </div>
    </>
  );
}

interface StatsPanelProps {
  stats?: AdminStats;
  isLoading: boolean;
}

function StatsPanel({ stats, isLoading }: StatsPanelProps) {
  const { t } = useI18n();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin h-8 w-8 border-2 border-blue-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="text-center py-12 text-zinc-500">
        {t("admin.statsError") || "Failed to load statistics"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Main Stats Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard
          label={t("admin.totalUsers") || "Total Users"}
          value={stats.total_users}
        />
        <StatCard
          label={t("admin.registeredUsers") || "Registered"}
          value={stats.total_registered}
        />
        <StatCard
          label={t("admin.guestUsers") || "Guests"}
          value={stats.total_guests}
        />
        <StatCard
          label={t("admin.activeUsers") || "Active (30d)"}
          value={stats.total_active}
        />
      </div>

      {/* Secondary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard
          label={t("admin.totalTeams") || "Total Teams"}
          value={stats.total_teams}
        />
        <StatCard
          label={t("admin.featuredTeamsTotal") || "Featured Teams"}
          value={stats.total_featured_teams}
        />
        <StatCard
          label={t("admin.totalAnalyses") || "Total Analyses"}
          value={stats.total_analyses}
        />
        <StatCard
          label={t("admin.lockedUsers") || "Locked"}
          value={stats.total_locked}
          highlight={stats.total_locked > 0 ? "warning" : undefined}
        />
        <StatCard
          label={t("admin.guestConversions") || "Guest Conversions"}
          value={stats.guest_conversions}
        />
      </div>

      {/* Registration Trends */}
      <div className="bg-white border border-zinc-200 rounded-lg p-4">
        <h3 className="font-medium text-zinc-900 mb-3">
          {t("admin.registrationTrends") || "Registration Trends"}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-2xl font-semibold text-zinc-900">
              {stats.registrations_today}
            </div>
            <div className="text-sm text-zinc-500">
              {t("admin.today") || "Today"}
            </div>
          </div>
          <div>
            <div className="text-2xl font-semibold text-zinc-900">
              {stats.registrations_this_week}
            </div>
            <div className="text-sm text-zinc-500">
              {t("admin.thisWeek") || "This Week"}
            </div>
          </div>
          <div>
            <div className="text-2xl font-semibold text-zinc-900">
              {stats.registrations_this_month}
            </div>
            <div className="text-sm text-zinc-500">
              {t("admin.thisMonth") || "This Month"}
            </div>
          </div>
        </div>
      </div>

      {/* Analysis Trends */}
      <div className="bg-white border border-zinc-200 rounded-lg p-4">
        <h3 className="font-medium text-zinc-900 mb-3">
          {t("admin.analysisTrends") || "Analysis Trends"}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-2xl font-semibold text-zinc-900">
              {stats.analyses_today}
            </div>
            <div className="text-sm text-zinc-500">
              {t("admin.today") || "Today"}
            </div>
          </div>
          <div>
            <div className="text-2xl font-semibold text-zinc-900">
              {stats.analyses_this_week}
            </div>
            <div className="text-sm text-zinc-500">
              {t("admin.thisWeek") || "This Week"}
            </div>
          </div>
          <div>
            <div className="text-2xl font-semibold text-zinc-900">
              {stats.analyses_this_month}
            </div>
            <div className="text-sm text-zinc-500">
              {t("admin.thisMonth") || "This Month"}
            </div>
          </div>
        </div>
      </div>

      {/* Users by Tier */}
      <div className="bg-white border border-zinc-200 rounded-lg p-4">
        <h3 className="font-medium text-zinc-900 mb-3">
          {t("admin.usersByTier") || "Users by Tier"}
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {Object.entries(stats.users_by_tier).map(([tier, count]) => (
            <div key={tier} className="text-center p-2 bg-zinc-50 rounded">
              <div className="text-lg font-semibold text-zinc-900">{count}</div>
              <div className="text-xs text-zinc-500 capitalize">{tier}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: number;
  highlight?: "warning" | "success";
}

function StatCard({ label, value, highlight }: StatCardProps) {
  const bgColor =
    highlight === "warning"
      ? "bg-amber-50 border-amber-200"
      : highlight === "success"
      ? "bg-green-50 border-green-200"
      : "bg-white border-zinc-200";

  return (
    <div className={`border rounded-lg p-4 ${bgColor}`}>
      <div className="text-2xl font-semibold text-zinc-900">{value}</div>
      <div className="text-sm text-zinc-500">{label}</div>
    </div>
  );
}
