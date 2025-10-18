import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import { useBuilderStore } from "./builderStore";
import MonsterCard from "@/components/MonsterCard";
import CustomSelect from "@/components/CustomSelect";
import AnalysisResults from "@/components/AnalysisResults";
import type { MagicItemOut, UserMonsterCreate, TeamCreate, TeamAnalysisOut, TeamOut, TeamUpdate } from "@/types";
import { useMemo, useState } from "react";
import MonsterInspector from "./MonsterInspector";
import { useI18n, pickName } from "@/i18n";

/* --- magic item icon --- */
function encode(s?: string | null) {
  return s ? encodeURIComponent(String(s).trim()) : "";
}
function magicItemIconUrl(mi?: MagicItemOut | null): string | null {
  if (!mi) return null;
  const zh = (mi as any)?.localized?.zh;
  const cnName = zh && typeof zh.name === "string" ? zh.name : null;
  if (cnName) return `/magic-items/${encode(cnName)}.png`;
  if (mi.name) return `/magic-items/${encode(mi.name)}.png`;
  return null;
}

type VKey =
  | "v_pickMonster"
  | "v_setPersonality"
  | "v_chooseLegacy"
  | "v_select4Moves"
  | "v_pickTalent"
  | "v_max3";

function boostedCount(t: UserMonsterCreate["talent"]) {
  const vals = [
    t.hp_boost,
    t.phy_atk_boost,
    t.mag_atk_boost,
    t.phy_def_boost,
    t.mag_def_boost,
    t.spd_boost,
  ];
  return vals.filter((v) => (v ?? 0) > 0).length;
}

function validateSlot(slot: UserMonsterCreate): VKey[] {
  const errs: VKey[] = [];
  if (!slot.monster_id) errs.push("v_pickMonster");
  if (!slot.personality_id) errs.push("v_setPersonality");
  if (!slot.legacy_type_id) errs.push("v_chooseLegacy");
  const moves = [slot.move1_id, slot.move2_id, slot.move3_id, slot.move4_id];
  if (moves.some((m) => !m)) errs.push("v_select4Moves");
  const b = boostedCount(slot.talent || ({} as any));
  if (b === 0) errs.push("v_pickTalent");
  if (b > 3) errs.push("v_max3");
  return errs;
}

function extractAxiosMessage(e: any): string {
  const d = e?.response?.data;
  if (d?.detail) return typeof d.detail === "string" ? d.detail : JSON.stringify(d.detail);
  return e?.message ?? "Request failed";
}

// quick helper for clearing a single slot
const zeroTalent = { hp_boost:0, phy_atk_boost:0, mag_atk_boost:0, phy_def_boost:0, mag_def_boost:0, spd_boost:0 } as const;

