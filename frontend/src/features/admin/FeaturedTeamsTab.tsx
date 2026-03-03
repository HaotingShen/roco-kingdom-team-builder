import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { endpoints, adminEndpoints } from "@/lib/api";
import { useBuilderStore } from "@/features/builder/builderStore";
import { useI18n } from "@/i18n";
import type { TeamOut } from "@/types";

export default function FeaturedTeamsTab() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const loadFromTeam = useBuilderStore(s => s.loadFromTeam);
  const setIsFeaturedTeam = useBuilderStore(s => s.setIsFeaturedTeam);

  const teamsQuery = useQuery({
    queryKey: ["admin", "featured-teams"],
    queryFn: () => endpoints.getFeaturedTeams().then(r => r.data as TeamOut[]),
    retry: false,
  });

  const deleteTeam = useMutation({
    mutationFn: (id: number) => adminEndpoints.deleteFeaturedTeam(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "featured-teams"] });
    },
  });

  const onEdit = (team: TeamOut) => {
    loadFromTeam(team);
    setIsFeaturedTeam(true);
    navigate("/build");
  };

  const onDelete = (team: TeamOut) => {
    if (!window.confirm(`Delete featured team "${team.name}"?`)) return;
    deleteTeam.mutate(team.id);
  };

  if (teamsQuery.isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin h-8 w-8 border-2 border-purple-600 border-t-transparent rounded-full" />
      </div>
    );
  }

  const teams: TeamOut[] = teamsQuery.data ?? [];

  if (!teams.length) {
    return (
      <div className="text-center py-12 text-zinc-500">
        <p className="text-base">{t("admin.featuredTeamsEmpty") || "No featured teams yet. Build a team in the builder and click \"Save as Featured\"."}</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-zinc-500">
        {t("admin.featuredTeamsEmpty")?.split(".")[1]?.trim() ||
          "To add a featured team, build it in the builder and click \"Save as Featured\"."}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-zinc-200 text-left text-zinc-500">
              <th className="py-2 pr-4 font-medium">Name</th>
              <th className="py-2 pr-4 font-medium">Monsters</th>
              <th className="py-2 pr-4 font-medium">Magic Item</th>
              <th className="py-2 pr-4 font-medium">Created</th>
              <th className="py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {teams.map(team => (
              <tr key={team.id} className="border-b border-zinc-100 hover:bg-zinc-50">
                <td className="py-3 pr-4 font-medium text-zinc-900">{team.name ?? "—"}</td>
                <td className="py-3 pr-4 text-zinc-600">
                  <div className="flex flex-wrap gap-1">
                    {team.user_monsters.map(um => (
                      <span key={um.id} className="bg-zinc-100 text-zinc-700 text-xs px-2 py-0.5 rounded">
                        {um.monster.name}
                      </span>
                    ))}
                  </div>
                </td>
                <td className="py-3 pr-4 text-zinc-600">{team.magic_item.name}</td>
                <td className="py-3 pr-4 text-zinc-500">
                  {team.created_at ? new Date(team.created_at).toLocaleDateString() : "—"}
                </td>
                <td className="py-3">
                  <div className="flex gap-2">
                    <button
                      onClick={() => onEdit(team)}
                      className="h-7 px-3 rounded text-xs border border-purple-300 text-purple-700 hover:bg-purple-50 cursor-pointer"
                    >
                      {t("admin.editFeaturedTeam") || "Edit"}
                    </button>
                    <button
                      onClick={() => onDelete(team)}
                      disabled={deleteTeam.isPending}
                      className="h-7 px-3 rounded text-xs border border-red-300 text-red-700 hover:bg-red-50 cursor-pointer disabled:opacity-50"
                    >
                      {t("admin.deleteFeaturedTeam") || "Delete"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
