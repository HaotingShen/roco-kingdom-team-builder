import { create } from "zustand";
import type { UserMonsterCreate } from "@/types";

// ─── Slot-level state (active tab, custom defender, attacker statuses) ─────────

type SlotAnalysisState = {
  activeTab: string;
  customDefender: UserMonsterCreate | null;
  attackerStatusIds: number[];
  // MoveCoveragePanel toggles
  effectiveMode: "single" | "dual";
  blindMode: "single" | "dual";
  // EffectiveStatsPanel damage calculator
  calcAtk: number;
  calcPower: number;
  // Leader form toggle (shared across all analysis tabs for this slot)
  showLeaderForm: boolean;
};

const DEFAULT_SLOT: SlotAnalysisState = {
  activeTab: "stats",
  customDefender: null,
  attackerStatusIds: [],
  effectiveMode: "single",
  blindMode: "single",
  calcAtk: 250,
  calcPower: 100,
  showLeaderForm: false,
};

// ─── Per-MatchupPanel state ───────────────────────────────────────────────────
// Key: `${pathname}:${defenderMonsterId}` — unique per attacker slot + defender.

export type MatchupPanelState = {
  isReversed: boolean;
  defDefenseId: string;
  atkDefenseId: string;
  featuredAtkStatusIds: number[];
  outgoingDebuffIds: number[];
  incomingDebuffIds: number[];
  defShowLeaderForm: boolean;
  /** Energy level for Mana Burst (0–10). Default 10. */
  magicEnergyLevel: number;
};

// ─── Store ────────────────────────────────────────────────────────────────────

type AnalysisStore = {
  slots: Record<number, SlotAnalysisState>;
  setActiveTab: (slotIdx: number, tab: string) => void;
  setCustomDefender: (slotIdx: number, slot: UserMonsterCreate | null) => void;
  setAttackerStatusIds: (slotIdx: number, ids: number[]) => void;
  patchSlot: (slotIdx: number, patch: Partial<SlotAnalysisState>) => void;

  matchupStates: Record<string, MatchupPanelState>;
  setMatchupState: (key: string, state: MatchupPanelState) => void;

  // Active featured-team sub-tab: keyed by pathname (encodes the attacker slot)
  featuredTeamTabs: Record<string, string>;
  setFeaturedTeamTab: (pathname: string, key: string) => void;

  // Active builder slot index — persisted across navigation within the session
  builderActiveSlot: number;
  setBuilderActiveSlot: (idx: number) => void;
};

export const useAnalysisStore = create<AnalysisStore>((set) => ({
  slots: {},
  setActiveTab: (slotIdx, tab) =>
    set((s) => ({
      slots: { ...s.slots, [slotIdx]: { ...(s.slots[slotIdx] ?? DEFAULT_SLOT), activeTab: tab } },
    })),
  setCustomDefender: (slotIdx, slot) =>
    set((s) => ({
      slots: { ...s.slots, [slotIdx]: { ...(s.slots[slotIdx] ?? DEFAULT_SLOT), customDefender: slot } },
    })),
  setAttackerStatusIds: (slotIdx, ids) =>
    set((s) => ({
      slots: { ...s.slots, [slotIdx]: { ...(s.slots[slotIdx] ?? DEFAULT_SLOT), attackerStatusIds: ids } },
    })),
  patchSlot: (slotIdx, patch) =>
    set((s) => ({
      slots: { ...s.slots, [slotIdx]: { ...(s.slots[slotIdx] ?? DEFAULT_SLOT), ...patch } },
    })),

  matchupStates: {},
  setMatchupState: (key, state) =>
    set((s) => ({ matchupStates: { ...s.matchupStates, [key]: state } })),

  featuredTeamTabs: {},
  setFeaturedTeamTab: (pathname, key) =>
    set((s) => ({ featuredTeamTabs: { ...s.featuredTeamTabs, [pathname]: key } })),

  builderActiveSlot: 0,
  setBuilderActiveSlot: (idx) => set({ builderActiveSlot: idx }),
}));
