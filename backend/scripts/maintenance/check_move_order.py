"""
check_move_order.py

Checks the last N moves of learnable_moves and move_stones in monster_moves.json
for priority-order anomalies. Types have a canonical priority order (Normal first,
Illusion last). A tail move is an anomaly if its type has HIGHER priority (lower
index in TYPE_PRIORITY_ORDER) than the most recent preceding move of a different
type — meaning it was appended out of order.

Example (tail=3): [..., Illusion, Illusion, Normal, Grass, Fire]
  - Fire (index 2) compared to Grass (index 1) before it → Fire > Grass priority? No, Fire=2, Grass=1 → Fire is lower priority, fine
  - Grass (index 1) compared to Normal (index 0) before it → Grass > Normal priority? No → fine
  - Normal (index 0) compared to Illusion (index 17) before it → Normal IS higher priority → anomaly

Usage:
  python3 -m backend.scripts.maintenance.check_move_order              # tail=3
  python3 -m backend.scripts.maintenance.check_move_order --tail=5
  python3 -m backend.scripts.maintenance.check_move_order --output=report.txt
"""

import json
import sys
from pathlib import Path

MOVES_PATH         = Path(__file__).parents[3] / "backend" / "data" / "moves.json"
MONSTER_MOVES_PATH = Path(__file__).parents[3] / "backend" / "data" / "monster_moves.json"

TYPE_PRIORITY_ORDER = [
    "Normal", "Grass", "Fire", "Water", "Light", "Ground", "Ice", "Dragon",
    "Electric", "Poison", "Bug", "Fighting", "Flying", "Cute", "Ghost",
    "Dark", "Mechanical", "Illusion",
]

def type_priority(t: str | None) -> int:
    """Lower index = higher priority. Unknown types get 999."""
    if t is None:
        return 999
    try:
        return TYPE_PRIORITY_ORDER.index(t)
    except ValueError:
        return 999


def build_zh_type_map(moves: list) -> dict[str, str | None]:
    """zh_name / en_name → English type name (or None)"""
    m: dict[str, str | None] = {}
    for mv in moves:
        t = mv.get("type")
        zh = mv.get("localized", {}).get("zh", {}).get("name")
        if zh:
            m[zh] = t
        if mv.get("name"):
            m[mv["name"]] = t
    return m


def find_tail_anomalies(move_list: list[str], zh_type: dict, tail: int) -> list[dict]:
    """
    For each of the last `tail` moves, find the most recent preceding move of a
    different known type and compare priorities. Flag the tail move if its type
    has HIGHER priority (lower index) than that preceding move's type.

    Returns list of {"move", "type", "priority", "prev_move", "prev_type",
                      "prev_priority", "index", "unknown"}.
    """
    if not move_list:
        return []

    # Resolve all types up front
    resolved: list[tuple[str, str | None]] = []  # (move_name, type_or_None)
    for move in move_list:
        if move not in zh_type:
            resolved.append((move, "__unknown__"))
        else:
            resolved.append((move, zh_type[move]))

    tail_start = max(0, len(resolved) - tail)
    anomalies = []

    for i in range(tail_start, len(resolved)):
        move, t = resolved[i]

        if t == "__unknown__":
            anomalies.append({
                "move": move, "type": "???", "priority": 999,
                "prev_move": None, "prev_type": None, "prev_priority": None,
                "index": i, "unknown": True,
            })
            continue

        if t is None:
            # Typeless move — skip
            continue

        # Find the most recent preceding move with a different known type
        prev_move_name = None
        prev_type = None
        for j in range(i - 1, -1, -1):
            _, pt = resolved[j]
            if pt is None or pt == "__unknown__":
                continue
            if pt != t:
                prev_move_name = resolved[j][0]
                prev_type = pt
                break

        if prev_type is None:
            # No preceding move with a different type — nothing to compare
            continue

        curr_priority = type_priority(t)
        prev_priority = type_priority(prev_type)

        if curr_priority < prev_priority:
            anomalies.append({
                "move": move, "type": t, "priority": curr_priority,
                "prev_move": prev_move_name, "prev_type": prev_type,
                "prev_priority": prev_priority,
                "index": i, "unknown": False,
            })

    return anomalies


def main():
    tail = 3
    output_path = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg.startswith("--tail="):
            tail = int(arg.split("=", 1)[1])
        elif arg.startswith("--output="):
            output_path = arg.split("=", 1)[1]
        elif arg == "--output" and i + 1 < len(sys.argv):
            output_path = sys.argv[i + 1]

    moves_raw     = json.load(open(MOVES_PATH, encoding="utf-8"))
    monster_moves = json.load(open(MONSTER_MOVES_PATH, encoding="utf-8"))
    zh_type       = build_zh_type_map(moves_raw)

    out = open(output_path, "w", encoding="utf-8") if output_path else sys.stdout

    def p(*args, **kwargs):
        print(*args, **kwargs, file=out)

    flagged_monsters: list[dict] = []

    for moveset_key, moveset in monster_moves.items():
        issues: dict[str, list] = {}

        for pool_name in ("learnable_moves", "move_stones"):
            move_list = moveset.get(pool_name, [])
            if not move_list:
                continue
            anomalies = find_tail_anomalies(move_list, zh_type, tail)
            if anomalies:
                issues[pool_name] = anomalies

        if issues:
            flagged_monsters.append({"key": moveset_key, "issues": issues})

    # --- Report ---
    p("=" * 70)
    p("MOVE TYPE ORDERING REPORT")
    p(f"Scope: last {tail} moves of learnable_moves + move_stones")
    p(f"Anomaly: tail move has HIGHER priority type than preceding move")
    p("=" * 70)

    if not flagged_monsters:
        p("\n  (none — no ordering anomalies detected in the last {tail} moves)")
    else:
        for entry in flagged_monsters:
            p(f"\n[{entry['key']}]")
            for pool_name, anomalies in entry["issues"].items():
                p(f"  {pool_name}:")
                for a in anomalies:
                    if a.get("unknown"):
                        p(f"    pos {a['index']+1:>3}: '{a['move']}' — not found in moves.json")
                    else:
                        p(
                            f"    pos {a['index']+1:>3}: '{a['move']}' ({a['type']}, priority={a['priority']+1})"
                            f" > '{a['prev_move']}' ({a['prev_type']}, priority={a['prev_priority']+1})"
                        )

    p(f"\n{'─'*70}")
    p("SUMMARY")
    p(f"{'─'*70}")
    p(f"  Total movesets checked : {len(monster_moves)}")
    p(f"  Movesets with anomalies: {len(flagged_monsters)}")
    p()

    if output_path:
        out.close()
        print(f"Report saved to {output_path}")


if __name__ == "__main__":
    main()
