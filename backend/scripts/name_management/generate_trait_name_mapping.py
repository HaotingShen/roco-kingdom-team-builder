#!/usr/bin/env python3
"""
Generate trait name mapping file (Chinese -> English) from traits.json.
This mapping file can be used to quickly update English names in traits.json.

Output: backend/data/trait_name_mapping.json
"""
import json
from pathlib import Path
from typing import Dict

# File paths
TRAITS_JSON = Path("backend/data/traits.json")
OUTPUT_FILE = Path("backend/data/trait_name_mapping.json")


def load_traits() -> list:
    """Load traits from traits.json."""
    try:
        with open(TRAITS_JSON, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: traits.json not found at {TRAITS_JSON}")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in traits.json")
        print(f"   {e}")
        exit(1)


def generate_trait_name_mapping(traits: list) -> Dict[str, str]:
    """
    Generate mapping of Chinese trait names to English trait names.

    Args:
        traits: List of trait dictionaries from traits.json

    Returns:
        Dictionary mapping {chinese_name: english_name}
    """
    mapping = {}
    duplicates = []
    missing_chinese = []
    missing_english = []

    for i, trait in enumerate(traits, 1):
        english_name = trait.get('name', '')
        chinese_name = trait.get('localized', {}).get('zh', {}).get('name', '')

        # Check for missing names
        if not english_name:
            missing_english.append(f"Trait #{i}: Missing English name")

        if not chinese_name:
            missing_chinese.append(f"Trait #{i} ({english_name}): Missing Chinese name")
            continue

        # Check for duplicates
        if chinese_name in mapping:
            duplicates.append(f"{chinese_name}: '{mapping[chinese_name]}' vs '{english_name}'")

        # Add to mapping
        mapping[chinese_name] = english_name

    # Report issues
    if missing_english:
        print(f"⚠️  Warning: {len(missing_english)} traits missing English names:")
        for msg in missing_english[:5]:
            print(f"   - {msg}")
        if len(missing_english) > 5:
            print(f"   ... and {len(missing_english) - 5} more")
        print()

    if missing_chinese:
        print(f"⚠️  Warning: {len(missing_chinese)} traits missing Chinese names:")
        for msg in missing_chinese[:5]:
            print(f"   - {msg}")
        if len(missing_chinese) > 5:
            print(f"   ... and {len(missing_chinese) - 5} more")
        print()

    if duplicates:
        print(f"⚠️  Warning: {len(duplicates)} duplicate Chinese names (keeping last):")
        for msg in duplicates[:5]:
            print(f"   - {msg}")
        if len(duplicates) > 5:
            print(f"   ... and {len(duplicates) - 5} more")
        print()

    return mapping


def save_mapping(mapping: Dict[str, str], output_path: Path):
    """Save mapping to JSON file with pretty formatting (preserves insertion order)."""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False, sort_keys=False)
        print(f"✅ Saved mapping to: {output_path}")
    except Exception as e:
        print(f"❌ Error saving mapping file: {e}")
        exit(1)


def main():
    """Generate trait name mapping file."""
    print("=" * 80)
    print("GENERATE TRAIT NAME MAPPING")
    print("=" * 80)
    print()

    # Load traits
    print(f"📖 Loading traits from: {TRAITS_JSON}")
    traits = load_traits()
    print(f"   Found {len(traits)} traits")
    print()

    # Generate mapping
    print("🔄 Generating name mapping...")
    mapping = generate_trait_name_mapping(traits)
    print(f"   Created {len(mapping)} mappings")
    print()

    # Save mapping
    print(f"💾 Saving to: {OUTPUT_FILE}")
    save_mapping(mapping, OUTPUT_FILE)
    print()

    # Summary
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print(f"Total traits in traits.json: {len(traits)}")
    print(f"Total mappings created: {len(mapping)}")
    print(f"Output file: {OUTPUT_FILE}")
    print()
    print("✅ Trait name mapping file generated successfully!")
    print()
    print("Usage:")
    print("  - Edit trait_name_mapping.json to update English names")
    print("  - Create apply_trait_name_changes.py (similar to apply_move_name_changes.py)")
    print("  - Use it to apply changes back to traits.json")
    print()


if __name__ == "__main__":
    main()
