"""
Phase 7: Generate Import Preview

This script shows what will change in the database when the transformed
data is imported. It compares existing data with transformed data.

Usage:
    python3 -m backend.scripts.generate_import_preview
    python3 -m backend.scripts.generate_import_preview --detailed

Requirements:
    - Transformed monsters.json must exist
"""

import json
from pathlib import Path
from collections import defaultdict
import argparse

# File paths
BACKEND_DIR = Path(__file__).parent.parent.parent
OLD_MONSTERS_JSON = BACKEND_DIR / "data" / "monsters.json.backup"  # Backup of old file
NEW_MONSTERS_JSON = BACKEND_DIR / "data" / "monsters.json"
OLD_SPECIES_JSON = BACKEND_DIR / "data" / "monster_species.json.backup"
NEW_SPECIES_JSON = BACKEND_DIR / "data" / "monster_species.json"


def compare_stats(old, new):
    """Compare monster stats and return differences."""
    stat_fields = [
        'base_hp', 'base_phy_atk', 'base_mag_atk',
        'base_phy_def', 'base_mag_def', 'base_spd'
    ]

    changes = {}
    for field in stat_fields:
        old_val = old.get(field, 0)
        new_val = new.get(field, 0)
        if old_val != new_val:
            changes[field] = {'old': old_val, 'new': new_val}

    return changes


