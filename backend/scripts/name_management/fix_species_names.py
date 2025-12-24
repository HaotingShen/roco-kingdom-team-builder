"""
Fix Species Names in Database

This script updates species names to match their corresponding monster names
in cases where a base evolution monster was renamed.

Usage:
    python3 -m backend.scripts.fix_species_names
"""

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from backend.config import DATABASE_URL

engine = create_engine(DATABASE_URL)


def fix_species_names():
    """Update species names to match renamed base evolution monsters."""
    print("=" * 70)
    print("Fixing Species Names")
    print("=" * 70)
    print()

    # These are the species that need updating based on your name changes
    species_updates = [
        {"old": "Meowoo", "new": "Meowu"},
        {"old": "Snowbabe", "new": "Snowling"},
        {"old": "Jadejelly", "new": "Jade Jelly"},
        {"old": "Glassjelly", "new": "Glass Jelly"},
        {"old": "Starlet", "new": "Starlette"},
        {"old": "Fighto-5", "new": "Fighto Five"},
        {"old": "Fighto-6", "new": "Fighto Six"},
        {"old": "Fighto-8", "new": "Fighto Eight"},
    ]

    print(f"Will update {len(species_updates)} species names:")
    print()
    for item in species_updates:
        print(f"  {item['old']} → {item['new']}")
    print()

    response = input("Continue? (yes/no): ")
    print()

    if response.lower() != 'yes':
        print("Aborted.")
        return

    print("Updating species in database...")
    with Session(engine) as session:
        updated_count = 0

        for item in species_updates:
            result = session.execute(
                text("""
                    UPDATE monster_species
                    SET name = :new_name
                    WHERE name = :old_name
                """),
                {
                    "new_name": item["new"],
                    "old_name": item["old"]
                }
            )

            if result.rowcount > 0:
                updated_count += 1
                print(f"  ✓ Updated: {item['old']} → {item['new']}")
            else:
                print(f"  ⚠️  Not found: {item['old']}")

        session.commit()

    print()
    print("=" * 70)
    print(f"✅ SUCCESS: Updated {updated_count} species")
    print("=" * 70)
    print()
    print("Next step: Sync JSON files to match database")
    print("  python3 -m backend.scripts.sync_monsters_json")
    print()
    print("=" * 70)


def main():
    fix_species_names()


if __name__ == "__main__":
    main()
