#!/usr/bin/env python3
"""
Compare moves.json with moves_all.json to identify differences.
Generates reports for missing moves, outdated moves, and extra moves.
"""
import json
from pathlib import Path
from typing import Dict, List, Tuple

# File paths
MOVES_ALL_PATH = Path("backend/data/moves_all.json")
MOVES_PATH = Path("backend/data/moves.json")
REPORTS_DIR = Path("backend/data/move_reports")

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

def get_chinese_name(move: dict) -> str:
    """Extract Chinese name from move data."""
    # For moves_all.json: name is directly in Chinese
    if 'localized' not in move:
        return move['name']
    # For moves.json: Chinese name is in localized.zh.name
    return move.get('localized', {}).get('zh', {}).get('name', '')

def normalize_description(desc: str, from_moves_all: bool = False) -> str:
    """
    Normalize description for comparison.
    Both files now use Chinese punctuation, just need to ensure period at end.

    Args:
        desc: Description text
        from_moves_all: True if from moves_all.json (needs period check)

    Returns:
        Normalized description
    """
    if not desc:
        return ''

    if from_moves_all:
        # Ensure Chinese period at end (moves_all.json might be missing it)
        if desc and not desc.endswith('。'):
            desc = desc + '。'

    return desc

def get_chinese_description(move: dict) -> str:
    """Extract Chinese description from move data."""
    # For moves_all.json: description is directly in Chinese
    if 'localized' not in move:
        desc = move.get('description', '')
        return normalize_description(desc, from_moves_all=True)
    # For moves.json: Chinese description is in localized.zh.description
    return move.get('localized', {}).get('zh', {}).get('description', '')

def normalize_power(power) -> str:
    """Normalize power value for comparison."""
    if power is None or power == '' or power == '--':
        return '--'
    return str(power)

def display_power(power) -> str:
    """
    Format power value for display in reports.
    Shows 'null' for all non-numeric values (None, '', '--')
    since that's what will be written to the JSON file.
    """
    if power is None or power == '' or power == '--':
        return 'null'
    return str(power)

def normalize_category(category: str, is_chinese: bool = True) -> str:
    """Normalize category for comparison."""
    if is_chinese:
        return CATEGORY_MAP.get(category, category)
    return category

def compare_moves() -> Tuple[List[dict], List[dict], List[dict]]:
    """
    Compare moves_all.json with moves.json.

    Returns:
        (missing_moves, outdated_moves, extra_moves)
    """
    moves_all = load_json(MOVES_ALL_PATH)
    moves = load_json(MOVES_PATH)

    # Build lookup by Chinese name
    moves_all_map = {get_chinese_name(m): m for m in moves_all}
    moves_map = {get_chinese_name(m): m for m in moves}

    # Find missing moves (in moves_all but not in moves)
    missing_moves = []
    for zh_name, move_all in moves_all_map.items():
        if zh_name not in moves_map:
            missing_moves.append({
                'chinese_name': zh_name,
                'type': TYPE_MAP.get(move_all.get('attribute', ''), move_all.get('attribute', 'Unknown')),
                'category': CATEGORY_MAP.get(move_all.get('category', ''), move_all.get('category', '')),
                'energy_cost': move_all.get('energy_consumption', ''),
                'power': display_power(move_all.get('power')),
                'description_zh': normalize_description(move_all.get('description', ''), from_moves_all=True),
                'source_id': move_all.get('id')
            })

    # Find outdated moves (different description, power, or category)
    # Maintain the order from moves.json for consistent output
    outdated_moves = []
    for move_current in moves:
        zh_name = get_chinese_name(move_current)
        if zh_name not in moves_all_map:
            continue  # Extra move, skip

        move_all = moves_all_map[zh_name]

        differences = []

        # Compare Chinese description (with normalization)
        desc_all = normalize_description(move_all.get('description', ''), from_moves_all=True)
        desc_current = get_chinese_description(move_current)
        if desc_all != desc_current:
            differences.append(f"Description: '{desc_current}' → '{desc_all}'")

        # Compare power
        power_all_normalized = normalize_power(move_all.get('power'))
        power_current_normalized = normalize_power(move_current.get('power'))
        if power_all_normalized != power_current_normalized:
            # Use display format in the difference message
            power_all_display = display_power(move_all.get('power'))
            power_current_display = display_power(move_current.get('power'))
            differences.append(f"Power: {power_current_display} → {power_all_display}")

        # Compare category
        category_all = normalize_category(move_all.get('category', ''), is_chinese=True)
        category_current = normalize_category(move_current.get('category', ''), is_chinese=False)
        if category_all != category_current:
            differences.append(f"Category: {category_current} → {category_all}")

        # Compare energy cost
        energy_all = str(move_all.get('energy_consumption', ''))
        energy_current = str(move_current.get('energy_cost', ''))
        if energy_all != energy_current:
            differences.append(f"Energy: {energy_current} → {energy_all}")

        # Compare type
        type_all = TYPE_MAP.get(move_all.get('attribute', ''), move_all.get('attribute', ''))
        type_current = move_current.get('type', '')
        if type_all and type_all != type_current:
            differences.append(f"Type: {type_current} → {type_all}")

        if differences:
            outdated_moves.append({
                'chinese_name': zh_name,
                'english_name': move_current.get('name', ''),
                'differences': differences,
                'current': {
                    'description_zh': desc_current,
                    'power': display_power(move_current.get('power')),
                    'category': category_current,
                    'energy_cost': energy_current,
                    'type': type_current
                },
                'new': {
                    'description_zh': desc_all,
                    'power': display_power(move_all.get('power')),
                    'category': category_all,
                    'energy_cost': energy_all,
                    'type': type_all
                }
            })

    # Find extra moves (in moves but not in moves_all)
    extra_moves = []
    for zh_name, move in moves_map.items():
        if zh_name not in moves_all_map:
            extra_moves.append({
                'chinese_name': zh_name,
                'english_name': move.get('name', ''),
                'type': move.get('type', ''),
                'category': move.get('category', ''),
                'energy_cost': move.get('energy_cost', ''),
                'power': display_power(move.get('power')),
                'description_en': move.get('description', ''),
                'description_zh': get_chinese_description(move)
            })

    return missing_moves, outdated_moves, extra_moves

