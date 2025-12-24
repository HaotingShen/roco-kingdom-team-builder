"""
Phase 1: Generate Monster Name Translation Template

This script creates a mapping file (monster_name_mapping.json) that contains:
- Pre-filled Chinese→English name pairs from existing monsters.json
- Empty entries for new monsters that need manual translation

Usage:
    python3 -m backend.scripts.generate_monster_name_template
"""

import json
from pathlib import Path
from collections import OrderedDict

# File paths
BACKEND_DIR = Path(__file__).parent.parent.parent
MONSTERS_JSON = BACKEND_DIR / "data" / "monsters.json"
MONSTERS_ALL_JSON = BACKEND_DIR / "data" / "monsters_all.json"
OUTPUT_JSON = BACKEND_DIR / "data" / "monster_name_mapping.json"


def extract_existing_translations():
    """
    Extract Chinese→English name pairs from current monsters.json.
    Returns a dict mapping Chinese names to English names.
    """
    with open(MONSTERS_JSON, encoding="utf-8") as f:
        monsters = json.load(f)

    mapping = {}
    for monster in monsters:
        english_name = monster["name"]
        localized = monster.get("localized", {})
        zh_data = localized.get("zh", {})
        chinese_name = zh_data.get("name")

        if chinese_name:
            mapping[chinese_name] = english_name

    return mapping


def collect_all_chinese_names():
    """
    Collect all unique Chinese monster names from monsters_all.json.
    Returns a list of Chinese names in order of appearance.
    """
    with open(MONSTERS_ALL_JSON, encoding="utf-8") as f:
        monsters_all = json.load(f)

    # Use OrderedDict to preserve order while removing duplicates
    seen = OrderedDict()
    for monster in monsters_all:
        chinese_name = monster["name"]
        if chinese_name not in seen:
            seen[chinese_name] = None

    return list(seen.keys())


def generate_template():
    """
    Generate the monster name translation template.
    Pre-fills existing translations and leaves empty entries for new monsters.
    """
    print("=" * 70)
    print("Phase 1: Generating Monster Name Translation Template")
    print("=" * 70)
    print()

    # Step 1: Extract existing translations
    print("Step 1: Reading existing translations from monsters.json...")
    existing_mapping = extract_existing_translations()
    print(f"✓ Found {len(existing_mapping)} existing translations")
    print()

    # Step 2: Collect all Chinese names from source
    print("Step 2: Reading all Chinese names from monsters_all.json...")
    all_chinese_names = collect_all_chinese_names()
    print(f"✓ Found {len(all_chinese_names)} unique Chinese monster names")
    print()

    # Step 3: Build final mapping (preserve order from source file)
    print("Step 3: Building translation template...")
    template = OrderedDict()

    pre_filled_count = 0
    needs_translation_count = 0

    for chinese_name in all_chinese_names:
        if chinese_name in existing_mapping:
            # Pre-fill with existing translation
            template[chinese_name] = existing_mapping[chinese_name]
            pre_filled_count += 1
        else:
            # Empty entry - needs manual translation
            template[chinese_name] = ""
            needs_translation_count += 1

    print(f"✓ Pre-filled: {pre_filled_count} translations")
    print(f"✓ Need manual translation: {needs_translation_count} monsters")
    print()

    # Step 4: Save to file
    print(f"Step 4: Writing template to {OUTPUT_JSON}...")
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)
    print("✓ Template file created successfully!")
    print()

    # Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total monsters in source:     {len(all_chinese_names)}")
    print(f"Pre-filled translations:      {pre_filled_count}")
    print(f"Needs manual translation:     {needs_translation_count}")
    print()
    print(f"Output file: {OUTPUT_JSON}")
    print()
    print("NEXT STEP: Open the file and fill in empty strings with English names")
    print("Example entries that need translation:")
    print()

    # Show first 5 entries that need translation
    examples_shown = 0
    for chinese_name, english_name in template.items():
        if not english_name and examples_shown < 5:
            print(f"  \"{chinese_name}\": \"\"  ← needs translation")
            examples_shown += 1

    print()
    print("TIP: Use check_translation_progress.py to track completion status")
    print("=" * 70)


def main():
    generate_template()


if __name__ == "__main__":
    main()
