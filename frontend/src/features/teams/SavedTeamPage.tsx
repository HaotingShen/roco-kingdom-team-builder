import { Link, useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { endpoints } from "@/lib/api";
import { useBuilderStore } from "../builder/builderStore";
import type { TeamOut } from "@/types";
import { pickName, useI18n } from "@/i18n";

/* --- Animated dots component --- */
function AnimatedDots() {
  const [dots, setDots] = useState(".");

  useEffect(() => {
    const interval = setInterval(() => {
      setDots(prev => {
        if (prev === "...") return ".";
        return prev + ".";
      });
    }, 400);

    return () => clearInterval(interval);
  }, []);

  return <span className="inline-block w-3 text-left">{dots}</span>;
}

export default function SavedTeamPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const { lang, t } = useI18n();
  const loadIntoBuilder = useBuilderStore(s => s.loadFromTeam);
  const setAnalysis = useBuilderStore(s => s.setAnalysis);
  const isAnalyzing = useBuilderStore(s => s.isAnalyzing);
  const setIsAnalyzing = useBuilderStore(s => s.setIsAnalyzing);
  const qc = useQueryClient();

  const teamId = Number(id);
  const q = useQuery<TeamOut>({
    queryKey: ["team", teamId],
    queryFn: () => endpoints.getTeam(teamId).then(r => r.data),
    enabled: Number.isFinite(teamId),
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: false,
  });

  const del = useMutation({
    mutationFn: () => endpoints.deleteTeam(teamId).then(r => r.data),
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: ["teams"] });
      const prev = qc.getQueryData<TeamOut[]>(["teams"]);
      qc.setQueryData<TeamOut[]>(["teams"], (old) =>
        (old ?? []).filter(t => t.id !== teamId)
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["teams"], ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["teams"] });
      qc.removeQueries({ queryKey: ["team", teamId] });
    },
    onSuccess: () => nav("/teams"),
  });

  const onDeleteClick = () => {
    if (del.isPending) return;
    const ok = window.confirm(
      t("teams.confirmDelete") ?? "Delete this team? This cannot be undone."
    );
    if (!ok) return;
    del.mutate();
  };

  const [serverErr, setServerErr] = useState<string | null>(null);

  const analyze = useMutation({
    mutationFn: () => endpoints.analyzeTeamById({ team_id: teamId, language: lang }).then(r => r.data),
    onMutate: () => {
      setIsAnalyzing(true);
    },
    onError: (err: any) => {
      setServerErr(err?.response?.data?.detail || err?.message || t("builder.analysisFailed"));
      setIsAnalyzing(false);
    },
    onSuccess: (res) => {
      setServerErr(null);
      setAnalysis(res);
      setIsAnalyzing(false);
      nav("/build");
    },
    onSettled: () => {
      setIsAnalyzing(false);
    },
  });

  const onAnalyze = () => {
    if (isAnalyzing) {
      setServerErr(t("builder.analysisInProgress"));
      return;
    }
    setServerErr(null);
    analyze.mutate();
  };

  if (q.isLoading) return <div>{t("common.loading")}</div>;
  if (!q.data) return <div>{t("teams.notFound")}</div>;
  const team = q.data;

  return (
    <div className="space-y-3">
      <div className="flex items-center">
        <Link
          to="/teams"
          className="inline-flex items-center gap-1 text-sm rounded border px-2 py-1 hover:bg-zinc-100 cursor-pointer"
          aria-label={t("teams.backToList") || "Back to Teams"}
        >
          <span aria-hidden className="text-lg leading-none">←</span>
          {t("teams.backToList") || "Back to Teams"}
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_300px] gap-4">
        <section className="rounded border bg-white p-3">
          <div className="font-medium mb-2">{team.name ?? `Team #${id}`}</div>

          <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-3">
            {(team.user_monsters ?? []).map((um) => (
              <div key={um.id} className="rounded border p-3 space-y-1">
                <div className="text-sm font-medium">{pickName(um.monster as any, lang)}</div>
                <div className="text-xs text-zinc-600">
                  {t("builder.personality")}: {pickName(um.personality as any, lang)} · {t("labels.legacy")}: {pickName(um.legacy_type as any, lang)}
                </div>
                <div className="text-xs text-zinc-600">
                  {t("builder.moves")}: {[um.move1, um.move2, um.move3, um.move4].map(m => pickName(m as any, lang)).join(", ")}
                </div>
              </div>
            ))}
          </div>
        </section>

        <aside className="rounded border bg-white p-3 space-y-2">
          <div className="font-medium">{t("teams.actions")}</div>

          <button
            className="w-full h-9 border rounded hover:bg-zinc-50 cursor-pointer
                       disabled:opacity-60 disabled:cursor-not-allowed"
            onClick={async () => {
              const fresh = await endpoints.getTeam(teamId).then(r => r.data);
              loadIntoBuilder(fresh);
              nav("/build");
            }}
          >
            {t("teams.editInBuilder")}
          </button>

          <button
            className="w-full h-9 border rounded hover:bg-zinc-50 cursor-pointer
                       disabled:opacity-60 disabled:cursor-not-allowed"
            onClick={() => {
              const clone = { ...team, id: 0, name: (team.name || "Team") + " (Copy)" };
              loadIntoBuilder(clone as any);
              nav("/build");
            }}
          >
            {t("teams.editCopyInBuilder")}
          </button>

          <button
            className={`w-full h-9 rounded cursor-pointer
                       ${analyze.isPending || isAnalyzing ? "bg-zinc-300 text-zinc-600 cursor-not-allowed" : "bg-zinc-900 text-white hover:bg-zinc-800"}`}
            onClick={onAnalyze}
            disabled={analyze.isPending || isAnalyzing}
          >
            {analyze.isPending || isAnalyzing ? (
              <span className="inline-flex items-center justify-center">
                {t("teams.analyzing").replace("…", "").replace("...", "")}
                <AnimatedDots />
              </span>
            ) : (
              t("teams.analyze")
            )}
          </button>

          <button
            className="w-full h-9 border rounded text-red-600 hover:bg-red-100 cursor-pointer
                       disabled:opacity-60 disabled:cursor-not-allowed"
            onClick={onDeleteClick}
            disabled={del.isPending}
          >
            {del.isPending ? t("teams.deleting") : t("teams.delete")}
          </button>

          {serverErr && (
            <div className="rounded border border-red-300 bg-red-50 text-red-700 p-2 text-xs flex items-start justify-between">
              <div className="pr-2">{serverErr}</div>
              <button
                onClick={() => setServerErr(null)}
                className="text-red-700 hover:text-red-900 px-1 cursor-pointer"
                aria-label="Close"
                title="Close"
              >
                x
              </button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}