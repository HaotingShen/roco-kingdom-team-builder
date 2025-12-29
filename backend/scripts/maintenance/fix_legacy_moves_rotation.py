"""
Fix the rotation bug in legacy_moves data.

The legacy_moves arrays in monster_moves.json have a rotation error:
- Positions 0-4 (Normal through Light) are correct
- Position 5 (Ground) has position 16's move (Mechanical)
- Positions 6-16 (Ice through Mechanical) have the previous position's move
- Position 17 (Illusion) is correct

This script fixes the rotation by rearranging the moves.
"""
import json
from pathlib import Path

MONSTERS_JSON_PATH = Path("backend/data/monsters.json")
MONSTER_MOVES_JSON_PATH = Path("backend/data/monster_moves.json")
MONSTER_MOVES_BACKUP_PATH = Path("backend/data/monster_moves.json.backup")

LEGACY_TYPES_ORDER = [
    "Normal", "Grass", "Fire", "Water", "Light", "Ground", "Ice", "Dragon",
    "Electric", "Poison", "Bug", "Fighting", "Flying", "Cute", "Ghost",
    "Dark", "Mechanical", "Illusion"
]

def fix_rotation(legacy_moves):
    """
    Fix the rotation in a legacy_moves array.

    Current pattern (wrong):
        [0, 1, 2, 3, 4, 16, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17]

    Should be:
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
    """
    if len(legacy_moves) != 18:
        print(f"Warning: Expected 18 legacy moves, got {len(legacy_moves)}")
        return legacy_moves

    fixed = legacy_moves.copy()

    # Positions 0-4 are correct (Normal through Light)
    # Position 5 (Ground) currently has position 16's move (Mechanical) - needs fixing
    # Positions 6-16 currently have previous position's move - need shifting
    # Position 17 (Illusion) is correct

    # Extract the correct order:
    # - Keep 0-4 as is (Normal through Light) ✓
    # - Position 5 (Ground) should get from position 6 (currently has Ice's move which is Ground's)
    # - Shift positions 6-16 forward by 1
    # - Position 16 (Mechanical) should get from position 5 (currently has Mechanical's move)
    # - Position 17 stays as is ✓

    # Actually, let me re-analyze the pattern:
    # Current: [N, G, F, W, L, Mechanical, Ground, Ice, Dragon, Electric, Poison, Bug, Fighting, Flying, Cute, Ghost, Dark, Illusion]
    # Want:    [N, G, F, W, L, Ground,     Ice,    Dragon, Electric, Poison, Bug, Fighting, Flying, Cute, Ghost, Dark, Mechanical, Illusion]

    # So the fix is:
    # - Positions 0-4: keep as is ✓
    # - Positions 5-16: shift right by 1 (6→5, 7→6, ..., 16→15, 5→16)
    # - Position 17: keep as is ✓

    temp = fixed[5]  # Save Mechanical's move
    for i in range(5, 16):
        fixed[i] = legacy_moves[i + 1]  # Shift left: position i gets position i+1's value
    fixed[16] = temp  # Position 16 (Mechanical) gets the saved value

    return fixed

def main():
    # Backup the original file
    print(f"Creating backup at {MONSTER_MOVES_BACKUP_PATH}")
    with open(MONSTER_MOVES_JSON_PATH, 'r', encoding='utf-8') as f:
        original_data = json.load(f)

    with open(MONSTER_MOVES_BACKUP_PATH, 'w', encoding='utf-8') as f:
        json.dump(original_data, f, ensure_ascii=False, indent=2)

    # Fix all legacy_moves arrays
    fixed_count = 0
    for moveset_key, moveset in original_data.items():
        if 'legacy_moves' in moveset and len(moveset['legacy_moves']) == 18:
            original_legacy = moveset['legacy_moves']
            fixed_legacy = fix_rotation(original_legacy)
            moveset['legacy_moves'] = fixed_legacy
            fixed_count += 1

    # Write the fixed data
    print(f"Fixed {fixed_count} movesets")
    with open(MONSTER_MOVES_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(original_data, f, ensure_ascii=False, indent=2)

    print(f"✓ Fixed data written to {MONSTER_MOVES_JSON_PATH}")
    print(f"✓ Backup saved at {MONSTER_MOVES_BACKUP_PATH}")
    print()
    print("Next steps:")
    print("  1. Review the changes")
    print("  2. Re-run the import script:")
    print("     python3 -m backend.scripts.importers.import_legacy_moves")

if __name__ == "__main__":
    main()
