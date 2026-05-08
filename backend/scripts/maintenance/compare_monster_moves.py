#!/usr/bin/env python3
"""
Compare monster move assignments between an external source (monsters_all2.json)
and the local monster_moves.json, using the moveset_key logic from monsters.json.

Moveset-key rules (from monsters.json):
  - Single-form evo chains (A→B→C): all stages share the same moveset_key,
    which equals the final evo's zh name. Only the final evo is compared.
  - Multi-form (A→B1/B2): each form has its own moveset_key.
  - Leader forms (is_leader_form=True): skipped entirely.

Match logic:
  1. Build zh_name → moveset_key from monsters.json (non-leader only).
  2. For each source entry, resolve its moveset_key via zh_name lookup
     (exact, then normalized — strip hyphens/spaces).
  3. Compare the source entry whose name == moveset_key (the canonical form)
     against monster_moves.json[moveset_key].
  4. Lower-evo source entries that map to the same moveset_key are ignored
     (local intentionally uses the final evo's moveset for all stages).
  5. Source entries that can't be resolved to any moveset_key → genuinely new.

Source fields:
  moves      → learnable_moves
  jinengshi  → move_stones
  xuemai     → legacy_moves

Usage (from project root):
  python3 -m backend.scripts.maintenance.compare_monster_moves
  python3 -m backend.scripts.maintenance.compare_monster_moves --source /path/to/monsters_all2.json
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict

SOURCE_JSON       = Path(r"D:\Alan\Github Projects\roco-kingdom-team-builder\backend\data\monsters_all2.json")
LOCAL_MONSTERS    = Path(__file__).resolve().parents[2] / "data" / "monsters.json"
LOCAL_MOVES       = Path(__file__).resolve().parents[2] / "data" / "monster_moves.json"
REPORTS_DIR       = Path(__file__).resolve().parents[2] / "data" / "move_reports"

FIELD_MAP = [
    ("moves",     "learnable_moves", "Learnable"),
    ("jinengshi", "move_stones",     "Move Stones"),
    ("xuemai",    "legacy_moves",    "Legacy"),
]


# ── helpers ──────────────────────────────────────────────────────────────────

def normalize(name: str) -> str:
    return name.replace("-", "").replace(" ", "").replace("　", "")

def parse_wiki_moves(value: str) -> set:
    if not value:
        return set()
    return {m.strip() for m in value.split(",") if m.strip()}

def load_source(path: Path) -> dict:
    """source_name → {learnable_moves, move_stones, legacy_moves} as sets."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {
        m["name"]: {
            "learnable_moves": parse_wiki_moves(m.get("moves", "")),
            "move_stones":     parse_wiki_moves(m.get("jinengshi", "")),
            "legacy_moves":    parse_wiki_moves(m.get("xuemai", "")),
        }
        for m in raw
    }

