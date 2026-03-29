"""
compare_and_update_stats.py

Compares base stats between lichouxuan-roco/monsters_stats.json (reference)
and backend/data/monsters.json (our data), then optionally applies updates.

Matching logic:
  - Match by Chinese name: monsters_stats.json["name"] == monsters.json["localized"]["zh"]["name"]
  - One stats entry may map to multiple monsters.json entries (different visual forms)
    sharing the same Chinese name — stats apply to all of them.
  - monsters_stats.json only records the default/first form for multi-form monsters,
    so non-default alt-forms without their own stats entry get the same stats.

Stat field mapping:
  monsters_stats.json → monsters.json
  hp               → base_hp
  attack           → base_phy_atk
  special_attack   → base_mag_atk
  defense          → base_phy_def
  special_defense  → base_mag_def
  speed            → base_spd

Usage:
  python3 -m backend.scripts.compare_and_update_stats           # dry run (report only)
  python3 -m backend.scripts.compare_and_update_stats --apply   # apply changes
"""

import json
import sys
import os
from pathlib import Path

STATS_PATH = Path("/mnt/d/Alan/Github Projects/lichouxuan-roco/monsters_stats.json")
MONSTERS_PATH = Path(__file__).parents[2] / "backend" / "data" / "monsters.json"

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
    for arg in sys.argv[1:]:
        if arg.startswith("--output="):
            output_path = arg.split("=", 1)[1]
        elif arg == "--output":
            idx = sys.argv.index("--output")
            if idx + 1 < len(sys.argv):
                output_path = sys.argv[idx + 1]

    stats_list = load_json(STATS_PATH)
    monsters = load_json(MONSTERS_PATH)

    # Build lookup: zh_name → stats entry
    stats_by_zh: dict[str, dict] = {s["name"]: s for s in stats_list}

    # Build lookup: zh_name → list of monster indices in monsters list
    from collections import defaultdict
    monsters_by_zh: dict[str, list[int]] = defaultdict(list)
    for i, m in enumerate(monsters):
        zh = m["localized"]["zh"]["name"]
        monsters_by_zh[zh].append(i)

    # --- Comparison ---
    matched_stats_names: set[str] = set()
    updates: list[dict] = []          # will be applied if --apply
    diffs_report: list[str] = []
    no_change_count = 0
    bad_data_report: list[str] = []  # total == 6 (corrupt source data)

    for zh_name, idxs in sorted(monsters_by_zh.items()):
        if zh_name not in stats_by_zh:
            continue  # handled in "needs manual update" section below

        matched_stats_names.add(zh_name)
        ref = stats_by_zh[zh_name]

        if ref.get("total", 0) == 6:
            for i in idxs:
                bad_data_report.append(f"  [{monsters[i]['name']}] ({zh_name})  total=6 — skipped")
            continue

        for i in idxs:
            m = monsters[i]
            en_name = m["name"]
            changed_fields = []

            for ref_field, our_field in STAT_MAP.items():
                ref_val = ref[ref_field]
                our_val = m.get(our_field)
                if ref_val != our_val:
                    changed_fields.append((our_field, our_val, ref_val))

            if changed_fields:
                updates.append({"idx": i, "fields": changed_fields})
                lines = [f"  [{en_name}] ({zh_name})"]
                for field, old, new in changed_fields:
                    lines.append(f"    {field}: {old} → {new}")
                diffs_report.append("\n".join(lines))
            else:
                no_change_count += 1

    # --- Monsters needing manual update (no stats entry found) ---
    manual_update_needed: list[tuple[str, str]] = []  # (en_name, zh_name)
    for i, m in enumerate(monsters):
        zh = m["localized"]["zh"]["name"]
        if zh not in stats_by_zh:
            manual_update_needed.append((m["name"], zh))

    # --- Stats entries missing from monsters.json ---
    missing_from_our_db: list[str] = []
    for s in stats_list:
        if s["name"] not in monsters_by_zh:
            missing_from_our_db.append(s["name"])

    # --- Print report ---
    out = open(output_path, "w", encoding="utf-8") if output_path else sys.stdout

    def p(*args, **kwargs):
        print(*args, **kwargs, file=out)

    p("=" * 70)
    p("MONSTER STATS COMPARISON REPORT")
    p("=" * 70)

    p(f"\n{'─'*70}")
    p(f"STATS UPDATES AVAILABLE ({len(diffs_report)} monsters with differences, {no_change_count} already match)")
    p(f"{'─'*70}")
    if diffs_report:
        for line in diffs_report:
            p(line)
    else:
        p("  (none — all matched monsters already have correct stats)")

    p(f"\n{'─'*70}")
    p(f"SKIPPED — bad source data (total=6) ({len(bad_data_report)} entries)")
    p(f"{'─'*70}")
    if bad_data_report:
        for line in bad_data_report:
            p(line)
    else:
        p("  (none)")

    p(f"\n{'─'*70}")
    p(f"NEEDS MANUAL UPDATE — in monsters.json but NOT in monsters_stats.json ({len(manual_update_needed)} entries)")
    p(f"{'─'*70}")
    if manual_update_needed:
        for en, zh in manual_update_needed:
            p(f"  [{en}] ({zh})")
    else:
        p("  (none)")

    p(f"\n{'─'*70}")
    p(f"MISSING FROM monsters.json — in monsters_stats.json but NOT in our data ({len(missing_from_our_db)} entries)")
    p(f"{'─'*70}")
    if missing_from_our_db:
        for zh in missing_from_our_db:
            ref = stats_by_zh[zh]
            p(f"  {zh}  (HP:{ref['hp']} ATK:{ref['attack']} SPATK:{ref['special_attack']} DEF:{ref['defense']} SPDEF:{ref['special_defense']} SPD:{ref['speed']})")
    else:
        p("  (none)")

    p(f"\n{'─'*70}")
    p("SUMMARY")
    p(f"{'─'*70}")
    p(f"  monsters_stats.json entries : {len(stats_list)}")
    p(f"  monsters.json entries       : {len(monsters)}")
    p(f"  Matched by Chinese name     : {len(matched_stats_names)} unique zh names")
    p(f"  Stats differ (auto-fix)     : {len(diffs_report)} monsters")
    p(f"  Stats already correct       : {no_change_count} monsters")
    p(f"  Skipped (bad source data)   : {len(bad_data_report)} monsters")
    p(f"  Needs manual update         : {len(manual_update_needed)} monsters")
    p(f"  Missing from monsters.json  : {len(missing_from_our_db)} monsters")
    p()

    if output_path:
        out.close()
        print(f"Report saved to {output_path}")

    if not apply:
        print("Dry run — no changes written. Re-run with --apply to update monsters.json.")
        return

    # --- Apply updates ---
    if not updates:
        print("Nothing to update.")
        return

    for u in updates:
        for field, _, new_val in u["fields"]:
            monsters[u["idx"]][field] = new_val

    save_json(MONSTERS_PATH, monsters)
    print(f"Applied stat updates to {len(updates)} monster entries.")


if __name__ == "__main__":
    main()