def generate_preview(detailed=False):
    """Generate import preview showing what will change."""
    print("=" * 70)
    print("Phase 7: Import Preview")
    print("=" * 70)
    print()

    # Step 1: Create backup if it doesn't exist
    if not OLD_MONSTERS_JSON.exists():
        print("Creating backup of current monsters.json...")
        if NEW_MONSTERS_JSON.exists():
            with open(NEW_MONSTERS_JSON, encoding="utf-8") as f:
                old_data = json.load(f)
            with open(OLD_MONSTERS_JSON, "w", encoding="utf-8") as f:
                json.dump(old_data, f, ensure_ascii=False, indent=2)
            print("✓ Backup created at monsters.json.backup")
        else:
            print("⚠️  No existing monsters.json found - nothing to preview")
            return
    else:
        print("Using existing backup: monsters.json.backup")

    print()

    # Load old and new data
    print("Loading data files...")
    with open(OLD_MONSTERS_JSON, encoding="utf-8") as f:
        old_monsters = json.load(f)

    try:
        with open(NEW_MONSTERS_JSON, encoding="utf-8") as f:
            new_monsters = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: {NEW_MONSTERS_JSON} not found!")
        print("Run transformation scripts first.")
        return

    print(f"✓ Old data: {len(old_monsters)} monsters")
    print(f"✓ New data: {len(new_monsters)} monsters")
    print()

    # Build lookup maps
    old_map = {(m['name'], m['form']): m for m in old_monsters}
    new_map = {(m['name'], m['form']): m for m in new_monsters}

    old_keys = set(old_map.keys())
    new_keys = set(new_map.keys())

    # Categorize changes
    to_add = new_keys - old_keys
    to_remove = old_keys - new_keys
    to_update = old_keys & new_keys

    # Analyze updates
    updates_with_changes = []
    for key in to_update:
        old_monster = old_map[key]
        new_monster = new_map[key]

        # Check for any differences
        stat_changes = compare_stats(old_monster, new_monster)
        type_changes = (
            old_monster.get('main_type') != new_monster.get('main_type') or
            old_monster.get('sub_type') != new_monster.get('sub_type')
        )
        trait_changes = old_monster.get('trait') != new_monster.get('trait')
        moveset_changes = old_monster.get('moveset_key') != new_monster.get('moveset_key')

        if stat_changes or type_changes or trait_changes or moveset_changes:
            updates_with_changes.append({
                'key': key,
                'old': old_monster,
                'new': new_monster,
                'stat_changes': stat_changes,
                'type_changes': type_changes,
                'trait_changes': trait_changes,
                'moveset_changes': moveset_changes
            })

    # Display summary
    print("=" * 70)
    print("IMPORT PREVIEW SUMMARY")
    print("=" * 70)
    print()
    print(f"Monsters to ADD:        {len(to_add)}")
    print(f"Monsters to REMOVE:     {len(to_remove)}")
    print(f"Monsters to UPDATE:     {len(to_update)}")
    print(f"  (with changes):       {len(updates_with_changes)}")
    print(f"  (no changes):         {len(to_update) - len(updates_with_changes)}")
    print()

    # Show monsters to add
    if to_add:
        print("=" * 70)
        print(f"MONSTERS TO ADD ({len(to_add)}):")
        print("=" * 70)
        for idx, key in enumerate(sorted(to_add), 1):
            name, form = key
            monster = new_map[key]
            zh_name = monster['localized']['zh']['name']
            print(f"  {idx}. {name} ({zh_name}) - {form}")
            if detailed and idx <= 20:
                print(f"     Types: {monster.get('main_type')}/{monster.get('sub_type')}")
                print(f"     Trait: {monster.get('trait')}")
                print(f"     Stats: HP={monster.get('base_hp')} ATK={monster.get('base_phy_atk')}/{monster.get('base_mag_atk')}")
                print()
        if len(to_add) > 20 and detailed:
            print(f"  ... and {len(to_add) - 20} more (use --detailed to see all)")
        print()

    # Show monsters to remove
    if to_remove:
        print("=" * 70)
        print(f"MONSTERS TO REMOVE ({len(to_remove)}):")
        print("=" * 70)
        for idx, key in enumerate(sorted(to_remove), 1):
            name, form = key
            print(f"  {idx}. {name} - {form}")
        print()

    # Show monsters with changes
    if updates_with_changes:
        print("=" * 70)
        print(f"MONSTERS WITH CHANGES ({len(updates_with_changes)}):")
        print("=" * 70)
        for idx, update in enumerate(updates_with_changes[:20], 1):
            name, form = update['key']
            print(f"  {idx}. {name} - {form}")

            if detailed:
                if update['stat_changes']:
                    print(f"     Stat changes:")
                    for stat, change in update['stat_changes'].items():
                        print(f"       {stat}: {change['old']} → {change['new']}")

                if update['type_changes']:
                    old_types = f"{update['old'].get('main_type')}/{update['old'].get('sub_type')}"
                    new_types = f"{update['new'].get('main_type')}/{update['new'].get('sub_type')}"
                    print(f"     Types: {old_types} → {new_types}")

                if update['trait_changes']:
                    print(f"     Trait: {update['old'].get('trait')} → {update['new'].get('trait')}")

                if update['moveset_changes']:
                    print(f"     Moveset key: {update['old'].get('moveset_key')} → {update['new'].get('moveset_key')}")

                print()

        if len(updates_with_changes) > 20:
            print(f"  ... and {len(updates_with_changes) - 20} more (use --detailed to see all)")
        print()

    # Species preview
    if OLD_SPECIES_JSON.exists() and NEW_SPECIES_JSON.exists():
        with open(OLD_SPECIES_JSON, encoding="utf-8") as f:
            old_species = json.load(f)
        with open(NEW_SPECIES_JSON, encoding="utf-8") as f:
            new_species = json.load(f)

        old_species_names = {s['name'] for s in old_species}
        new_species_names = {s['name'] for s in new_species}

        new_species_to_add = new_species_names - old_species_names

        if new_species_to_add:
            print("=" * 70)
            print(f"NEW SPECIES TO ADD ({len(new_species_to_add)}):")
            print("=" * 70)
            for idx, species_name in enumerate(sorted(new_species_to_add)[:20], 1):
                species = next(s for s in new_species if s['name'] == species_name)
                zh_name = species['localized']['zh']
                print(f"  {idx}. {species_name} ({zh_name})")

            if len(new_species_to_add) > 20:
                print(f"  ... and {len(new_species_to_add) - 20} more")
            print()

    # Final message
    print("=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print()
    print("1. Review the changes above carefully")
    print("2. If everything looks good, proceed with database import:")
    print("   python3 -m backend.scripts.reset_and_reimport")
    print()
    print("3. Or run individual import scripts:")
    print("   python3 -m backend.scripts.import_monster_species")
    print("   python3 -m backend.scripts.import_monsters")
    print("   python3 -m backend.scripts.import_monster_moves")
    print("   python3 -m backend.scripts.import_legacy_moves")
    print()
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Generate import preview showing what will change"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed changes for each monster"
    )

    args = parser.parse_args()
    generate_preview(detailed=args.detailed)


if __name__ == "__main__":
    main()