export default function BuilderPage() {
  const {
    teamId,
    name,
    setName,
    slots,
    setSlot,
    magic_item_id,
    setMagicItem,
    toPayload,
    toUpdatePayload,
    analysis,
    setAnalysis,
  } = useBuilderStore();

  const [activeIdx, setActiveIdx] = useState<number>(0);
  const [serverErr, setServerErr] = useState<string | null>(null);
  const [serverOk, setServerOk] = useState<string | null>(null);
  const { lang, t } = useI18n();

  const magicItems = useQuery<MagicItemOut[]>({
    queryKey: ["magic_items"],
    queryFn: () => endpoints.magicItems().then((r) => r.data as MagicItemOut[]),
  });
  const qc = useQueryClient();

  const allErrors = useMemo<VKey[][]>(() => slots.map(validateSlot), [slots]);
  const canAnalyze = allErrors.every((list) => list.length === 0) && !!magic_item_id;

  /* ---------- analyze ---------- */
  const analyze = useMutation({
    mutationFn: (payload: TeamCreate) =>
      endpoints.analyzeTeam(payload).then((r) => r.data as TeamAnalysisOut),
    onError: (err) => setServerErr(extractAxiosMessage(err)),
    onSuccess: (data) => {
      setServerErr(null);
      setAnalysis(data);
    },
  });

  const onAnalyze = () => {
    if (!magic_item_id) {
      setServerErr(t("builder.v_pickMagicItem"));
      return;
    }
    if (!canAnalyze) {
      setServerErr(t("builder.incompleteTeamMsg"));
      return;
    }
    try {
      analyze.mutate(toPayload());
    } catch (e: any) {
      setServerErr(e?.message || t("builder.incompleteTeamMsg"));
    }
  };

  /* ---------- save (create new) / update (modify existing) ---------- */
  const createTeam = useMutation({
    mutationFn: (payload: TeamCreate) =>
      endpoints.createTeam(payload).then((r) => r.data as TeamOut),
    onError: (err) => {
      setServerOk(null);
      setServerErr(extractAxiosMessage(err));
    },
    onSuccess: (team) => {
      setServerErr(null);
      setServerOk(t("builder.savedMsg"));           // persistent until closed
      useBuilderStore.setState({ teamId: team.id }); // keep id for future updates
      qc.invalidateQueries({ queryKey: ["teams"] });
      qc.invalidateQueries({ queryKey: ["team", team.id] });
    },
  });

  const updateTeam = useMutation({
    mutationFn: ({ id, body }: { id: number; body: TeamUpdate }) =>
      endpoints.updateTeam(id, body).then((r) => r.data as TeamOut),
    onError: (err) => {
      setServerOk(null);
      setServerErr(extractAxiosMessage(err));
    },
    onSuccess: (_updatedTeam, variables) => {
      setServerErr(null);
      setServerOk(t("builder.updatedMsg"));         // persistent until closed
      qc.invalidateQueries({ queryKey: ["teams"] });
      qc.invalidateQueries({ queryKey: ["team", variables.id] });
    },
  });

  const onSaveNew = () => {
    if (!magic_item_id || !canAnalyze) {
      setServerErr(t("builder.incompleteTeamMsg"));
      return;
    }
    try {
      createTeam.mutate(toPayload());
    } catch (e: any) {
      setServerErr(e?.message || t("builder.incompleteTeamMsg"));
    }
  };

  const onUpdateExisting = () => {
    if (!teamId) return; // hidden if no teamId anyway
    if (!magic_item_id || !canAnalyze) {
      setServerErr(t("builder.incompleteTeamMsg"));
      return;
    }
    try {
      const body = toUpdatePayload();
      if (!body) {
        setServerErr(t("builder.incompleteTeamMsg"));
        return;
      }
      updateTeam.mutate({ id: teamId, body });
    } catch (e: any) {
      setServerErr(e?.message || t("builder.incompleteTeamMsg"));
    }
  };

  return (
    <div className="grid gap-4 grid-cols-1 lg:grid-cols-[1fr_380px] xl:grid-cols-[1fr_420px]">
      <section className="space-y-3">
        {/* grid */}
        <div className="grid grid-cols-3 gap-3">
          {slots.map((slot, i) => {
            const errs = allErrors?.[i] ?? [];
            const hasMonster = !!slot.monster_id;
            const isComplete = hasMonster && errs.length === 0;

            const statusKey = !hasMonster
              ? "status_empty"
              : isComplete
              ? "status_complete"
              : "status_incomplete";
            const statusText = t(`builder.${statusKey}`);

            const dotClass = !hasMonster
              ? "bg-zinc-300"
              : isComplete
              ? "bg-emerald-500"
              : "bg-amber-500";

            const chipClass = !hasMonster
              ? "border-zinc-300 bg-zinc-50 text-zinc-600"
              : isComplete
              ? "border-emerald-300 bg-emerald-50 text-emerald-700"
              : "border-amber-300 bg-amber-50 text-amber-700";

            return (
              <div
                key={i}
                className={`rounded border ${i === activeIdx ? "border-zinc-900" : "border-zinc-200"} bg-white p-3 space-y-2 cursor-pointer`}
                onClick={() => setActiveIdx(i)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setActiveIdx(i)}
              >
                <div className="flex items-center justify-between">
                  <div className="text-sm text-zinc-600">{t("builder.slot", { n: i + 1 })}</div>
                  <span
                    className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] ${chipClass}`}
                    title={statusText}
                    aria-label={statusText}
                  >
                    <span className={`h-2.5 w-2.5 rounded-full ${dotClass}`} />
                    <span className="hidden sm:inline">{statusText}</span>
                  </span>
                </div>

                <MonsterCard
                  monsterId={slot.monster_id || undefined}
                  personalityId={slot.personality_id || null}
                  legacyTypeId={slot.legacy_type_id || null}
                  moveIds={[slot.move1_id, slot.move2_id, slot.move3_id, slot.move4_id]}
                  talent={slot.talent}
                  onClick={() => setActiveIdx(i)}
                  // quick delete only when a monster is present
                  onDelete={
                    hasMonster
                      ? () => {
                          setSlot(i, {
                            monster_id: 0,
                            personality_id: 0,
                            legacy_type_id: 0,
                            move1_id: 0,
                            move2_id: 0,
                            move3_id: 0,
                            move4_id: 0,
                            talent: { ...zeroTalent },
                          });
                        }
                      : undefined
                  }
                />

                {errs.length > 0 && (
                  <ul className="text-[11px] text-red-600 list-disc pl-4">
                    {errs.map((k, j) => (
                      <li key={`${i}-${j}`}>{t(`builder.${k}`)}</li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>

        {/* bottom bar */}
        <div className="flex flex-wrap items-center gap-3 bg-white border rounded p-3">
          {/* team name */}
          <div className="flex items-center gap-2">
            <label className="text-sm">{t("builder.teamName") ?? "Team name"}</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("builder.teamNamePlaceholder") ?? "My Team"}
              className="h-9 rounded border px-2 text-sm w-[220px]"
            />
          </div>

          {/* magic item */}
          <div className="flex items-center gap-2">
            <div className="text-sm">{t("builder.magicItem")}</div>
            <CustomSelect
              value={magic_item_id ?? null}
              options={[
                { value: 0, label: t("common.select"), leftIconUrl: null },
                ...(magicItems.data ?? []).map((mi) => ({
                  value: mi.id,
                  label: pickName(mi as any, lang) || mi.name,
                  leftIconUrl: magicItemIconUrl(mi),
                })),
              ]}
              placeholder={t("common.select")}
              onChange={(v) => setMagicItem(v ? v : null)}
              buttonClassName="min-w-[150px]"
            />
          </div>

          <div className="flex-1" />

          {/* split buttons */}
          <button
            onClick={onSaveNew}
            disabled={!canAnalyze || createTeam.isPending}
            className={`h-9 px-4 rounded ${canAnalyze ? "border cursor-pointer" : "bg-zinc-300 text-zinc-600 cursor-not-allowed"}`}
            title={!canAnalyze ? t("builder.incompleteTeamMsg") : ""}
          >
            {createTeam.isPending ? t("builder.saving") : (t("builder.saveTeam") ?? "Save")}
          </button>

          {teamId ? (
            <button
              onClick={onUpdateExisting}
              disabled={!canAnalyze || updateTeam.isPending}
              className={`h-9 px-4 rounded ${canAnalyze ? "border cursor-pointer" : "bg-zinc-300 text-zinc-600 cursor-not-allowed"}`}
              title={!canAnalyze ? t("builder.incompleteTeamMsg") : ""}
            >
              {updateTeam.isPending ? t("builder.updating") : (t("builder.updateTeam") ?? "Update")}
            </button>
          ) : null}

          {/* analyze */}
          <button
            onClick={onAnalyze}
            disabled={!canAnalyze || analyze.isPending}
            className={`h-9 px-4 rounded ${
              canAnalyze ? "bg-zinc-900 text-white cursor-pointer" : "bg-zinc-300 text-zinc-600 cursor-not-allowed"
            }`}
          >
            {analyze.isPending ? t("builder.analyzing") : t("builder.analyze")}
          </button>
        </div>

        {/* closable messages */}
        {serverErr && (
          <div className="rounded border border-red-300 bg-red-50 text-red-700 p-3 text-sm flex items-start justify-between">
            <div className="pr-4">{serverErr}</div>
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
        {serverOk && (
          <div className="rounded border border-emerald-300 bg-emerald-50 text-emerald-700 p-3 text-sm flex items-start justify-between">
            <div className="pr-4">{serverOk}</div>
            <button
              onClick={() => setServerOk(null)}
              className="text-emerald-700 hover:text-emerald-900 px-1 cursor-pointer"
              aria-label="Close"
              title="Close"
            >
              x
            </button>
          </div>
        )}

        {analysis ? <AnalysisResults analysis={analysis} /> : null}
      </section>

      <MonsterInspector activeIdx={activeIdx} />
    </div>
  );
}