def generate_reports():
    """Generate comparison reports."""
    # Create reports directory
    REPORTS_DIR.mkdir(exist_ok=True)

    print("🔍 Comparing moves.json with moves_all.json...")
    print()

    missing, outdated, extra = compare_moves()

    # Report 1: Missing moves
    print(f"📋 Report 1: Missing Moves ({len(missing)} moves)")
    print("=" * 80)
    if missing:
        with open(REPORTS_DIR / "missing_moves.txt", 'w', encoding='utf-8') as f:
            f.write("MISSING MOVES (in moves_all.json but not in moves.json)\n")
            f.write("=" * 80 + "\n\n")
            for i, move in enumerate(missing, 1):
                line = f"{i}. {move['chinese_name']}\n"
                line += f"   Type: {move['type']}\n"
                line += f"   Category: {move['category']}\n"
                line += f"   Energy: {move['energy_cost']}, Power: {move['power']}\n"
                line += f"   Description (ZH): {move['description_zh']}\n"
                line += f"   Source ID: {move['source_id']}\n\n"
                f.write(line)
                print(f"  {i}. {move['chinese_name']} ({move['category']}, Power: {move['power']})")
        print(f"\n✅ Saved to: {REPORTS_DIR / 'missing_moves.txt'}")
    else:
        print("  ✅ No missing moves!")
    print()

    # Report 2: Outdated moves
    print(f"📋 Report 2: Outdated Moves ({len(outdated)} moves)")
    print("=" * 80)
    if outdated:
        with open(REPORTS_DIR / "outdated_moves.txt", 'w', encoding='utf-8') as f:
            f.write("OUTDATED MOVES (different description/power/category/energy/type)\n")
            f.write("=" * 80 + "\n\n")
            for i, move in enumerate(outdated, 1):
                line = f"{i}. {move['chinese_name']} ({move['english_name']})\n"
                line += f"   Differences:\n"
                for diff in move['differences']:
                    line += f"     - {diff}\n"
                line += f"\n   Current values:\n"
                line += f"     Description: {move['current']['description_zh']}\n"
                line += f"     Power: {move['current']['power']}, Category: {move['current']['category']}\n"
                line += f"     Energy: {move['current']['energy_cost']}, Type: {move['current']['type']}\n"
                line += f"\n   New values:\n"
                line += f"     Description: {move['new']['description_zh']}\n"
                line += f"     Power: {move['new']['power']}, Category: {move['new']['category']}\n"
                line += f"     Energy: {move['new']['energy_cost']}, Type: {move['new']['type']}\n\n"
                f.write(line)
                print(f"  {i}. {move['chinese_name']} - {len(move['differences'])} difference(s)")
        print(f"\n✅ Saved to: {REPORTS_DIR / 'outdated_moves.txt'}")
    else:
        print("  ✅ No outdated moves!")
    print()

    # Report 3: Extra moves
    print(f"📋 Report 3: Extra Moves ({len(extra)} moves)")
    print("=" * 80)
    if extra:
        with open(REPORTS_DIR / "extra_moves.txt", 'w', encoding='utf-8') as f:
            f.write("EXTRA MOVES (in moves.json but not in moves_all.json)\n")
            f.write("=" * 80 + "\n\n")
            for i, move in enumerate(extra, 1):
                line = f"{i}. {move['chinese_name']} ({move['english_name']})\n"
                line += f"   Type: {move['type']}, Category: {move['category']}\n"
                line += f"   Energy: {move['energy_cost']}, Power: {move['power']}\n"
                line += f"   Description (EN): {move['description_en']}\n"
                line += f"   Description (ZH): {move['description_zh']}\n\n"
                f.write(line)
                print(f"  {i}. {move['chinese_name']} ({move['english_name']})")
        print(f"\n✅ Saved to: {REPORTS_DIR / 'extra_moves.txt'}")
    else:
        print("  ✅ No extra moves!")
    print()

    # Summary
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print(f"Total moves in moves_all.json: {len(load_json(MOVES_ALL_PATH))}")
    print(f"Total moves in moves.json: {len(load_json(MOVES_PATH))}")
    print(f"Missing moves: {len(missing)}")
    print(f"Outdated moves: {len(outdated)}")
    print(f"Extra moves: {len(extra)}")
    print()
    print(f"📁 Reports saved to: {REPORTS_DIR}/")
    print()

if __name__ == "__main__":
    generate_reports()
