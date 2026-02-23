/**
 * Application constants and configuration values
 */

/* ========== Query Keys ========== */

export const QUERY_KEYS = {
  MONSTERS: ["monsters"] as const,
  MONSTER_DETAIL: (id: number | string) => ["monsters", id] as const,
  MONSTER_LIST: (params?: Record<string, unknown>) =>
    ["monsters", "list", params] as const,

  MOVES: ["moves"] as const,
  MOVE_DETAIL: (id: number | string) => ["moves", id] as const,
  MOVE_LIST: (params?: Record<string, unknown>) =>
    ["moves", "list", params] as const,

  TYPES: ["types"] as const,
  TYPES_INDEX: ["types-index"] as const,

  PERSONALITIES: ["personalities"] as const,

  MAGIC_ITEMS: ["magic_items"] as const,

  GAME_TERMS: ["game_terms"] as const,

  TEAMS: ["teams"] as const,
  TEAM_DETAIL: (id: number | string) => ["teams", id] as const,
  TEAM_LIST: (params?: Record<string, unknown>) =>
    ["teams", "list", params] as const,

  QUOTA: ["quota"] as const,
} as const;

/* ========== Team Configuration ========== */

export const TEAM_CONFIG = {
  /** Number of monsters in a team */
  TEAM_SIZE: 6,
  /** Number of moves per monster */
  MOVES_PER_MONSTER: 4,
  /** Minimum talent boosts required */
  MIN_TALENT_BOOSTS: 1,
  /** Maximum talent boosts allowed */
  MAX_TALENT_BOOSTS: 3,
  /** Maximum talent value per stat */
  MAX_TALENT_VALUE: 31,
  /** Maximum team name length */
  MAX_TEAM_NAME_LENGTH: 50,
} as const;

/* ========== Game Data Configuration ========== */

/**
 * The canonical order of types for legacy moves.
 * This matches the order in backend/scripts/importers/import_legacy_moves.py
 */
export const LEGACY_TYPES_ORDER = [
  "Normal", "Grass", "Fire", "Water", "Light", "Ground", "Ice", "Dragon",
  "Electric", "Poison", "Bug", "Fighting", "Flying", "Cute", "Ghost",
  "Dark", "Mechanical", "Illusion"
] as const;

/* ========== UI Constants ========== */

export const CACHE_TIME = {
  /** Short cache time (30 seconds) */
  SHORT: 30_000,
  /** Medium cache time (5 minutes) */
  MEDIUM: 300_000,
  /** Long cache time (30 minutes) */
  LONG: 1_800_000,
} as const;
