import { create } from "zustand";
import type { ID, UserMonsterCreate, TeamCreate, TalentUpsert, TeamAnalysisOut, TeamOut, UserMonsterUpsert, TeamUpdate } from "@/types";

const emptyTalent: TalentUpsert = { hp_boost:0, phy_atk_boost:0, mag_atk_boost:0, phy_def_boost:0, mag_def_boost:0, spd_boost:0 };
function emptySlot(): UserMonsterCreate & { id?: ID } {
  return {
    id: undefined,
    monster_id: 0,
    personality_id: 0,
    legacy_type_id: 0,
    move1_id: 0, move2_id: 0, move3_id: 0, move4_id: 0,
    talent: { ...emptyTalent },
  };
}

type PartialNoUndef<T> = { [K in keyof T]?: Exclude<T[K], undefined> };
function mergeWithoutUndef<T extends object>(base: T, patch: PartialNoUndef<T>): T {
  const next: any = { ...base }; for (const k in patch) { const v = (patch as any)[k]; if (v !== undefined) next[k] = v; } return next as T;
}

type BuilderState = {
  teamId: ID | null;
  name: string;
  magic_item_id: ID | null;
  slots: (UserMonsterCreate & { id?: ID })[]; // length 6

  setName: (v: string) => void;
  setMagicItem: (id: ID | null) => void;
  setSlot: (idx: number, patch: PartialNoUndef<UserMonsterCreate & { id?: ID }>) => void;

  toPayload: () => TeamCreate;                    // throws if magic_item_id null
  toUpdatePayload: () => TeamUpdate | null;       // when teamId is known

  loadFromTeam: (team: TeamOut) => void;          // pull saved team into builder
  clearTeamId: () => void;

  analysis: TeamAnalysisOut | null;
  setAnalysis: (a: TeamAnalysisOut | null) => void;

  isAnalyzing: boolean;
  setIsAnalyzing: (v: boolean) => void;

  reset: () => void;
};

export const useBuilderStore = create<BuilderState>((set, get) => ({
  teamId: null,
  name: "",
  magic_item_id: null,
  slots: Array.from({ length: 6 }, emptySlot),

  setName: (name) => set({ name }),
  setMagicItem: (magic_item_id) => set({ magic_item_id }),
  setSlot: (idx, patch) => set((s) => {
    const slots = s.slots.slice();
    const current = slots[idx] ?? emptySlot();
    slots[idx] = mergeWithoutUndef<typeof current>(current, patch);
    return { slots };
  }),

  toPayload: () => {
    const s = get();
    if (!s.magic_item_id) throw new Error("Pick a magic item before saving.");
    return {
      name: s.name,
      magic_item_id: s.magic_item_id,
      user_monsters: s.slots.map(({ id: _omit, ...um }, index) => ({ ...um, position: index })),
    };
  },

  toUpdatePayload: () => {
    const s = get();
    if (!s.teamId) return null;
    return {
      name: s.name,
      magic_item_id: s.magic_item_id,
      user_monsters: s.slots.map((um, index) => ({
        id: um.id,
        monster_id: um.monster_id,
        personality_id: um.personality_id,
        legacy_type_id: um.legacy_type_id,
        move1_id: um.move1_id, move2_id: um.move2_id, move3_id: um.move3_id, move4_id: um.move4_id,
        talent: { ...um.talent },
        position: index,
      })),
    };
  },

  loadFromTeam: (team) => set(() => {
    const slots: (UserMonsterCreate & { id?: ID })[] = (team.user_monsters ?? []).slice(0, 6).map((um): (UserMonsterCreate & { id?: ID }) => ({
      id: um.id,
      monster_id: um.monster.id,
      personality_id: um.personality.id,
      legacy_type_id: um.legacy_type.id,
      move1_id: um.move1.id, move2_id: um.move2.id, move3_id: um.move3.id, move4_id: um.move4.id,
      talent: {
        hp_boost: um.talent.hp_boost, phy_atk_boost: um.talent.phy_atk_boost, mag_atk_boost: um.talent.mag_atk_boost,
        phy_def_boost: um.talent.phy_def_boost, mag_def_boost: um.talent.mag_def_boost, spd_boost: um.talent.spd_boost,
      }
    }));
    while (slots.length < 6) slots.push(emptySlot());
    return { teamId: team.id, name: team.name ?? "My Team", magic_item_id: team.magic_item?.id ?? null, slots };
  }),

  clearTeamId: () => set({ teamId: null }),

  analysis: null,
  setAnalysis: (a) => set({ analysis: a }),

  isAnalyzing: false,
  setIsAnalyzing: (v) => set({ isAnalyzing: v }),

  reset: () => set({
    teamId: null,
    name: "",
    magic_item_id: null,
    slots: Array.from({ length: 6 }, emptySlot),
    analysis: null,
    isAnalyzing: false,
  }),
}));