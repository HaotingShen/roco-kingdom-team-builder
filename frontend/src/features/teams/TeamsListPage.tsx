import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { endpoints } from "@/lib/api";
import { formatLocal } from "@/lib/datetime";
import type { TeamOut } from "@/types";
import { useI18n, pickName } from "@/i18n";
import { useState, useEffect } from "react";
import { monsterImageFallbackChain, magicItemImageUrl } from "@/lib/images";

/** Component for displaying circular monster images with fallback */
function MonsterAvatar({ monster, size = 60 }: { monster: any; size?: number }) {
  const [imgSrc, setImgSrc] = useState<string | null>(null);
  const fallbackChain = monsterImageFallbackChain(monster, 180);

  useEffect(() => {
    setImgSrc(fallbackChain[0] || "/monsters/placeholder.png");
  }, [monster]);

  const handleError = () => {
    const currentIndex = fallbackChain.indexOf(imgSrc || "");
    if (currentIndex < fallbackChain.length - 1) {
      const nextSrc = fallbackChain[currentIndex + 1];
      if (nextSrc) {
        setImgSrc(nextSrc);
      }
    }
  };

  return (
    <div
      className="rounded-full overflow-hidden bg-zinc-100 border-2 border-white shadow-sm"
      style={{ width: size, height: size }}
    >
      <img
        src={imgSrc || "/monsters/placeholder.png"}
        alt={monster?.name || "Monster"}
        className="w-full h-full object-cover"
        onError={handleError}
      />
    </div>
  );
}