def load_local_moves(path: Path) -> dict:
    """moveset_key → {learnable_moves, move_stones, legacy_moves} as sets."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {
        key: {
            "learnable_moves": set(data.get("learnable_moves") or []),
            "move_stones":     set(data.get("move_stones") or []),
            "legacy_moves":    set(data.get("legacy_moves") or []),
        }
        for key, data in raw.items()
    }

def build_known_names(monsters_path: Path):
    """
    Returns a set of normalize(zh_name) for all non-leader monsters in monsters.json.
    Used to distinguish lower-evo source entries (known in monsters.json) from
    genuinely new monsters (not in monsters.json at all).

    Source entries often combine zh_name + form suffix (e.g. '丢丢草地附近的样子')
    while monsters.json stores just the base zh name ('丢丢').  We therefore
    check prefix containment, not exact match.
    """
    with open(monsters_path, encoding="utf-8") as f:
        monsters = json.load(f)
    known = set()
    for m in monsters:
        if m.get("is_leader_form"):
            continue
        zh = m.get("localized", {}).get("zh", {}).get("name", "")
        if zh:
            known.add(normalize(zh))
    return known


def is_known_in_monsters(source_name: str, known_zh_norms: set) -> bool:
    """
    Return True if this source name is already accounted for in monsters.json.
    Handles two cases:
      - Exact normalized match  (e.g. lower-evo with same name)
      - Prefix match            (e.g. '丢丢草地附近的样子' starts with '丢丢')
    """
    norm = normalize(source_name)
    for zh_norm in known_zh_norms:
        if norm == zh_norm or norm.startswith(zh_norm):
            return True
    return False


def compare_moves(wiki_data: dict, local_data: dict):
    """Return list of (label, added, removed) for fields that differ."""
    diffs = []
    for _, field, label in FIELD_MAP:
        w = wiki_data[field]
        l = local_data[field]
        added   = sorted(w - l)
        removed = sorted(l - w)
        if added or removed:
            diffs.append((label, added, removed))
    return diffs


# ── main ─────────────────────────────────────────────────────────────────────

def generate_report(source_path: Path):
    print(f"Loading source: {source_path}")
    print(f"Loading local:  {LOCAL_MOVES}")
    print()

    source      = load_source(source_path)
    local_moves = load_local_moves(LOCAL_MOVES)
    known_zh_norms = build_known_names(LOCAL_MONSTERS)

    # Build source lookup by normalized name for fast access
    source_by_norm = {normalize(sname): sname for sname in source}

    # ── For each local moveset_key, find its canonical source entry ────────
    # The canonical source entry is the one whose name matches the moveset_key
    # directly (exact or normalized). Lower-evo source entries are NOT used
    # for comparison — local intentionally uses the final-evo moveset for all
    # stages in the chain.
    monsters_with_diffs = []   # (moveset_key, canonical_source_name, diffs)
    keys_no_source_entry = []  # moveset_key not found in source at all

    for key, local_data in sorted(local_moves.items()):
        # Exact match first, then normalized
        if key in source:
            canonical = key
        elif normalize(key) in source_by_norm:
            canonical = source_by_norm[normalize(key)]
        else:
            keys_no_source_entry.append(key)
            continue

        diffs = compare_moves(source[canonical], local_data)
        if diffs:
            monsters_with_diffs.append((key, canonical, diffs))

    # ── Classify source entries ────────────────────────────────────────────
    # A source entry is "genuinely new" if its normalized name is NOT recognized
    # as any zh_name in monsters.json (it's a brand new monster not yet added
    # locally). Entries recognized in monsters.json are lower-evo / alternate
    # forms that intentionally share a moveset_key with their final-evo form.
    canonical_source_norms = {normalize(key) for key in local_moves}
    unresolved_source = [
        sname for sname in source
        if normalize(sname) not in canonical_source_norms
        and not is_known_in_monsters(sname, known_zh_norms)
    ]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Report 1: Move diffs ───────────────────────────────────────────────
    report1 = REPORTS_DIR / "monster_move_diffs.txt"
    with open(report1, "w", encoding="utf-8") as f:
        f.write("MONSTER MOVE DIFFS — source (monsters_all2.json) vs local monster_moves.json\n")
        f.write("Comparison is done on the canonical (final-evo / form) source entry only.\n")
        f.write("=" * 80 + "\n\n")
        if monsters_with_diffs:
            for key, canonical, diffs in monsters_with_diffs:
                label = key if key == canonical else f"{key}  (source name: {canonical})"
                f.write(f"{label}\n")
                for field_label, added, removed in diffs:
                    if added:
                        f.write(f"  [{field_label}] SOURCE HAS (not in local) : {', '.join(added)}\n")
                    if removed:
                        f.write(f"  [{field_label}] LOCAL HAS (not in source)  : {', '.join(removed)}\n")
                f.write("\n")
        else:
            f.write("No differences found.\n")

    print(f"{'=' * 60}")
    print(f"Report 1: Move diffs ({len(monsters_with_diffs)} monsters with diffs)")
    print("=" * 60)
    for key, canonical, diffs in monsters_with_diffs:
        label = key if key == canonical else f"{key}  (source: {canonical})"
        print(f"  {label}")
        for field_label, added, removed in diffs:
            if added:
                print(f"    [{field_label}] source adds: {added}")
            if removed:
                print(f"    [{field_label}] local only : {removed}")
    print(f"\n  Saved → {report1}")

    # ── Report 2: Genuinely new source entries (not in monsters.json) ──────
    report2 = REPORTS_DIR / "monster_moves_new_in_source.txt"
    with open(report2, "w", encoding="utf-8") as f:
        f.write("SOURCE ENTRIES NOT IN monsters.json\n")
        f.write("These are monsters not yet added to the local dataset at all.\n")
        f.write("=" * 80 + "\n\n")
        for sname in sorted(unresolved_source):
            d = source[sname]
            f.write(f"{sname}\n")
            f.write(f"  Learnable  : {', '.join(sorted(d['learnable_moves']))}\n")
            f.write(f"  Move Stones: {', '.join(sorted(d['move_stones']))}\n")
            f.write(f"  Legacy     : {', '.join(sorted(d['legacy_moves']))}\n\n")

    print(f"\n{'=' * 60}")
    print(f"Report 2: Genuinely new source entries not in monsters.json ({len(unresolved_source)})")
    print("=" * 60)
    for name in sorted(unresolved_source):
        print(f"  {name}")
    print(f"\n  Saved → {report2}")

    # ── Report 3: Local moveset_keys with no source entry ─────────────────
    # These are forms the source simply doesn't track separately (e.g. one
    # entry covers all forms, while local tracks each form individually).
    # Nothing is missing locally — source is simply less granular.
    report3 = REPORTS_DIR / "monster_moves_no_source.txt"
    with open(report3, "w", encoding="utf-8") as f:
        f.write("LOCAL moveset_keys WITH NO CANONICAL SOURCE ENTRY\n")
        f.write("The source does not list these forms as separate entries.\n")
        f.write("Local data is complete — source is simply less granular.\n")
        f.write("=" * 80 + "\n\n")
        for key in sorted(keys_no_source_entry):
            f.write(f"{key}\n")

    print(f"\n{'=' * 60}")
    print(f"Report 3: Local keys with no source entry ({len(keys_no_source_entry)}) — source doesn't list these forms separately")
    print("=" * 60)
    for key in sorted(keys_no_source_entry):
        print(f"  {key}")
    print(f"\n  Saved → {report3}")

    # ── Summary ────────────────────────────────────────────────────────────
    total_matched = len(local_moves) - len(keys_no_source_entry)
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"  Source entries            : {len(source)}")
    print(f"  Local moveset_keys        : {len(local_moves)}")
    print(f"  Canonical matches         : {total_matched}")
    print(f"  With move diffs           : {len(monsters_with_diffs)}")
    print(f"  Genuinely new in source   : {len(unresolved_source)}  (not in monsters.json at all)")
    print(f"  Local key, no source entry: {len(keys_no_source_entry)}  (source not granular enough for these forms)")
    print(f"\n  Reports in: {REPORTS_DIR}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE_JSON,
                        help="Path to monsters_all2.json")
    args = parser.parse_args()
    generate_report(args.source)
