"""
Detect Name Changes in Monster Mapping

This script compares monster_name_mapping.json with existing monsters.json
to identify which English names were changed.

Usage:
    python3 -m backend.scripts.detect_name_changes
"""

import json
from pathlib import Path
from collections import defaultdict

# File paths
BACKEND_DIR = Path(__file__).parent.parent.parent
MAPPING_JSON = BACKEND_DIR / "data" / "monster_name_mapping.json"
MONSTERS_JSON = BACKEND_DIR / "data" / "monsters.json"


def detect_changes():
    """Compare mapping file with existing monsters.json to find changes."""
    print("=" * 70)
    print("Detecting Name Changes in Monster Mapping")
    print("=" * 70)
    print()

    # Load mapping file
    try:
        with open(MAPPING_JSON, encoding="utf-8") as f:
            mapping = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: {MAPPING_JSON} not found!")
        return

    # Load existing monsters.json
    try:
        with open(MONSTERS_JSON, encoding="utf-8") as f:
            monsters = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: {MONSTERS_JSON} not found!")
        print("This means all names in mapping are NEW (no existing data).")
        return

    print(f"✓ Loaded {len(mapping)} names from mapping file")
    print(f"✓ Loaded {len(monsters)} monsters from monsters.json")
    print()

    # Build lookup: Chinese name → existing English name
    existing_names = {}
    for monster in monsters:
        zh_name = monster.get("localized", {}).get("zh", {}).get("name")
        if zh_name:
            existing_names[zh_name] = monster["name"]

    # Compare and categorize
    changed = []
    unchanged = []
    new_monsters = []

    for zh_name, new_en_name in mapping.items():
        if not new_en_name:
            # Skip untranslated
            continue

        if zh_name in existing_names:
            old_en_name = existing_names[zh_name]
            if old_en_name != new_en_name:
                changed.append({
                    "zh": zh_name,
                    "old": old_en_name,
                    "new": new_en_name
                })
            else:
                unchanged.append(zh_name)
        else:
            new_monsters.append({
                "zh": zh_name,
                "new": new_en_name
            })

    # Display results
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print()
    print(f"✅ Unchanged names:     {len(unchanged)}")
    print(f"⚠️  CHANGED names:       {len(changed)}")
    print(f"🆕 NEW monsters:        {len(new_monsters)}")
    print()

    if changed:
        print("=" * 70)
        print(f"⚠️  NAMES THAT WERE CHANGED ({len(changed)}):")
        print("=" * 70)
        print()
        print("These will create DUPLICATE monsters if you proceed with import!")
        print()
        for i, item in enumerate(changed, 1):
            print(f"{i:3}. {item['zh']}")
            print(f"     Old: {item['old']}")
            print(f"     New: {item['new']}")
            print()

    if new_monsters and len(new_monsters) <= 20:
        print("=" * 70)
        print(f"🆕 NEW MONSTERS ({len(new_monsters)}):")
        print("=" * 70)
        print()
        for i, item in enumerate(new_monsters, 1):
            print(f"{i:3}. {item['zh']} → {item['new']}")
        print()
    elif new_monsters:
        print(f"(🆕 {len(new_monsters)} new monsters - too many to display)")
        print()

    # Provide recommendations
    print("=" * 70)
    print("RECOMMENDATIONS")
    print("=" * 70)
    print()

    if changed:
        print("⚠️  You have CHANGED names! Choose one option:")
        print()
        print("Option 1: REVERT the changes (recommended if names were good)")
        print("  - Run: python3 -m backend.scripts.revert_name_changes")
        print("  - This will restore old English names in the mapping file")
        print()
        print("Option 2: KEEP the changes and update database")
        print("  - Run: python3 -m backend.scripts.apply_name_changes")
        print("  - This will UPDATE database to use new names (safe, no duplicates)")
        print()
        print("Option 3: FRESH START (⚠️  deletes all saved teams!)")
        print("  - Run: python3 -m backend.scripts.reset_and_reimport")
        print("  - Only use if you don't have important saved teams")
        print()
    else:
        print("✅ No name changes detected!")
        print("   You can safely proceed with the transformation:")
        print()
        print("   python3 -m backend.scripts.check_translation_progress")
        print("   python3 -m backend.scripts.transform_monsters_to_english")
        print("   # ... continue with other scripts")
        print()

    print("=" * 70)

    return {
        "changed": changed,
        "unchanged_count": len(unchanged),
        "new_count": len(new_monsters)
    }


def main():
    detect_changes()


if __name__ == "__main__":
    main()
