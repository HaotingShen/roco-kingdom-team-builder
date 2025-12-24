#!/usr/bin/env python3
"""
Generate move name mapping file (Chinese -> English) from moves.json.
This mapping file can be used to quickly update English names in moves.json.

Output: backend/data/move_name_mapping.json
"""
import json
from pathlib import Path
from typing import Dict

# File paths
MOVES_JSON = Path("backend/data/moves.json")
OUTPUT_FILE = Path("backend/data/move_name_mapping.json")


def load_moves() -> list:
    """Load moves from moves.json."""
    try:
        with open(MOVES_JSON, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: moves.json not found at {MOVES_JSON}")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in moves.json")
        print(f"   {e}")
        exit(1)


def generate_move_name_mapping(moves: list) -> Dict[str, str]:
    """
    Generate mapping of Chinese move names to English move names.

    Args:
        moves: List of move dictionaries from moves.json

    Returns:
        Dictionary mapping {chinese_name: english_name}
    """
    mapping = {}
    duplicates = []
    missing_chinese = []
    missing_english = []

    for i, move in enumerate(moves, 1):
        english_name = move.get('name', '')
        chinese_name = move.get('localized', {}).get('zh', {}).get('name', '')

        # Check for missing names
        if not english_name:
            missing_english.append(f"Move #{i}: Missing English name")

        if not chinese_name:
            missing_chinese.append(f"Move #{i} ({english_name}): Missing Chinese name")
            continue

        # Check for duplicates
        if chinese_name in mapping:
            duplicates.append(f"{chinese_name}: '{mapping[chinese_name]}' vs '{english_name}'")

        # Add to mapping
        mapping[chinese_name] = english_name

    # Report issues
    if missing_english:
        print(f"⚠️  Warning: {len(missing_english)} moves missing English names:")
        for msg in missing_english[:5]:
            print(f"   - {msg}")
        if len(missing_english) > 5:
            print(f"   ... and {len(missing_english) - 5} more")
        print()

    if missing_chinese:
        print(f"⚠️  Warning: {len(missing_chinese)} moves missing Chinese names:")
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
    """Save mapping to JSON file with pretty formatting."""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False, sort_keys=True)
        print(f"✅ Saved mapping to: {output_path}")
    except Exception as e:
        print(f"❌ Error saving mapping file: {e}")
        exit(1)


def main():
    """Generate move name mapping file."""
    print("=" * 80)
    print("GENERATE MOVE NAME MAPPING")
    print("=" * 80)
    print()

    # Load moves
    print(f"📖 Loading moves from: {MOVES_JSON}")
    moves = load_moves()
    print(f"   Found {len(moves)} moves")
    print()

    # Generate mapping
    print("🔄 Generating name mapping...")
    mapping = generate_move_name_mapping(moves)
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
    print(f"Total moves in moves.json: {len(moves)}")
    print(f"Total mappings created: {len(mapping)}")
    print(f"Output file: {OUTPUT_FILE}")
    print()
    print("✅ Move name mapping file generated successfully!")
    print()
    print("Usage:")
    print("  - Edit move_name_mapping.json to update English names")
    print("  - Use apply_move_name_changes.py to apply changes back to moves.json")
    print()


if __name__ == "__main__":
    main()
