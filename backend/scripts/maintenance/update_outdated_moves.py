#!/usr/bin/env python3
"""
Auto-update outdated moves in moves.json using data from moves_all.json.
Updates Chinese descriptions, power, category, and energy cost.
Preserves English names, English descriptions, and has_counter values.
"""
import json
from pathlib import Path
from typing import Dict, List

# File paths
MOVES_ALL_PATH = Path("backend/data/moves_all.json")
MOVES_PATH = Path("backend/data/moves.json")
BACKUP_PATH = Path("backend/data/moves.json.backup")

# Category mappings
CATEGORY_MAP = {
    "物攻": "Physical Attack",
    "魔攻": "Magic Attack",
    "防御": "Defense",
    "状态": "Status"
}

# Type mappings (both abbreviated and full Chinese names)
TYPE_MAP = {
    "龙": "Dragon",
    "火": "Fire",
    "水": "Water",
    "草": "Grass",
    "电": "Electric",
    "冰": "Ice",
    "地": "Ground",
    "翼": "Flying",
    "虫": "Bug",
    "毒": "Poison",
    "武": "Fighting",
    "普通": "Normal",
    "萌": "Cute",
    "幽": "Ghost",
    "光": "Light",
    "恶": "Dark",
    "机械": "Mechanical",
    "幻": "Illusion",
    "首": "Leader"
}

def load_json(path: Path) -> List[dict]:
    """Load JSON file."""
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def save_json(path: Path, data: List[dict]):
    """Save JSON file."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_chinese_name(move: dict) -> str:
    """Extract Chinese name from move data."""
    if 'localized' not in move:
        return move['name']
    return move.get('localized', {}).get('zh', {}).get('name', '')

def normalize_description(desc: str) -> str:
    """
    Normalize description from moves_all.json.
    Ensures Chinese period at end (already uses Chinese punctuation).
    """
    if not desc:
        return ''

    # Ensure Chinese period at end
    if desc and not desc.endswith('。'):
        desc = desc + '。'

    return desc

def normalize_power(power) -> int | None:
    """Normalize power value."""
    if power is None or power == '' or power == '--':
        return None
    try:
        return int(power)
    except (ValueError, TypeError):
        return None

def update_outdated_moves(auto_confirm: bool = False):
    """Update outdated moves in moves.json."""
    # Load data
    moves_all = load_json(MOVES_ALL_PATH)
    moves = load_json(MOVES_PATH)

    # Build lookup by Chinese name
    moves_all_map = {get_chinese_name(m): m for m in moves_all}

    # Track changes
    updated_count = 0
    changes_log = []

    # Update outdated moves
    for move in moves:
        zh_name = get_chinese_name(move)

        if zh_name not in moves_all_map:
            continue  # Extra move, skip

        move_all = moves_all_map[zh_name]
        updated = False
        move_changes = []

        # Update Chinese description (with normalization)
        new_desc_zh = normalize_description(move_all.get('description', ''))
        current_desc_zh = move.get('localized', {}).get('zh', {}).get('description', '')
        if new_desc_zh != current_desc_zh:
            if 'localized' not in move:
                move['localized'] = {}
            if 'zh' not in move['localized']:
                move['localized']['zh'] = {}
            move['localized']['zh']['description'] = new_desc_zh
            updated = True
            move_changes.append(f"Description updated")

        # Update power
        new_power = normalize_power(move_all.get('power'))
        current_power = normalize_power(move.get('power'))
        if new_power != current_power:
            move['power'] = new_power
            updated = True
            move_changes.append(f"Power: {current_power} → {new_power}")

        # Update category
        new_category = CATEGORY_MAP.get(move_all.get('category', ''), move_all.get('category', ''))
        current_category = move.get('category', '')
        if new_category != current_category:
            move['category'] = new_category
            updated = True
            move_changes.append(f"Category: {current_category} → {new_category}")

        # Update energy cost
        new_energy = int(move_all.get('energy_consumption', 0))
        current_energy = move.get('energy_cost', 0)
        if new_energy != current_energy:
            move['energy_cost'] = new_energy
            updated = True
            move_changes.append(f"Energy: {current_energy} → {new_energy}")

        # Update type
        new_type = TYPE_MAP.get(move_all.get('attribute', ''), move_all.get('attribute'))
        current_type = move.get('type')
        if new_type and new_type != current_type:
            move['type'] = new_type if new_type != '' else None
            updated = True
            move_changes.append(f"Type: {current_type} → {new_type}")

        if updated:
            updated_count += 1
            changes_log.append({
                'chinese_name': zh_name,
                'english_name': move.get('name', ''),
                'changes': move_changes
            })

    # Show summary
    print("=" * 80)
    print("📊 UPDATE SUMMARY")
    print("=" * 80)
    print(f"Total moves to update: {updated_count}")
    print()

    if updated_count == 0:
        print("✅ No updates needed. All moves are up to date!")
        return

    # Show some examples
    print("Sample changes:")
    for i, change in enumerate(changes_log[:5], 1):
        print(f"{i}. {change['chinese_name']} ({change['english_name']})")
        for diff in change['changes']:
            print(f"   - {diff}")

    if len(changes_log) > 5:
        print(f"   ... and {len(changes_log) - 5} more")
    print()

    # Confirm
    if not auto_confirm:
        print("⚠️  This will update moves.json with data from moves_all.json")
        print("   English names, descriptions, and has_counter will be preserved")
        print()
        response = input("Continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            return

    # Backup
    print()
    print(f"💾 Creating backup: {BACKUP_PATH}")
    save_json(BACKUP_PATH, load_json(MOVES_PATH))

    # Save updated moves
    print(f"💾 Saving updated moves to: {MOVES_PATH}")
    save_json(MOVES_PATH, moves)

    # Save change log
    log_path = Path("backend/data/move_reports/update_log.json")
    save_json(log_path, changes_log)

    print()
    print("=" * 80)
    print("✅ UPDATE COMPLETE")
    print("=" * 80)
    print(f"Updated {updated_count} moves")
    print(f"Backup saved to: {BACKUP_PATH}")
    print(f"Change log saved to: {log_path}")
    print()
    print("Next steps:")
    print("1. Review the changes in moves.json")
    print("2. If everything looks good, re-import moves:")
    print("   python3 -m backend.scripts.import_moves")
    print()

if __name__ == "__main__":
    import sys
    auto_confirm = '--yes' in sys.argv or '-y' in sys.argv
    update_outdated_moves(auto_confirm=auto_confirm)
