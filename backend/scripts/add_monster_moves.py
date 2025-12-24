#!/usr/bin/env python3
"""
Script to add monster move entries to monster_moves.json from data_all.xlsx

Usage:
    python3 -m backend.scripts.add_monster_moves
"""

import json
import openpyxl
from pathlib import Path


def read_excel_monster_moves(monster_name: str, excel_path: str) -> dict | None:
    """
    Read monster moves from the 技能表 worksheet in data_all.xlsx

    Args:
        monster_name: Chinese name of the monster
        excel_path: Path to the Excel file

    Returns:
        Dictionary with learnable_moves, move_stones, and legacy_moves lists,
        or None if monster not found
    """
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb['技能表']

    # Find the monster row
    monster_row = None
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[1] and str(row[1]).strip() == monster_name.strip():
            monster_row = row
            break

    if not monster_row:
        return None

    # Extract learnable moves (cols 2-39, pairs of level/move_name)
    learnable_moves = []
    for i in range(2, 40, 2):  # Skip level numbers, only get move names
        if monster_row[i+1]:  # i is level, i+1 is move name
            learnable_moves.append(monster_row[i+1])

    # Extract move stones (cols 40-60)
    move_stones = []
    for i in range(40, 61):
        if monster_row[i]:
            move_stones.append(monster_row[i])

    # Extract legacy moves (cols 61-79)
    legacy_moves = []
    for i in range(61, 79):
        if monster_row[i]:
            legacy_moves.append(monster_row[i])

    return {
        "learnable_moves": learnable_moves,
        "move_stones": move_stones,
        "legacy_moves": legacy_moves
    }


def format_move_list(moves: list[str], indent: int = 4) -> str:
    """
    Format a list of moves into JSON format with max 10 moves per row

    Args:
        moves: List of move names
        indent: Number of spaces for indentation

    Returns:
        Formatted string
    """
    if not moves:
        return "[]"

    lines = []
    indent_str = " " * indent

    # Split into chunks of 10
    for i in range(0, len(moves), 10):
        chunk = moves[i:i+10]
        # Format with quotes and commas
        formatted_chunk = ", ".join(f'"{move}"' for move in chunk)
        lines.append(f"{indent_str}{formatted_chunk}{',' if i + 10 < len(moves) else ''}")

    return "[\n" + "\n".join(lines) + "\n  ]"


def add_to_monster_moves_json(monster_name: str, moves_data: dict, json_path: str):
    """
    Add monster moves entry to monster_moves.json in the correct position

    Tries to find monsters with the same base name (prefix before dash) and places
    the new entry after the last matching one. If no match found, places at top.

    Args:
        monster_name: Chinese name of the monster
        moves_data: Dictionary with learnable_moves, move_stones, and legacy_moves
        json_path: Path to monster_moves.json
    """
    # Read existing JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        existing_data = json.load(f)

    # Check if monster already exists
    if monster_name in existing_data:
        print(f"⚠️  Warning: '{monster_name}' already exists in monster_moves.json")
        response = input("Do you want to replace it? (y/n): ").strip().lower()
        if response != 'y':
            print("Cancelled.")
            return
        # Remove existing entry
        del existing_data[monster_name]

    # Extract base name (prefix before dash)
    base_name = monster_name.split('-')[0] if '-' in monster_name else monster_name

    # Find the position to insert (after the last matching base name)
    insert_position = None
    last_matching_key = None

    for i, key in enumerate(existing_data.keys()):
        key_base = key.split('-')[0] if '-' in key else key
        if key_base == base_name:
            insert_position = i + 1
            last_matching_key = key

    # Build new ordered dictionary
    new_data = {}

    if insert_position is None:
        # No match found, add at the beginning
        print(f"ℹ️  No matching base name '{base_name}' found. Adding to the top.")
        new_data[monster_name] = moves_data
        new_data.update(existing_data)
    else:
        # Insert after the last matching entry
        print(f"ℹ️  Found matching base name '{base_name}'. Inserting after '{last_matching_key}'.")
        for i, (key, value) in enumerate(existing_data.items()):
            new_data[key] = value
            if i == insert_position - 1:
                new_data[monster_name] = moves_data

    # Write back with custom formatting to match the original style
    with open(json_path, 'w', encoding='utf-8') as f:
        f.write("{\n")

        for i, (name, data) in enumerate(new_data.items()):
            # Write monster name
            f.write(f'  "{name}": {{\n')

            # Write learnable_moves
            f.write('    "learnable_moves": ')
            f.write(format_move_list(data["learnable_moves"]))
            f.write(',\n')

            # Write move_stones
            f.write('    "move_stones": ')
            f.write(format_move_list(data["move_stones"]))
            f.write(',\n')

            # Write legacy_moves
            f.write('    "legacy_moves": ')
            f.write(format_move_list(data["legacy_moves"]))
            f.write('\n')

            # Close monster entry
            if i < len(new_data) - 1:
                f.write('  },\n')
            else:
                f.write('  }\n')

        f.write("}\n")

    print(f"✅ Successfully added '{monster_name}' to monster_moves.json")


def main():
    """Main function to run the script interactively"""
    # Setup paths
    script_dir = Path(__file__).parent.parent
    excel_path = script_dir / "data" / "data_all.xlsx"
    json_path = script_dir / "data" / "monster_moves.json"

    # Check if files exist
    if not excel_path.exists():
        print(f"❌ Error: {excel_path} not found")
        return

    if not json_path.exists():
        print(f"❌ Error: {json_path} not found")
        return

    # Prompt for monster name
    print("=" * 60)
    print("Add Monster Moves to monster_moves.json")
    print("=" * 60)
    monster_name = input("\nEnter monster name in Chinese (e.g., 岚鸟-本来的样子): ").strip()

    if not monster_name:
        print("❌ Error: Monster name cannot be empty")
        return

    # Read from Excel
    print(f"\n🔍 Searching for '{monster_name}' in {excel_path.name}...")
    moves_data = read_excel_monster_moves(monster_name, str(excel_path))

    if not moves_data:
        print(f"❌ Error: Monster '{monster_name}' not found in the Excel file")
        return

    # Display preview
    print(f"\n✅ Found '{monster_name}'!")
    print(f"\n📋 Preview:")
    print(f"  Learnable moves: {len(moves_data['learnable_moves'])} moves")
    print(f"    {', '.join(moves_data['learnable_moves'][:5])}{'...' if len(moves_data['learnable_moves']) > 5 else ''}")
    print(f"  Move stones: {len(moves_data['move_stones'])} moves")
    print(f"    {', '.join(moves_data['move_stones'][:5])}{'...' if len(moves_data['move_stones']) > 5 else ''}")
    print(f"  Legacy moves: {len(moves_data['legacy_moves'])} moves")
    print(f"    {', '.join(moves_data['legacy_moves'][:5])}{'...' if len(moves_data['legacy_moves']) > 5 else ''}")

    # Confirm
    print(f"\n❓ Add this entry to the beginning of monster_moves.json?")
    response = input("Continue? (y/n): ").strip().lower()

    if response != 'y':
        print("Cancelled.")
        return

    # Add to JSON
    add_to_monster_moves_json(monster_name, moves_data, str(json_path))

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
