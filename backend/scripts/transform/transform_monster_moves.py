"""
Phase 4: Transform Monster Moveset Data

This script generates monster_moves.json from monsters_all.json.
Moves are grouped by evolution family and keyed by moveset_key (Chinese name).

Usage:
    python3 -m backend.scripts.transform_monster_moves

Requirements:
    - monsters_all.json must exist
    - transform_monsters_to_english.py should be run first to generate moveset_keys
"""

import json
from pathlib import Path
from collections import defaultdict

# File paths
BACKEND_DIR = Path(__file__).parent.parent.parent
MONSTERS_ALL_JSON = BACKEND_DIR / "data" / "monsters_all.json"
MONSTERS_JSON = BACKEND_DIR / "data" / "monsters.json"
OUTPUT_JSON = BACKEND_DIR / "data" / "monster_moves.json"


def parse_move_list(move_string):
    """
    Parse comma-separated move string into list of move names.

    Args:
        move_string: String like "防御,拍击,星轨裂变,大爆炸,..."

    Returns:
        List of move names (strings)
    """
    if not move_string:
        return []

    moves = [m.strip() for m in move_string.split(',') if m.strip()]
    return moves


def format_move_array(moves, max_per_row=10):
    """
    Format a list of moves into a multi-line string with max N moves per row.

    Args:
        moves: List of move names
        max_per_row: Maximum number of moves per row (default: 10)

    Returns:
        Formatted string for JSON array
    """
    if not moves:
        return "[]"

    lines = []
    lines.append("[")

    for i in range(0, len(moves), max_per_row):
        chunk = moves[i:i + max_per_row]
        # Format each move name with quotes
        formatted_chunk = ', '.join(f'"{move}"' for move in chunk)

        # Add comma at end if not the last chunk
        if i + max_per_row < len(moves):
            lines.append(f"    {formatted_chunk},")
        else:
            lines.append(f"    {formatted_chunk}")

    lines.append("  ]")
    return '\n'.join(lines)


def format_monster_moves_json(data):
    """
    Format the monster moves data as JSON with custom array formatting.

    Args:
        data: Dictionary of moveset data

    Returns:
        Formatted JSON string
    """
    lines = ["{"]

    moveset_keys = list(data.keys())
    for idx, moveset_key in enumerate(moveset_keys):
        moveset = data[moveset_key]

        # Add moveset key
        lines.append(f'  "{moveset_key}": {{')

        # Format each field
        learnable = format_move_array(moveset['learnable_moves'])
        move_stones = format_move_array(moveset['move_stones'])
        legacy = format_move_array(moveset['legacy_moves'])

        lines.append(f'    "learnable_moves": {learnable},')
        lines.append(f'    "move_stones": {move_stones},')
        lines.append(f'    "legacy_moves": {legacy}')

        # Close moveset object
        if idx < len(moveset_keys) - 1:
            lines.append("  },")
        else:
            lines.append("  }")

    lines.append("}")
    return '\n'.join(lines)


def transform_monster_moves():
    """Generate monster_moves.json from monsters_all.json."""
    print("=" * 70)
    print("Phase 4: Transforming Monster Moveset Data")
    print("=" * 70)
    print()

    # Step 1: Load source data
    print("Step 1: Loading monsters_all.json...")
    with open(MONSTERS_ALL_JSON, encoding="utf-8") as f:
        monsters_all = json.load(f)
    print(f"✓ Loaded {len(monsters_all)} monsters")
    print()

    # Step 2: Load transformed monsters to get moveset_keys
    print("Step 2: Loading monsters.json to get moveset_keys...")
    try:
        with open(MONSTERS_JSON, encoding="utf-8") as f:
            monsters_transformed = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: {MONSTERS_JSON} not found!")
        print("Please run transform_monsters_to_english.py first.")
        return False

    # Build Chinese name -> moveset_key mapping
    # Also track order of first appearance
    chinese_to_moveset_key = {}
    moveset_key_order = []  # Track order of first appearance

    for monster in monsters_transformed:
        chinese_name = monster['localized']['zh']['name']
        moveset_key = monster['moveset_key']
        chinese_to_moveset_key[chinese_name] = moveset_key

        # Track order of first appearance
        if moveset_key not in moveset_key_order:
            moveset_key_order.append(moveset_key)

    print(f"✓ Loaded {len(monsters_transformed)} transformed monsters")
    print(f"✓ Found {len(moveset_key_order)} unique moveset keys")
    print()

    # Step 3: Group monsters by moveset_key and collect moves (preserving order)
    print("Step 3: Grouping monsters by moveset_key and collecting moves...")
    moveset_data = defaultdict(lambda: {
        'learnable_moves': [],
        'move_stones': [],
        'legacy_moves': []
    })

    for monster in monsters_all:
        chinese_name = monster['name']
        moveset_key = chinese_to_moveset_key.get(chinese_name)

        if not moveset_key:
            print(f"⚠️  Warning: No moveset_key for '{chinese_name}' - skipping")
            continue

        # Parse move strings
        learnable = parse_move_list(monster.get('moves', ''))
        move_stones = parse_move_list(monster.get('jinengshi', ''))
        legacy = parse_move_list(monster.get('xuemai', ''))

        # Add to moveset (preserving order, avoiding duplicates)
        for move in learnable:
            if move not in moveset_data[moveset_key]['learnable_moves']:
                moveset_data[moveset_key]['learnable_moves'].append(move)

        for move in move_stones:
            if move not in moveset_data[moveset_key]['move_stones']:
                moveset_data[moveset_key]['move_stones'].append(move)

        for move in legacy:
            if move not in moveset_data[moveset_key]['legacy_moves']:
                moveset_data[moveset_key]['legacy_moves'].append(move)

    print(f"✓ Created {len(moveset_data)} unique movesets")
    print()

    # Step 4: Build output (preserving order from monsters_all.json)
    print("Step 4: Building output structure...")
    output = {}

    # Use the order from moveset_key_order instead of alphabetical sorting
    for moveset_key in moveset_key_order:
        data = moveset_data[moveset_key]

        # Keep the exact order from monsters_all.json (no sorting)
        output[moveset_key] = {
            "learnable_moves": data['learnable_moves'],
            "move_stones": data['move_stones'],
            "legacy_moves": data['legacy_moves']
        }

    print(f"✓ Built {len(output)} moveset entries")
    print()

    # Step 5: Write output with custom formatting
    print(f"Step 5: Writing movesets to {OUTPUT_JSON}...")
    formatted_json = format_monster_moves_json(output)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        f.write(formatted_json)
    print("✓ File written successfully")
    print()

    # Statistics
    total_learnable = sum(len(v['learnable_moves']) for v in output.values())
    total_stones = sum(len(v['move_stones']) for v in output.values())
    total_legacy = sum(len(v['legacy_moves']) for v in output.values())

    print("=" * 70)
    print("MOVESET TRANSFORMATION COMPLETE")
    print("=" * 70)
    print(f"Total movesets created:     {len(output)}")
    print(f"Total learnable moves:      {total_learnable}")
    print(f"Total move stone moves:     {total_stones}")
    print(f"Total legacy moves:         {total_legacy}")
    print()
    print("NOTE: All move names are in CHINESE (no translation needed!)")
    print()
    print("NEXT STEP: Run generate_new_species.py to create new species entries")
    print("=" * 70)

    return True


def main():
    success = transform_monster_moves()
    if not success:
        exit(1)


if __name__ == "__main__":
    main()
