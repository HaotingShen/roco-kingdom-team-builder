import type { MoveOut, StatusOut } from "@/types";

function modifiesOffense(status: StatusOut): boolean {
  return (
    status.phy_atk_boost !== 0 ||
    status.mag_atk_boost !== 0 ||
    status.flat_power_boost !== 0 ||
    status.pct_power_boost !== 0 ||
    status.dmg_bonus_pct !== 0
  );
}

function isAttackerStatusOption(status: StatusOut): boolean {
  const usage = status.usage ?? "all";
  const affect = status.affect ?? "self";
  return (
    (usage === "all" || usage === "attack_only") &&
    affect === "self" &&
    modifiesOffense(status)
  );
}

export function getAttackerStatusOptions(moves: readonly MoveOut[]): StatusOut[] {
  const seen = new Set<number>();
  const statuses: StatusOut[] = [];
  for (const move of moves) {
    for (const status of move.statuses ?? []) {
      if (seen.has(status.id) || !isAttackerStatusOption(status)) continue;
      seen.add(status.id);
      statuses.push(status);
    }
  }
  return statuses;
}
