"""
reorder_legacy_moves.py

Reorders the legacy_moves array in monster_moves.json so each move sits at
the position matching its type in LEGACY_TYPES_ORDER.

How it works:
  1. Build a zh_name → English type map from moves.json.
  2. For each monster, look up the type of each legacy move and slot it into
     the correct position.
  3. Warn about any move whose type cannot be resolved or doesn't appear in
     LEGACY_TYPES_ORDER.
  4. Write the corrected file (dry run by default).

Usage:
  python3 -m backend.scripts.maintenance.reorder_legacy_moves          # dry run
  python3 -m backend.scripts.maintenance.reorder_legacy_moves --apply  # write changes
"""

import json
import sys
from pathlib import Path

MOVES_PATH        = Path(__file__).parents[3] / "backend" / "data" / "moves.json"
MONSTER_MOVES_PATH = Path(__file__).parents[3] / "backend" / "data" / "monster_moves.json"

LEGACY_TYPES_ORDER = [
    "Normal", "Grass", "Fire", "Water", "Light", "Ground", "Ice", "Dragon",
    "Electric", "Poison", "Bug", "Fighting", "Flying", "Cute", "Ghost",
    "Dark", "Mechanical", "Illusion",
]
N = len(LEGACY_TYPES_ORDER)  # 18


def build_zh_type_map(moves: list) -> dict[str, str]:
    """zh_name → English type name"""
    m = {}
    for mv in moves:
        zh = mv.get("localized", {}).get("zh", {}).get("name")
        t = mv.get("type")
        if zh and t:
            m[zh] = t
        # also map English name for robustness
        if mv.get("name") and t:
            m[mv["name"]] = t
    return m


def reorder_for_monster(moveset_key: str, legacy: list, zh_type: dict) -> tuple[list, list]:
    """
    Return (reordered_list, warnings).
    reordered_list has exactly N entries; unknown/unplaceable moves are flagged.
    """
    warnings = []
    slots: list[str | None] = [None] * N

    for move in legacy:
        t = zh_type.get(move)
        if t is None:
            warnings.append(f"  [{moveset_key}] '{move}' — type not found in moves.json")
            continue
        if t not in LEGACY_TYPES_ORDER:
            warnings.append(f"  [{moveset_key}] '{move}' type '{t}' not in LEGACY_TYPES_ORDER")
            continue
        idx = LEGACY_TYPES_ORDER.index(t)
        if slots[idx] is not None:
            warnings.append(
                f"  [{moveset_key}] type '{t}' slot already filled by '{slots[idx]}', "
                f"cannot also place '{move}'"
            )
            continue
        slots[idx] = move

    # Report any unfilled slots
    for i, s in enumerate(slots):
        if s is None:
            warnings.append(
                f"  [{moveset_key}] no move found for type '{LEGACY_TYPES_ORDER[i]}' (slot {i+1})"
            )

    return slots, warnings


def format_legacy_array(moves: list[str | None]) -> str:
    """Format as compact single-line JSON array."""
    entries = [f'"{m}"' if m else '"???"' for m in moves]
    return "[\n    " + ", ".join(entries) + "\n  ]"


def main():
    apply = "--apply" in sys.argv

    moves     = json.load(open(MOVES_PATH, encoding="utf-8"))
    raw_text  = MONSTER_MOVES_PATH.read_text(encoding="utf-8")
    data      = json.loads(raw_text)

    zh_type = build_zh_type_map(moves)

    all_warnings: list[str] = []
    changes: dict[str, list] = {}   # moveset_key → new legacy_moves list
    already_correct = 0
    skipped_wrong_count = 0

    for moveset_key, moveset in data.items():
        legacy = moveset.get("legacy_moves", [])

        if len(legacy) == 0:
            # Form variants not yet filled in — silently skip
            continue

        if len(legacy) != N:
            print(
                f"SKIP [{moveset_key}]: has {len(legacy)} legacy moves, expected {N}"
            )
            skipped_wrong_count += 1
            continue

        reordered, warnings = reorder_for_monster(moveset_key, legacy, zh_type)
        all_warnings.extend(warnings)

        if reordered == legacy:
            already_correct += 1
        else:
            changes[moveset_key] = reordered

    # --- Report ---
    print("=" * 70)
    print("LEGACY MOVES REORDER REPORT")
    print("=" * 70)

    if changes:
        print(f"\nMONSTERS TO REORDER ({len(changes)}):")
        for key, new_order in changes.items():
            old = data[key]["legacy_moves"]
            print(f"\n  [{key}]")
            print(f"    Before: {old}")
            print(f"    After:  {new_order}")
    else:
        print("\n  (none — all legacy_moves arrays are already in correct order)")

    if all_warnings:
        print(f"\nWARNINGS ({len(all_warnings)}):")
        for w in all_warnings:
            print(w)

    print(f"\nSUMMARY")
    print(f"  Total movesets          : {len(data)}")
    print(f"  Already correct         : {already_correct}")
    print(f"  Need reordering         : {len(changes)}")
    print(f"  Skipped (wrong count)   : {skipped_wrong_count}")
    print(f"  Warnings                : {len(all_warnings)}")

    if not apply:
        print("\nDry run — no changes written. Re-run with --apply to update monster_moves.json.")
        return

    if not changes:
        print("\nNothing to update.")
        return

    # Apply changes
    for key, new_order in changes.items():
        data[key]["legacy_moves"] = new_order

    # Re-serialize preserving the custom format (10 moves per row for learnable/stones,
    # single row for legacy since it's always exactly 18)
    from backend.scripts.transform.transform_monster_moves import format_monster_moves_json
    output = format_monster_moves_json(data)
    MONSTER_MOVES_PATH.write_text(output, encoding="utf-8")
    print(f"\n✓ Written {len(changes)} reordered movesets to {MONSTER_MOVES_PATH}")


if __name__ == "__main__":
    main()
