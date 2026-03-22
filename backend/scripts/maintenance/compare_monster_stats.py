"""
compare_monster_stats.py

Compares base stats between monsters_all.json (raw source) and monsters.json
(our working data) for all single-form monsters across all evolution stages.

Rules:
  - Single form: exactly one entry for that name in monsters.json.
    Multi-form monsters (e.g. Yajiking with Fluffy/Compact/Get-Up Duck) are
    skipped because monsters_all.json only records one set of stats and we
    cannot determine which form it corresponds to.
  - All evolution stages are included (not just final stage).
  - Matching: monsters_all.json `name` (Chinese) matched against
    monsters.json `localized.zh.name`.

Stat field mapping (monsters_all.json → monsters.json):
  hp               → base_hp
  attack           → base_phy_atk
  special_attack   → base_mag_atk
  defense          → base_phy_def
  special_defense  → base_mag_def
  speed            → base_spd

Usage:
  python3 -m backend.scripts.maintenance.compare_monster_stats          # report only
  python3 -m backend.scripts.maintenance.compare_monster_stats --apply  # write changes
  python3 -m backend.scripts.maintenance.compare_monster_stats --output=report.txt
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

MONSTERS_ALL_PATH = Path(__file__).parents[3] / "backend" / "data" / "monsters_all.json"
MONSTERS_PATH = Path(__file__).parents[3] / "backend" / "data" / "monsters.json"

STAT_MAP = {
    "hp": "base_hp",
    "attack": "base_phy_atk",
    "special_attack": "base_mag_atk",
    "defense": "base_phy_def",
    "special_defense": "base_mag_def",
    "speed": "base_spd",
}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✓ Saved updated monsters.json to {path}")


def main():
    apply = "--apply" in sys.argv

    output_path = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg.startswith("--output="):
            output_path = arg.split("=", 1)[1]
        elif arg == "--output" and i + 1 < len(sys.argv):
            output_path = sys.argv[i + 1]

    monsters_all = load_json(MONSTERS_ALL_PATH)
    monsters = load_json(MONSTERS_PATH)

    # --- Identify single-form monsters across all evolution stages ---
    # Group by English name
    by_name: dict[str, list[int]] = defaultdict(list)
    for i, m in enumerate(monsters):
        by_name[m["name"]].append(i)

    # Qualify: single form only (all stages included)
    qualified_idxs: dict[str, int] = {}  # en_name → index in monsters list
    skipped_multi_form: list[str] = []

    for en_name, idxs in by_name.items():
        if len(idxs) > 1:
            skipped_multi_form.append(en_name)
            continue
        qualified_idxs[en_name] = idxs[0]

    # Build lookup: zh_name → index in monsters list (for qualified only)
    zh_to_idx: dict[str, int] = {}
    for en_name, idx in qualified_idxs.items():
        zh = monsters[idx]["localized"]["zh"]["name"]
        zh_to_idx[zh] = idx

    # Build lookup: zh_name → monsters_all entry
    all_by_zh: dict[str, dict] = {m["name"]: m for m in monsters_all}

    # --- Compare ---
    diffs: list[dict] = []       # {idx, en_name, zh_name, fields: [(field, old, new)]}
    no_change: list[str] = []
    not_in_all: list[str] = []   # in monsters.json but not in monsters_all.json
    skipped_bad_data: list[str] = []  # source has placeholder stats (any stat <= 1)

    for zh_name, idx in sorted(zh_to_idx.items()):
        if zh_name not in all_by_zh:
            not_in_all.append(monsters[idx]["name"])
            continue

        ref = all_by_zh[zh_name]
        m = monsters[idx]
        changed_fields = []

        # Skip monsters with bad source data (any stat <= 1 indicates placeholder)
        if any(ref.get(f, 0) <= 1 for f in STAT_MAP):
            skipped_bad_data.append(m["name"])
            continue

        for src_field, dst_field in STAT_MAP.items():
            ref_val = ref.get(src_field)
            our_val = m.get(dst_field)
            if ref_val is None:
                continue
            if ref_val != our_val:
                changed_fields.append((dst_field, our_val, ref_val))

        if changed_fields:
            diffs.append({
                "idx": idx,
                "en_name": m["name"],
                "zh_name": zh_name,
                "fields": changed_fields,
            })
        else:
            no_change.append(m["name"])

    # --- Report ---
    out = open(output_path, "w", encoding="utf-8") if output_path else sys.stdout

    def p(*args, **kwargs):
        print(*args, **kwargs, file=out)

    p("=" * 70)
    p("MONSTER STATS COMPARISON REPORT (monsters_all.json vs monsters.json)")
    p("Scope: all evolution stages, single-form monsters only")
    p("=" * 70)

    p(f"\n{'─'*70}")
    p(f"STATS UPDATES AVAILABLE ({len(diffs)} monsters with differences, {len(no_change)} already match)")
    p(f"{'─'*70}")
    if diffs:
        for d in diffs:
            p(f"  [{d['en_name']}] ({d['zh_name']})")
            for field, old, new in d["fields"]:
                p(f"    {field}: {old} → {new}")
    else:
        p("  (none — all compared monsters already have correct stats)")

    p(f"\n{'─'*70}")
    p(f"NOT IN monsters_all.json ({len(not_in_all)} monsters — no reference stats available)")
    p(f"{'─'*70}")
    if not_in_all:
        for en in not_in_all:
            p(f"  {en}")
    else:
        p("  (none)")

    p(f"\n{'─'*70}")
    p(f"SKIPPED — bad source data, any stat <= 1 ({len(skipped_bad_data)} monsters)")
    p(f"{'─'*70}")
    if skipped_bad_data:
        for en in skipped_bad_data:
            p(f"  {en}")
    else:
        p("  (none)")

    p(f"\n{'─'*70}")
    p(f"SKIPPED — multi-form ({len(skipped_multi_form)} monsters)")
    p(f"{'─'*70}")
    if skipped_multi_form:
        for en in sorted(skipped_multi_form):
            p(f"  {en}")
    else:
        p("  (none)")

    p(f"\n{'─'*70}")
    p("SUMMARY")
    p(f"{'─'*70}")
    p(f"  monsters_all.json entries      : {len(monsters_all)}")
    p(f"  monsters.json entries          : {len(monsters)}")
    p(f"  Qualified (single-form)        : {len(qualified_idxs)}")
    p(f"  Matched against monsters_all   : {len(diffs) + len(no_change)}")
    p(f"  Stats differ (auto-fix)        : {len(diffs)}")
    p(f"  Stats already correct          : {len(no_change)}")
    p(f"  Not in monsters_all.json       : {len(not_in_all)}")
    p(f"  Skipped (bad source data)      : {len(skipped_bad_data)}")
    p(f"  Skipped (multi-form)           : {len(skipped_multi_form)}")
    p()

    if output_path:
        out.close()
        print(f"Report saved to {output_path}")

    if not apply:
        print("Dry run — no changes written. Re-run with --apply to update monsters.json.")
        return

    # --- Apply ---
    if not diffs:
        print("Nothing to update.")
        return

    for d in diffs:
        for field, _, new_val in d["fields"]:
            monsters[d["idx"]][field] = new_val

    save_json(MONSTERS_PATH, monsters)
    print(f"Applied stat updates to {len(diffs)} monster entries.")


if __name__ == "__main__":
    main()
