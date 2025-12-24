#!/usr/bin/env python3
"""
Apply move name changes from move_name_mapping.json back to moves.json.
Allows you to quickly update English move names by editing the mapping file.

Workflow:
  1. Generate mapping: python3 -m backend.scripts.name_management.generate_move_name_mapping
  2. Edit move_name_mapping.json with new English names
  3. Apply changes: python3 -m backend.scripts.name_management.apply_move_name_changes
"""
import json
from pathlib import Path
from typing import Dict, List

# File paths
MOVES_JSON = Path("backend/data/moves.json")
MAPPING_FILE = Path("backend/data/move_name_mapping.json")
BACKUP_FILE = Path("backend/data/moves.json.backup_name_changes")


def load_json(path: Path) -> any:
    """Load JSON file."""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: File not found: {path}")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {path}")
        print(f"   {e}")
        exit(1)


def save_json(data: any, path: Path):
    """Save data to JSON file with pretty formatting."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved to: {path}")
    except Exception as e:
        print(f"❌ Error saving file: {e}")
        exit(1)


def create_backup(source: Path, backup: Path):
    """Create backup of source file."""
    try:
        import shutil
        shutil.copy2(source, backup)
        print(f"💾 Backup created: {backup}")
    except Exception as e:
        print(f"❌ Error creating backup: {e}")
        exit(1)


def apply_name_changes(moves: List[dict], mapping: Dict[str, str]) -> tuple:
    """
    Apply name changes from mapping to moves.

    Args:
        moves: List of move dictionaries from moves.json
        mapping: Dictionary mapping {chinese_name: new_english_name}

    Returns:
        (updated_moves, changes_count, changes_list)
    """
    changes = []
    not_found = []

    for move in moves:
        chinese_name = move.get('localized', {}).get('zh', {}).get('name', '')
        current_english = move.get('name', '')

        if not chinese_name:
            continue

        if chinese_name not in mapping:
            not_found.append(f"{chinese_name} ({current_english})")
            continue

        new_english = mapping[chinese_name]

        # Check if name actually changed
        if current_english != new_english:
            changes.append({
                'chinese_name': chinese_name,
                'old_english': current_english,
                'new_english': new_english
            })
            # Update the move
            move['name'] = new_english

    # Report not found
    if not_found:
        print(f"⚠️  Warning: {len(not_found)} moves in moves.json not found in mapping:")
        for msg in not_found[:5]:
            print(f"   - {msg}")
        if len(not_found) > 5:
            print(f"   ... and {len(not_found) - 5} more")
        print()

    return moves, len(changes), changes


def main():
    """Apply move name changes from mapping file."""
    print("=" * 80)
    print("APPLY MOVE NAME CHANGES")
    print("=" * 80)
    print()

    # Load mapping
    print(f"📖 Loading mapping from: {MAPPING_FILE}")
    mapping = load_json(MAPPING_FILE)
    print(f"   Found {len(mapping)} mappings")
    print()

    # Load moves
    print(f"📖 Loading moves from: {MOVES_JSON}")
    moves = load_json(MOVES_JSON)
    print(f"   Found {len(moves)} moves")
    print()

    # Apply changes
    print("🔄 Applying name changes...")
    updated_moves, changes_count, changes = apply_name_changes(moves, mapping)
    print(f"   {changes_count} changes detected")
    print()

    if changes_count == 0:
        print("✅ No changes needed. All names are already up to date!")
        print()
        return

    # Show changes
    print(f"📋 Changes to be applied ({changes_count} moves):")
    print("=" * 80)
    for i, change in enumerate(changes[:10], 1):
        print(f"{i}. {change['chinese_name']}")
        print(f"   Old: {change['old_english']}")
        print(f"   New: {change['new_english']}")
    if len(changes) > 10:
        print(f"... and {len(changes) - 10} more changes")
    print()

    # Confirm
    response = input("Apply these changes to moves.json? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Aborted. No changes were made.")
        return

    print()

    # Create backup
    print(f"💾 Creating backup...")
    create_backup(MOVES_JSON, BACKUP_FILE)
    print()

    # Save updated moves
    print(f"💾 Saving updated moves to: {MOVES_JSON}")
    save_json(updated_moves, MOVES_JSON)
    print()

    # Save change log
    log_file = Path("backend/data/move_name_changes_log.json")
    print(f"📋 Saving change log to: {log_file}")
    save_json(changes, log_file)
    print()

    # Summary
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print(f"Total moves processed: {len(moves)}")
    print(f"Names updated: {changes_count}")
    print(f"Backup saved to: {BACKUP_FILE}")
    print(f"Change log saved to: {log_file}")
    print()
    print("✅ Move names updated successfully!")
    print()


if __name__ == "__main__":
    main()
