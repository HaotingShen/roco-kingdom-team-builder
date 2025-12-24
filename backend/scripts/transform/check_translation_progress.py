"""
Helper: Check Monster Name Translation Progress

This script shows how many monster names have been translated in the
monster_name_mapping.json file and which ones still need translation.

Usage:
    python3 -m backend.scripts.check_translation_progress
    python3 -m backend.scripts.check_translation_progress --show-missing
"""

import json
from pathlib import Path
import argparse

# File paths
BACKEND_DIR = Path(__file__).parent.parent.parent
MAPPING_JSON = BACKEND_DIR / "data" / "monster_name_mapping.json"


def check_progress(show_missing=False):
    """
    Check translation progress in monster_name_mapping.json.

    Args:
        show_missing: If True, print all Chinese names that need translation
    """
    print("=" * 70)
    print("Monster Name Translation Progress")
    print("=" * 70)
    print()

    # Load mapping file
    try:
        with open(MAPPING_JSON, encoding="utf-8") as f:
            mapping = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: {MAPPING_JSON} not found!")
        print("Please run generate_monster_name_template.py first.")
        return

    # Count translated vs missing
    total = len(mapping)
    translated = sum(1 for v in mapping.values() if v)
    missing = total - translated
    percentage = (translated / total * 100) if total > 0 else 0

    # Display statistics
    print(f"Total monsters:          {total}")
    print(f"Translated:              {translated}")
    print(f"Still need translation:  {missing}")
    print(f"Progress:                {percentage:.1f}%")
    print()

    # Progress bar
    bar_width = 50
    filled = int(bar_width * translated / total) if total > 0 else 0
    bar = "█" * filled + "░" * (bar_width - filled)
    print(f"[{bar}] {percentage:.1f}%")
    print()

    # Show missing entries if requested
    if show_missing and missing > 0:
        print("=" * 70)
        print(f"Entries that need translation ({missing}):")
        print("=" * 70)
        print()

        for chinese_name, english_name in mapping.items():
            if not english_name:
                print(f"  \"{chinese_name}\": \"\"")

        print()

    # Status message
    if missing == 0:
        print("✅ All monster names have been translated!")
        print("You can now proceed to Phase 3: transform_monsters_to_english.py")
    else:
        print(f"⚠️  {missing} monster name(s) still need translation")
        print(f"Edit {MAPPING_JSON} to add English names")
        print()
        print("TIP: Use --show-missing flag to see all untranslated names")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Check monster name translation progress"
    )
    parser.add_argument(
        "--show-missing",
        action="store_true",
        help="Show all Chinese names that still need translation"
    )

    args = parser.parse_args()
    check_progress(show_missing=args.show_missing)


if __name__ == "__main__":
    main()
