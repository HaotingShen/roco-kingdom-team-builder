import { Link, useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { endpoints } from "@/lib/api";
import { useBuilderStore } from "../builder/builderStore";
import type { TeamOut } from "@/types";
import { pickName, pickFormName, useI18n, type Lang } from "@/i18n";
import { monsterImageFallbackChain, typeIconUrl, magicItemImageUrl } from "@/lib/images";
import { formatRowEffects } from "@/lib/personality";

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

/* --- Monster image component with fallback --- */
function MonsterImage({ monster, size = 180 }: { monster: any; size?: number }) {
  const [imgSrc, setImgSrc] = useState<string | null>(null);
  const fallbackChain = monsterImageFallbackChain(monster, size as 180 | 270 | 360);

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
    <img
      src={imgSrc || "/monsters/placeholder.png"}
      alt={monster?.name || "Monster"}
      className="w-full h-full object-contain"
      onError={handleError}
    />
  );
}

/* --- Type badge component --- */
function TypeBadge({ type, lang }: { type: any; lang: Lang }) {
  const iconUrl = typeIconUrl(type?.name);
  const typeName = pickName(type, lang);

  return (
    <div className="inline-flex items-center gap-1 px-2 py-1.5 bg-zinc-100 rounded text-xs font-medium">
      {iconUrl && (
        <img src={iconUrl} alt={typeName} className="w-3.5 h-3.5" onError={(e) => (e.currentTarget.style.display = 'none')} />
      )}
      <span>{typeName}</span>
    </div>
  );
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

  if (q.isLoading) return <div className="flex items-center justify-center h-64">{t("common.loading")}</div>;
  if (!q.data) return <div className="text-center text-zinc-500 h-64 flex items-center justify-center">{t("teams.notFound")}</div>;
  const team = q.data;
  const magicItemImg = magicItemImageUrl(team.magic_item);

  return (
    <div className="space-y-4">
      {/* Back button */}
      <div className="flex items-center">
        <Link
          to="/teams"
          className="inline-flex items-center gap-1 text-sm rounded border px-3 py-2 hover:bg-zinc-100 cursor-pointer"
          aria-label={t("teams.backToList") || "Back to Teams"}
        >
          <span aria-hidden className="text-lg leading-none">←</span>
          {t("teams.backToList") || "Back to Teams"}
        </Link>
      </div>

      {/* Team header with magic item */}
      <div className="rounded-lg border bg-white shadow-sm p-6">
        <h1 className="text-2xl font-bold mb-3">{team.name ?? `Team #${id}`}</h1>
        <div className="flex items-center gap-0.5 text-sm text-zinc-600">
          <span className="font-medium">{t("analysis.magicItem")}:</span>
          {magicItemImg && (
            <div className="w-8 h-8 rounded flex items-center justify-center">
              <img
                src={magicItemImg}
                alt={pickName(team.magic_item as any, lang)}
                className="w-full h-full object-contain"
                onError={(e) => (e.currentTarget.style.display = 'none')}
              />
            </div>
          )}
          <span className="font-bold">{pickName(team.magic_item as any, lang)}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
        {/* Monster cards */}
        <section className="space-y-4">
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {(team.user_monsters ?? []).map((um, idx) => (
              <div key={um.id} className="rounded-lg border bg-white shadow-sm overflow-hidden">
                {/* Monster image - reduced size */}
                <div className="relative bg-gradient-to-br from-zinc-50 to-zinc-100 p-4 flex items-center justify-center" style={{ minHeight: '160px' }}>
                  <div className="w-32 h-32">
                    <MonsterImage monster={um.monster} size={180} />
                  </div>
                  <div className="absolute top-2 left-2 bg-white/90 rounded-full w-8 h-8 flex items-center justify-center text-sm font-bold text-zinc-700 shadow">
                    {idx + 1}
                  </div>
                </div>

                {/* Monster info */}
                <div className="p-3 space-y-2.5">
                  <div>
                    <h3 className="font-bold text-lg mb-1.5">
                      {pickName(um.monster as any, lang)}
                      {pickFormName(um.monster as any, lang) && (
                        <span className="text-zinc-500 font-normal ml-1.5">({pickFormName(um.monster as any, lang)})</span>
                      )}
                    </h3>

                    {/* Types */}
                    <div className="flex flex-wrap gap-1 mb-1.5">
                      <TypeBadge type={um.monster.main_type} lang={lang} />
                      {um.monster.sub_type && (
                        <TypeBadge type={um.monster.sub_type} lang={lang} />
                      )}
                    </div>
                  </div>

                  {/* Personality and Legacy */}
                  <div className="grid grid-cols-2 gap-2 items-start">
                    <div>
                      <div className="text-zinc-500 mb-1 text-xs">{t("builder.personality")}:</div>
                      <div className="font-semibold text-zinc-800 text-xs">
                        {pickName(um.personality as any, lang)}
                        <span className="ml-1.5 text-zinc-600 font-semibold">
                          {formatRowEffects(um.personality, t)}
                        </span>
                      </div>
                    </div>
                    <div>
                      <div className="text-zinc-500 mb-1 text-xs">{t("labels.legacy")}:</div>
                      <div className="flex items-center gap-1 font-semibold text-zinc-800 text-xs">
                        {typeIconUrl(um.legacy_type?.name) && (
                          <img
                            src={typeIconUrl(um.legacy_type.name) || ""}
                            alt=""
                            className="w-3.5 h-3.5"
                            onError={(e) => (e.currentTarget.style.display = 'none')}
                          />
                        )}
                        <span>{pickName(um.legacy_type as any, lang)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Moves */}
                  <div>
                    <div className="text-xs text-zinc-500 mb-1.5 font-medium">{t("builder.moves")}:</div>
                    <div className="grid grid-cols-2 gap-1.5 text-xs">
                      {[um.move1, um.move2, um.move3, um.move4].map((move, i) => (
                        <div key={i} className="flex items-center gap-1 bg-zinc-50 px-2 py-1.5 rounded">
                          {typeIconUrl(move.move_type?.name || move.type?.name) && (
                            <img
                              src={typeIconUrl(move.move_type?.name || move.type?.name) || ""}
                              alt=""
                              className="w-3.5 h-3.5 flex-shrink-0"
                              onError={(e) => (e.currentTarget.style.display = 'none')}
                            />
                          )}
                          <span className="truncate text-zinc-700 font-medium">{pickName(move as any, lang)}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Talents */}
                  <div>
                    <div className="text-xs text-zinc-500 mb-1.5 font-medium">{t("builder.talents")}:</div>
                    <div className="grid grid-cols-3 gap-1.5">
                      <div className="bg-red-50 px-1.5 py-1 rounded text-center">
                        <div className="text-red-700 font-semibold text-xs">{t("labels.hp")}</div>
                        <div className="text-red-700 font-semibold text-sm">{um.talent.hp_boost}</div>
                      </div>
                      <div className="bg-stone-100 px-1.5 py-1 rounded text-center">
                        <div className="text-stone-700 font-semibold text-xs">{t("labels.phyAtk")}</div>
                        <div className="text-stone-700 font-semibold text-sm">{um.talent.phy_atk_boost}</div>
                      </div>
                      <div className="bg-purple-50 px-1.5 py-1 rounded text-center">
                        <div className="text-purple-700 font-semibold text-xs">{t("labels.magAtk")}</div>
                        <div className="text-purple-700 font-semibold text-sm">{um.talent.mag_atk_boost}</div>
                      </div>
                      <div className="bg-amber-50 px-1.5 py-1 rounded text-center">
                        <div className="text-amber-700 font-semibold text-xs">{t("labels.phyDef")}</div>
                        <div className="text-amber-700 font-semibold text-sm">{um.talent.phy_def_boost}</div>
                      </div>
                      <div className="bg-blue-50 px-1.5 py-1 rounded text-center">
                        <div className="text-blue-700 font-semibold text-xs">{t("labels.magDef")}</div>
                        <div className="text-blue-700 font-semibold text-sm">{um.talent.mag_def_boost}</div>
                      </div>
                      <div className="bg-green-50 px-1.5 py-1 rounded text-center">
                        <div className="text-green-700 font-semibold text-xs">{t("labels.spd")}</div>
                        <div className="text-green-700 font-semibold text-sm">{um.talent.spd_boost}</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Actions sidebar */}
        <aside className="rounded-lg border bg-white shadow-sm p-4 space-y-3 h-fit sticky top-4">
          <h2 className="font-bold text-lg mb-4">{t("teams.actions")}</h2>

          <button
            className="w-full h-10 border-2 border-zinc-300 rounded-lg hover:bg-zinc-50 cursor-pointer
                       disabled:opacity-60 disabled:cursor-not-allowed font-medium transition-colors"
            onClick={async () => {
              const fresh = await endpoints.getTeam(teamId).then(r => r.data);
              loadIntoBuilder(fresh);
              nav("/build");
            }}
          >
            {t("teams.editInBuilder")}
          </button>

          <button
            className="w-full h-10 border-2 border-zinc-300 rounded-lg hover:bg-zinc-50 cursor-pointer
                       disabled:opacity-60 disabled:cursor-not-allowed font-medium transition-colors"
            onClick={() => {
              const clone = { ...team, id: 0, name: (team.name || "Team") + " (Copy)" };
              loadIntoBuilder(clone as any);
              nav("/build");
            }}
          >
            {t("teams.editCopyInBuilder")}
          </button>

          <button
            className={`w-full h-10 rounded-lg cursor-pointer font-medium transition-colors
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

          <div className="pt-3 border-t">
            <button
              className="w-full h-10 border-2 border-red-300 rounded-lg text-red-600 hover:bg-red-50 cursor-pointer
                         disabled:opacity-60 disabled:cursor-not-allowed font-medium transition-colors"
              onClick={onDeleteClick}
              disabled={del.isPending}
            >
              {del.isPending ? t("teams.deleting") : t("teams.delete")}
            </button>
          </div>

          {serverErr && (
            <div className="rounded-lg border-2 border-red-300 bg-red-50 text-red-700 p-3 text-sm flex items-start justify-between">
              <div className="pr-2">{serverErr}</div>
              <button
                onClick={() => setServerErr(null)}
                className="text-red-700 hover:text-red-900 px-1 cursor-pointer font-bold"
                aria-label="Close"
                title="Close"
              >
                ×
              </button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}