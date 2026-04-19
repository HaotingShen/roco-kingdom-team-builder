"""
Production-safe game data update script.
Re-imports game data using ON CONFLICT DO UPDATE without dropping tables.
Preserves user data (teams, user_monsters, talents).
"""
from backend.scripts.importers import (
    import_types,
    import_traits,
    import_personalities,
    import_monster_species,
    import_magic_items,
    import_game_terms,
    import_moves,
    import_monsters,
    import_monster_moves,
    import_legacy_moves,
    import_statuses,
)

if __name__ == "__main__":
    print("🔄 Updating game data (preserving user data)...")
    print()

    # Run import scripts in order
    # These use ON CONFLICT DO UPDATE, so they're safe to re-run
    print("1/10 Importing game terms...")
    import_game_terms.main()

    print("2/10 Importing types...")
    import_types.main()

    print("3/10 Importing traits...")
    import_traits.main()

    print("4/10 Importing personalities...")
    import_personalities.main()

    print("5/10 Importing monster species...")
    import_monster_species.main()

    print("6/10 Importing magic items...")
    import_magic_items.main()

    print("7/10 Importing moves...")
    import_moves.main()

    print("8/10 Importing monsters...")
    import_monsters.main()

    print("9/10 Importing monster-move associations...")
    import_monster_moves.main()

    print("10/10 Importing legacy moves...")
    import_legacy_moves.main()

    print("11/11 Importing statuses...")
    import_statuses.main()

    print()
    print("✅ Game data updated successfully!")
    print("   User teams and data preserved.")
