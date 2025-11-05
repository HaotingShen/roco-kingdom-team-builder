import React, { createContext, useContext, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { endpoints } from "@/lib/api";
import type { TypeOut } from "@/types";

export type Lang = "en" | "zh";

/* ---------------- data localization ---------------- */

export function pickName(x: any, lang: Lang): string {
  if (!x) return "";
  if (lang === "zh" && x.localized?.zh != null) {
    const zh = x.localized.zh;
    if (typeof zh === "string") return zh;
    if (typeof zh === "object") {
      if (typeof zh.name === "string") return zh.name;
      if (typeof zh.title === "string") return zh.title;
    }
  }
  return x.name ?? x.key ?? "";
}

export function pickDesc(x: any, lang: Lang): string {
  if (!x) return "";
  if (lang === "zh" && x.localized?.zh != null) {
    const zh = x.localized.zh;
    if (typeof zh === "string") return zh;
    if (typeof zh === "object" && typeof zh.description === "string")
      return zh.description;
  }
  return x.description ?? "";
}

export function useTypeIndex() {
  const q = useQuery({
    queryKey: ["types-index"],
    queryFn: () => endpoints.types().then((r) => r.data as TypeOut[]),
  });
  const index = useMemo(() => {
    const m: Record<string, string> = {};
    (q.data ?? []).forEach((t) => {
      m[t.name] = pickName(t, "zh");
    });
    return m;
  }, [q.data]);
  return { index, isLoading: q.isLoading };
}

export function localizeTypeName(name: string | undefined, lang: Lang, index: Record<string, string>): string {
  if (!name) return "";
  return lang === "zh" ? index[name] ?? name : name;
}

export function pickFormName(x: any, lang: Lang): string {
  const form: string = x?.form ?? "";
  if (!form || form.toLowerCase() === "default") return "";
  if (lang === "zh") {
    const zh = x?.localized?.zh;
    if (zh && typeof zh === "object" && typeof zh.form === "string" && zh.form.trim()) {
      return zh.form;
    }
  }
  return form;
}

/* ---------------- UI localization ---------------- */

type Dict = Record<string, Record<string, string>>;

const ui: Record<Lang, Dict> = {
  en: {
    common: {
      select: "Select…",
      loading: "Loading…",
      edit: "Edit",
      search: "Search…",
      showMore: "Show more",
      showLess: "Show less",
    },
    sidebar: {
      siteName: "Roco Team Builder™",
      build: "Build",
      dex: "Dex",
      teams: "Saved Teams",
    },
    topbar: {
      builder: "Team Builder",
      dex: "Dex",
      teams: "Saved Teams",
      toggleLanguage: "Toggle Language",
      lang_en_zh: "EN / 中文",
      lang_zh_en: "中文 / EN",
      search: "Search anything…",
      reset: "Reset",
      confirmReset: "Reset the builder? This clears the current team and analysis.",
      quickBuild: "Quick Build",
      quickBuilding: "Loading…",
      quickBuildConfirm: "This will auto-generate a new team and replace your current team. Continue?",
      quickBuildFailed: "Failed to load a sample team.",
    },
    builder: {
      slot: "Slot {{n}}",
      inspectorTitle: "Inspector — Slot {{n}}",
      changeMonster: "Change Monster",
      viewInDex: "View in Dex",
      deleteMonster: "Delete",
      pickAMonster: "Pick a monster",
      tipAfterPick:
        "Tip: After choosing a monster, you can set Personality, Legacy Type, Moves, and Talents.",
      personality: "Personality",
      effects: "Effects: {{text}}",
      legacyType: "Legacy Type",
      legacyGrants:
        "Legacy Type grants: {{name}}. You can use it in one move slot.",
      legacyMissing: "No legacy move found for this Legacy Type.",
      legacyHint:
        "You can pick at most 1 Legacy Move.",
      moves: "Moves",
      moveN: "Move {{n}}",
      talents: "Talents",
      talentsHint: "At most 3 stats can be boosted.",
      magicItem: "Magic Item:",
      analyze: "Analyze",
      analyzing: "Analyzing…",
      selectMonster: "Select monster…",
      searchMonsters: "Search monsters…",
      teamName: "Team Name:",
      teamNamePlaceholder: "Enter name…",
      updateTeam: "Update",
      updating: "Updating…",
      saveTeam: "Save",
      saving: "Saving…",
      savedMsg: "Team saved!",
      updatedMsg: "Team updated!",
      // validation
      v_pickMonster: "Pick a monster",
      v_setPersonality: "Set a personality",
      v_chooseLegacy: "Choose a legacy type",
      v_select4Moves: "Select 4 moves",
      v_pickTalent: "Pick at least 1 talent boost",
      v_max3: "At most 3 stats can be boosted",
      v_pickMagicItem: "Pick a magic item",
      incompleteTeamMsg: "Team is incomplete. Fill all 6 slots (monster, personality, legacy type, 4 moves, at least 1 talent boost).",
      analysisInProgress: "Analysis already in progress. Please wait for it to complete.",
      analysisFailed: "Analysis failed. Please try again.",
      // slot status labels
      status_complete: "Complete",
      status_incomplete: "Incomplete",
      status_empty: "Empty",
    },
    stats: {
      noStats: "No stats.",
      noEnergy: "No energy profile.",
    },
    labels: {
      hp: "HP",
      phyAtk: "Phy Atk",
      magAtk: "Mag Atk",
      phyDef: "Phy Def",
      magDef: "Mag Def",
      spd: "Speed",
      legacy: "Legacy",
      leader: "Leader",
    },
    analysis: {
      teamOverview: "Team Overview",
      magicItem: "Magic Item",
      offensiveGaps: "Offensive Coverage Gaps:",
      teamWeakTo: "Team Vulnerable To:",
      magicItemTargets: "Valid Targets:",
      perMonster: "Per-Monster Analysis",
      recommendations: "Recommendations",
      avgEnergy: "Avg Energy",
      hasZeroCost: "Has 0-cost move",
      hasRestore: "Has energy restore",
      counters: "Counters",
      noCounters: "No counters",
      defStatusCount: "Defense/Status",
      synergyWith: "Trait synergy with",
      playTips: "Playing Tips",
      teamSynergy: "Team Playing Recommendations",
      keyCombos: "Key Combos",
      turnOrderStrategy: "Turn Order Strategy",
      magicItemUsage: "Magic Item Usage",
      generalStrategy: "General Team Strategy",
    },
    recommendationCategories: {
      coverage: "Type Coverage",
      weakness: "Weakness",
      magic_item: "Magic Item",
      energy: "Energy",
      counters: "Counters",
      defense_status: "Defense/Status",
      trait_synergy: "Trait Synergy",
      role_diversity: "Role Diversity",
      stat_highlight: "Stat Highlight",
      general: "General",
    },
    severity: {
      info: "Info",
      warn: "Warning",
      danger: "Danger",
    },
    errors: {
      rateLimitExceeded: "Too many requests. Please wait before analyzing again.",
      rateLimitTip: "Tip: Analyzing the same team again uses cache and is instant!",
    },
    dex: {
      tab_monsters: "Monsters",
      tab_moves: "Moves",
      tab_items: "Magic Items",
      tab_terms: "Game Terms",
      search: "Search…",
      noResults: "No results.",
      backToDex: "Back to Dex",
      totalBase: "Total Base Stats",
      typesLabel: "Element Types",
      formsLabel: "Forms",
      form_all: "All",
      form_regional: "Regional Forms",
      form_leader: "Leader Forms",
      skill_type: "Move Type",
      skill_category: "Move Category",
      cat_phy: "Physical",
      cat_mag: "Magical",
      cat_def: "Defense",
      cat_sta: "Status",
      defense: "Defense",
      status: "Status",
      move_stone: "Stone",
      learnable: "Learnable Moves",
      legacy: "Legacy Moves",
      evolution: "Evolution",
    },
    teams: {
      manageTeams: "Manage Your Teams",
      backToList: "Back to Teams",
      notFound: "Team not found.",
      noTeams: "No teams yet. Create one in the builder!",
      lastModified: "Last modified",
      actions: "Actions",
      editInBuilder: "Edit in Builder",
      editCopyInBuilder: "Edit Copy in Builder",
      open: "Open",
      analyze: "Analyze",
      analyzing: "Analyzing…",
      delete: "Delete",
      deleting: "Deleting…",
      confirmDelete: "Delete this team? This cannot be undone.",
    },
  },
  zh: {
    common: {
      select: "选择…",
      loading: "载入中…",
      edit: "编辑",
      search: "搜索…",
      showMore: "展开",
      showLess: "收起",
    },
    sidebar: {
      siteName: "洛手配队器™",
      build: "构筑",
      dex: "图鉴",
      teams: "队伍存档",
    },
    topbar: {
      builder: "队伍构筑",
      dex: "图鉴",
      teams: "队伍存档",
      toggleLanguage: "切换语言",
      lang_en_zh: "EN / 中文",
      lang_zh_en: "中文 / EN",
      search: "搜索任何…",
      reset: "重置",
      confirmReset: "重置队伍构筑？这将清空当前队伍与分析结果。",
      quickBuild: "快速组队",
      quickBuilding: "载入中…",
      quickBuildConfirm: "确认快速组队？这将自动生成新的队伍并替换当前队伍。",
      quickBuildFailed: "载入随机队伍失败。",
    },
    builder: {
      slot: "槽位 {{n}}",
      inspectorTitle: "面板 — 槽位 {{n}}",
      changeMonster: "更换精灵",
      viewInDex: "在图鉴中查看",
      deleteMonster: "移除",
      pickAMonster: "选择精灵",
      tipAfterPick: "提示：选择精灵后可设置性格、血脉、技能与个体值。",
      personality: "性格",
      effects: "效果：{{text}}",
      legacyType: "血脉",
      legacyGrants: "血脉提供：{{name}}。该技能仅可占用一个技能栏位。",
      legacyMissing: "该血脉没有可用的血脉技能。",
      legacyHint: "最多选择1个血脉技能。",
      moves: "技能",
      moveN: "技能{{n}}",
      talents: "个体值",
      talentsHint: "最多提升3项个体值。",
      magicItem: "血脉魔法：",
      analyze: "分析",
      analyzing: "分析中…",
      selectMonster: "选择精灵…",
      searchMonsters: "搜索精灵…",
      teamName: "队伍名称：",
      teamNamePlaceholder: "输入名称…",
      updateTeam: "更新",
      updating: "更新中…",
      saveTeam: "保存",
      saving: "保存中…",
      savedMsg: "队伍已保存！",
      updatedMsg: "队伍已更新！",
      // validation
      v_pickMonster: "选择一只精灵",
      v_setPersonality: "设置性格",
      v_chooseLegacy: "选择血脉",
      v_select4Moves: "选择4个技能",
      v_pickTalent: "最少提升1项个体值",
      v_max3: "最多提升3项个体值",
      v_pickMagicItem: "请选择一个血脉魔法",
      incompleteTeamMsg: "队伍未完成：请补全 6 个槽位（精灵、性格、血脉、4 个技能、至少 1 项个体值提升）。",
      analysisInProgress: "分析正在进行中，请等待完成后再试。",
      analysisFailed: "分析失败，请重试。",
      status_complete: "已完成",
      status_incomplete: "待完善",
      status_empty: "未选择",
    },
    stats: {
      noStats: "暂无属性数据。",
      noEnergy: "暂无能量分布。",
    },
    labels: {
      hp: "生命",
      phyAtk: "物攻",
      magAtk: "魔攻",
      phyDef: "物防",
      magDef: "魔防",
      spd: "速度",
      legacy: "血脉",
      leader: "首领",
    },
    analysis: {
      teamOverview: "队伍总览",
      magicItem: "血脉魔法",
      offensiveGaps: "队伍缺少打击面：",
      teamWeakTo: "队伍易被克制：",
      magicItemTargets: "可使用目标：",
      perMonster: "单体分析",
      recommendations: "优化建议",
      avgEnergy: "平均能量",
      hasZeroCost: "含0费技能",
      hasRestore: "含回能技能",
      counters: "应对技能数",
      noCounters: "无应对技能",
      defStatusCount: "防御/状态类技能数",
      synergyWith: "特性与以下技能契合",
      playTips: "玩法技巧",
      teamSynergy: "团队配合推荐",
      keyCombos: "核心连招",
      turnOrderStrategy: "出手顺序策略",
      magicItemUsage: "血脉魔法使用建议",
      generalStrategy: "整体策略",
    },
    recommendationCategories: {
      coverage: "属性覆盖",
      weakness: "弱点",
      magic_item: "魔法道具",
      energy: "能量",
      counters: "克制",
      defense_status: "防御/状态",
      trait_synergy: "特性协同",
      role_diversity: "角色多样性",
      stat_highlight: "属性亮点",
      general: "综合",
    },
    severity: {
      info: "提示",
      warn: "警告",
      danger: "危险",
    },
    errors: {
      rateLimitExceeded: "请求过于频繁，请等待后再试。",
      rateLimitTip: "提示：重新分析相同队伍会使用缓存，无需等待！",
    },
    dex: {
      tab_monsters: "精灵图鉴",
      tab_moves: "技能图鉴",
      tab_items: "血脉魔法",
      tab_terms: "游戏名词",
      search: "搜索…",
      noResults: "暂无结果。",
      backToDex: "返回图鉴",
      totalBase: "种族值",
      typesLabel: "精灵属性",
      formsLabel: "精灵形态",
      form_all: "全部",
      form_regional: "地区形态",
      form_leader: "首领形态",
      skill_type: "技能属性",
      skill_category: "技能类型",
      cat_phy: "物攻",
      cat_mag: "魔攻",
      cat_def: "防御",
      cat_sta: "状态",
      defense: "防御",
      status: "状态",
      move_stone: "技能石",
      learnable: "可学习技能",
      legacy: "血脉技能",
      evolution: "进化链",
    },
    teams: {
      manageTeams: "管理你的队伍",
      backToList: "返回队伍列表",
      notFound: "未找到队伍。",
      noTeams: "暂无队伍存档。前往构筑器创建一个吧！",
      lastModified: "最近修改",
      actions: "操作",
      editInBuilder: "在构筑器中修改",
      editCopyInBuilder: "在构筑器中创建新副本",
      open: "查看",
      analyze: "分析",
      analyzing: "分析中...",
      delete: "删除",
      deleting: "删除中...",
      confirmDelete: "确定要删除该队伍吗？此操作不可恢复。",
    }
  },
};

function resolve(dict: Dict, path: string, vars?: Record<string, any>) {
  const val = path.split(".").reduce<any>((a, k) => (a ? a[k] : undefined), dict);
  const str = typeof val === "string" ? val : path;
  return typeof vars === "object"
    ? str.replace(/\{\{(\w+)\}\}/g, (_, k) => `${vars[k] ?? ""}`)
    : str;
}
type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (key: string, vars?: Record<string, any>) => string; };
const I18nCtx = createContext<Ctx | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLang] = useState<Lang>((localStorage.getItem("lang") as Lang) || "en");
  const value = useMemo<Ctx>(() => ({
      lang,
      setLang: (l) => { localStorage.setItem("lang", l); setLang(l); },
      t: (key, vars) => resolve(ui[lang], key, vars) || resolve(ui.en, key, vars),
    }),
    [lang]
  );
  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nCtx);
  if (!ctx) throw new Error("useI18n must be used inside I18nProvider");
  return ctx;
}