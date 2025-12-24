"""
Check for Duplicate English Names in Mapping

This script detects when multiple Chinese names map to the same English name,
which would cause data loss during import.

Usage:
    python3 -m backend.scripts.transform.check_duplicate_names
"""

import json
from pathlib import Path
from collections import defaultdict

# File paths
BACKEND_DIR = Path(__file__).parent.parent.parent
MAPPING_JSON = BACKEND_DIR / "data" / "monster_name_mapping.json"


def check_duplicates():
    """Check for duplicate English names in mapping."""
    print("=" * 70)
    print("Checking for Duplicate English Names")
    print("=" * 70)
    print()

    # Load mapping
    try:
        with open(MAPPING_JSON, encoding="utf-8") as f:
            mapping = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: {MAPPING_JSON} not found!")
        return

    # Group Chinese names by English name
    en_to_zh = defaultdict(list)
    for zh_name, en_name in mapping.items():
        if en_name:  # Skip untranslated
            en_to_zh[en_name].append(zh_name)

    # Find duplicates
    duplicates = {en: zh_list for en, zh_list in en_to_zh.items() if len(zh_list) > 1}

    if not duplicates:
        print("✅ No duplicate English names found!")
        print("   All English names are unique.")
        print()
        return

    # Display duplicates
    print(f"❌ Found {len(duplicates)} English names used for multiple monsters:")
    print()
    print("⚠️  WARNING: These will cause DATA LOSS during import!")
    print("   The last monster in the list will overwrite the others.")
    print()

    for idx, (en_name, zh_list) in enumerate(sorted(duplicates.items()), 1):
        print(f"{idx}. English name: \"{en_name}\" is used for {len(zh_list)} monsters:")
        for zh_name in zh_list:
            print(f"   - {zh_name}")
        print()

    # Summary
    print("=" * 70)
    print("ACTION REQUIRED")
    print("=" * 70)
    print()
    print("You MUST fix these duplicates before running transform_monsters_to_english!")
    print()
    print("Options:")
    print("1. Give each monster a unique English name:")
    print('   "小星光": "Starlite"')
    print('   "小星光星光能量的样子": "Starlite Charged"  ← Make unique')
    print()
    print("2. Or use different forms if they're variants:")
    print('   In monsters_all.json, set different "form" values')
    print()
    print("=" * 70)


def main():
    check_duplicates()


if __name__ == "__main__":
    main()