export default function TeamsListPage() {
  const { t, lang } = useI18n();
  const qc = useQueryClient();
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [renamingTeam, setRenamingTeam] = useState<TeamOut | null>(null);
  const [newTeamName, setNewTeamName] = useState("");

  const teams = useQuery<TeamOut[]>({
    queryKey: ["teams"],
    queryFn: () => endpoints.listTeams().then(r => r.data),
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    staleTime: 0,
  });

  const remove = useMutation({
    mutationFn: (id: number) => endpoints.deleteTeam(id).then(r => r.data),
    onMutate: async (id: number) => {
      await qc.cancelQueries({ queryKey: ["teams"] });
      const prev = qc.getQueryData<TeamOut[]>(["teams"]);
      qc.setQueryData<TeamOut[]>(["teams"], (old) =>
        (old ?? []).filter(t => t.id !== id)
      );
      return { prev };
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.prev) qc.setQueryData(["teams"], ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["teams"] });
    },
  });

  const rename = useMutation({
    mutationFn: ({ id, name, team }: { id: number; name: string; team: TeamOut }) => {
      // Transform TeamOut to TeamUpdate format
      const updatePayload = {
        name,
        magic_item_id: team.magic_item.id,
        user_monsters: team.user_monsters.map((um: any, index: number) => ({
          id: um.id,
          monster_id: um.monster.id,
          personality_id: um.personality.id,
          legacy_type_id: um.legacy_type.id,
          move1_id: um.move1.id,
          move2_id: um.move2.id,
          move3_id: um.move3.id,
          move4_id: um.move4.id,
          talent: {
            hp_boost: um.talent.hp_boost,
            phy_atk_boost: um.talent.phy_atk_boost,
            mag_atk_boost: um.talent.mag_atk_boost,
            phy_def_boost: um.talent.phy_def_boost,
            mag_def_boost: um.talent.mag_def_boost,
            spd_boost: um.talent.spd_boost,
          },
          position: um.position ?? index,
        })),
      };
      return endpoints.updateTeam(id, updatePayload).then((r: any) => r.data);
    },
    onMutate: async ({ id, name }) => {
      await qc.cancelQueries({ queryKey: ["teams"] });
      const prev = qc.getQueryData<TeamOut[]>(["teams"]);
      qc.setQueryData<TeamOut[]>(["teams"], (old) =>
        (old ?? []).map(t => t.id === id ? { ...t, name } : t)
      );
      return { prev };
    },
    onSuccess: () => {
      setRenameModalOpen(false);
      setRenamingTeam(null);
      setNewTeamName("");
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(["teams"], ctx.prev);
      alert(t("teams.renameFailed"));
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["teams"] });
    },
  });

  const onDeleteClick = (id: number) => {
    if (remove.isPending) return;
    const ok = window.confirm(
      t("teams.confirmDelete") ?? "Delete this team? This cannot be undone."
    );
    if (!ok) return;
    remove.mutate(id);
  };

  const onRenameClick = (team: TeamOut) => {
    setRenamingTeam(team);
    setNewTeamName(team.name || `Team #${team.id}`);
    setRenameModalOpen(true);
  };

  const onRenameSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!renamingTeam || rename.isPending) return;
    if (!newTeamName.trim()) {
      alert(t("builder.teamNamePlaceholder"));
      return;
    }
    rename.mutate({
      id: renamingTeam.id,
      name: newTeamName.trim(),
      team: renamingTeam,
    });
  };

  const onRenameCancel = () => {
    setRenameModalOpen(false);
    setRenamingTeam(null);
    setNewTeamName("");
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-medium text-lg">{t("teams.manageTeams")}</h2>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {(teams.data ?? []).map((team) => (
          <div key={team.id} className="rounded-lg border bg-white shadow-sm hover:shadow-md transition-shadow overflow-hidden">
            <Link to={`/teams/${team.id}`} className="block">
              {/* Header with team name and date */}
              <div className="p-4 border-b bg-gradient-to-r from-zinc-50 to-white">
                <div className="font-semibold text-lg mb-1">
                  {team.name || `Team #${team.id}`}
                </div>
                <div className="text-xs text-zinc-500">
                  {t("teams.lastModified")}: {formatLocal(team.updated_at, lang === "zh" ? "zh-CN" : "en-US")}
                </div>
              </div>

              {/* Monster avatars in a 2x3 grid */}
              <div className="p-4 bg-gradient-to-b from-zinc-50/50 to-white">
                <div className="grid grid-cols-3 gap-3 mb-3">
                  {(team.user_monsters ?? []).slice(0, 6).map((um) => (
                    <div key={um.id} className="flex flex-col items-center">
                      <MonsterAvatar monster={um.monster} size={70} />
                      <div className="text-xs text-center mt-1 text-zinc-700 font-medium truncate w-full">
                        {pickName(um.monster as any, lang)}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Magic item info */}
                <div className="flex items-center gap-0.5 border-t pt-2">
                  <span className="text-xs font-medium text-zinc-600">{t("analysis.magicItem")}:</span>
                  {magicItemImageUrl(team.magic_item) && (
                    <div className="w-8 h-8 rounded p-0.5 flex items-center justify-center">
                      <img
                        src={magicItemImageUrl(team.magic_item) || ""}
                        alt={pickName(team.magic_item as any, lang)}
                        className="w-full h-full object-contain"
                        onError={(e) => (e.currentTarget.style.display = 'none')}
                      />
                    </div>
                  )}
                </div>
              </div>
            </Link>

            {/* Action buttons */}
            <div className="p-3 border-t bg-zinc-50 flex items-center gap-2">
              <Link
                to={`/teams/${team.id}`}
                className="flex-1 inline-flex items-center justify-center h-8 px-2 border rounded text-sm
                          text-zinc-700 bg-white hover:bg-zinc-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400"
              >
                {t("teams.open")}
              </Link>

              <button
                type="button"
                onClick={() => onRenameClick(team)}
                disabled={rename.isPending}
                className="flex-1 inline-flex items-center justify-center h-8 px-2 border rounded text-sm
                          text-zinc-700 bg-white hover:bg-zinc-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 cursor-pointer"
              >
                {t("teams.rename")}
              </button>

              <button
                type="button"
                onClick={() => onDeleteClick(team.id)}
                disabled={remove.isPending}
                className="flex-1 inline-flex items-center justify-center h-8 px-2 border rounded text-sm
                          text-red-600 bg-white hover:bg-red-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400 cursor-pointer"
              >
                {t("teams.delete")}
              </button>
            </div>
          </div>
        ))}
        {!teams.data?.length && (
          <div className="text-zinc-500">{t("teams.noTeams")}</div>
        )}
      </div>

      {/* Rename Modal */}
      {renameModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onRenameCancel}>
          <div className="bg-white rounded-lg shadow-lg p-6 w-full max-w-md m-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-medium mb-4">{t("teams.renameTeam")}</h3>
            <form onSubmit={onRenameSubmit}>
              <div className="mb-4">
                <label className="block text-sm font-medium text-zinc-700 mb-2">
                  {t("teams.newTeamName")}
                </label>
                <input
                  type="text"
                  value={newTeamName}
                  onChange={(e) => setNewTeamName(e.target.value)}
                  className="w-full px-3 py-2 border border-zinc-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder={t("builder.teamNamePlaceholder")}
                  autoFocus
                />
              </div>
              <div className="flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={onRenameCancel}
                  disabled={rename.isPending}
                  className="px-4 py-2 border rounded text-sm text-zinc-700 hover:bg-zinc-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400"
                >
                  {t("teams.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={rename.isPending}
                  className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 disabled:opacity-50"
                >
                  {rename.isPending ? t("teams.renaming") : t("teams.save")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}