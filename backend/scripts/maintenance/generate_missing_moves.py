#!/usr/bin/env python3
"""
Generate JSON entries for missing moves from moves_all.json.
Creates a template file with English placeholders that you can manually fill in.
"""
import json
from pathlib import Path
from typing import List, Dict

# File paths
MOVES_ALL_PATH = Path("backend/data/moves_all.json")
MOVES_PATH = Path("backend/data/moves.json")
OUTPUT_PATH = Path("backend/data/move_reports/missing_moves_template.json")

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
    "飞": "Flying",
    "虫": "Bug",
    "毒": "Poison",
    "格": "Fighting",
    "普": "Normal",
    "普通": "Normal",  # Full form
    "萌": "Cute",
    "幽": "Ghost",
    "光": "Light",
    "暗": "Dark",
    "恶": "Dark",  # Alternative name for Dark
    "机": "Mechanical",
    "幻": "Illusion",
    "首": "Leader"
}

def load_json(path: Path) -> List[dict]:
    """Load JSON file."""
    with open(path, encoding='utf-8') as f:
        return json.load(f)

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

def generate_move_entry(move_all: dict) -> dict:
    """Generate a move entry in moves.json format from moves_all.json data."""
    chinese_name = move_all['name']
    category_zh = move_all.get('category', '')
    type_zh = move_all.get('attribute', '')

    # Map to English
    category_en = CATEGORY_MAP.get(category_zh, category_zh)
    type_en = TYPE_MAP.get(type_zh, type_zh)

    # Determine move_category for database
    move_category = None
    if category_en == "Physical Attack":
        move_category = "PHY_ATTACK"
    elif category_en == "Magic Attack":
        move_category = "MAG_ATTACK"
    elif category_en == "Defense":
        move_category = "DEFENSE"
    elif category_en == "Status":
        move_category = "STATUS"

    return {
        "name": f"[TODO: English name for '{chinese_name}']",
        "type": type_en if type_zh else None,
        "category": category_en,
        "energy_cost": int(move_all.get('energy_consumption', 0)),
        "power": normalize_power(move_all.get('power')),
        "description": f"[TODO: English description for '{chinese_name}']",
        "has_counter": False,  # You'll need to manually set this
        "localized": {
            "zh": {
                "name": chinese_name,
                "description": normalize_description(move_all.get('description', ''))
            }
        },
        "_notes": {
            "source_id": move_all.get('id'),
            "original_category": category_zh,
            "original_type": type_zh,
            "beizhu": move_all.get('beizhu')
        }
    }

def find_type_insert_positions(moves: List[dict]) -> Dict[str, int]:
    """
    Find the index where each type group ends in moves.json.
    Returns a dict mapping type name to the index after the last move of that type.
    """
    type_positions = {}
    for i, move in enumerate(moves):
        move_type = move.get('type')
        if move_type:
            # Keep updating - the last occurrence will be the end of the type group
            type_positions[move_type] = i + 1
    return type_positions

def generate_missing_moves():
    """Generate JSON template for missing moves."""
    moves_all = load_json(MOVES_ALL_PATH)
    moves = load_json(MOVES_PATH)

    # Build lookup by Chinese name
    moves_all_map = {get_chinese_name(m): m for m in moves_all}
    moves_map = {get_chinese_name(m): m for m in moves}

    # Find missing moves
    missing = []
    for zh_name, move_all in moves_all_map.items():
        if zh_name not in moves_map:
            missing.append(generate_move_entry(move_all))

    # Group missing moves by type
    missing_by_type = {}
    for move in missing:
        move_type = move.get('type') or 'Unknown'
        if move_type not in missing_by_type:
            missing_by_type[move_type] = []
        missing_by_type[move_type].append(move)

    # Sort each type group by Chinese name
    for move_type in missing_by_type:
        missing_by_type[move_type].sort(key=lambda m: m['localized']['zh']['name'])

    # Find where each type group ends in moves.json
    type_positions = find_type_insert_positions(moves)

    # Flatten back to list, maintaining type grouping
    missing = []
    for move_type in sorted(missing_by_type.keys()):
        missing.extend(missing_by_type[move_type])

    # Create reports directory
    OUTPUT_PATH.parent.mkdir(exist_ok=True)

    # Save to JSON file
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(missing, f, indent=2, ensure_ascii=False)

    print(f"✅ Generated {len(missing)} missing move entries")
    print(f"📁 Saved to: {OUTPUT_PATH}")
    print()

    # Show type grouping and insert positions
    print("📍 Suggested insertion positions by type:")
    print()
    for move_type, moves_list in sorted(missing_by_type.items()):
        position = type_positions.get(move_type, 'unknown')
        count = len(moves_list)
        print(f"  {move_type}: Insert {count} move(s) at index {position}")
        for move in moves_list:
            zh_name = move['localized']['zh']['name']
            print(f"    - {zh_name}")
    print()

    print("📝 Next steps:")
    print("1. Open the generated file")
    print("2. Search for '[TODO:' to find fields that need English translations")
    print("3. Manually fill in:")
    print("   - English move names")
    print("   - English descriptions")
    print("   - has_counter (true/false)")
    print("4. Remove the '_notes' field")
    print("5. Insert moves at the suggested positions to keep types grouped")
    print()

    # Also create a simple checklist
    checklist_path = OUTPUT_PATH.parent / "missing_moves_checklist.txt"
    with open(checklist_path, 'w', encoding='utf-8') as f:
        f.write("MISSING MOVES CHECKLIST\n")
        f.write("=" * 80 + "\n\n")
        for i, move in enumerate(missing, 1):
            zh_name = move['localized']['zh']['name']
            category = move['category']
            power = move['power'] or '--'
            f.write(f"[ ] {i}. {zh_name} ({category}, Power: {power})\n")

    print(f"📋 Checklist saved to: {checklist_path}")

if __name__ == "__main__":
    generate_missing_moves()
