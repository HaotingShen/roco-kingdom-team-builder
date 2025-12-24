"""
Apply Name Changes to Database

This script safely updates the database to match changed English names
in monster_name_mapping.json without creating duplicates.

It updates:
- monsters.name
- monster_species.name (for base evolutions)

Usage:
    python3 -m backend.scripts.apply_name_changes
"""

import json
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from backend.config import DATABASE_URL

# File paths
BACKEND_DIR = Path(__file__).parent.parent.parent
MAPPING_JSON = BACKEND_DIR / "data" / "monster_name_mapping.json"
MONSTERS_JSON = BACKEND_DIR / "data" / "monsters.json"
SPECIES_JSON = BACKEND_DIR / "data" / "monster_species.json"

engine = create_engine(DATABASE_URL)


def apply_changes():
    """Apply name changes to database."""
    print("=" * 70)
    print("Applying Name Changes to Database")
    print("=" * 70)
    print()

    # Load files
    with open(MAPPING_JSON, encoding="utf-8") as f:
        mapping = json.load(f)

    with open(MONSTERS_JSON, encoding="utf-8") as f:
        monsters = json.load(f)

    # Load species
    try:
        with open(SPECIES_JSON, encoding="utf-8") as f:
            species_list = json.load(f)
    except FileNotFoundError:
        species_list = []

    # Build lookup: Chinese name → existing English name
    existing_names = {}
    existing_species = {}

    for monster in monsters:
        zh_name = monster.get("localized", {}).get("zh", {}).get("name")
        if zh_name:
            existing_names[zh_name] = {
                "old_name": monster["name"],
                "form": monster["form"],
                "species": monster.get("species")  # Track species
            }

    # Build species lookup
    for species in species_list:
        species_name = species.get("name")
        zh_name = species.get("localized", {}).get("zh")
        if species_name and zh_name:
            existing_species[zh_name] = species_name

    # Find changes
    monster_changes = []
    species_changes = []

    for zh_name, new_en_name in mapping.items():
        if zh_name in existing_names:
            old_en_name = existing_names[zh_name]["old_name"]
            form = existing_names[zh_name]["form"]
            species = existing_names[zh_name]["species"]

            if old_en_name != new_en_name:
                monster_changes.append({
                    "zh": zh_name,
                    "old": old_en_name,
                    "new": new_en_name,
                    "form": form,
                    "species": species
                })

                # Check if this is also a species (base evolution)
                if species == old_en_name:
                    species_changes.append({
                        "zh": zh_name,
                        "old": old_en_name,
                        "new": new_en_name
                    })

    if not monster_changes:
        print("✓ No name changes to apply!")
        print()
        return

    print(f"Found {len(monster_changes)} monster names to update:")
    print()
    for item in monster_changes:
        is_species = item["species"] == item["old"]
        species_marker = " (also a species)" if is_species else ""
        print(f"  {item['zh']} (form: {item['form']}){species_marker}")
        print(f"    {item['old']} → {item['new']}")
    print()

    if species_changes:
        print(f"Found {len(species_changes)} species names to update:")
        print()
        for item in species_changes:
            print(f"  {item['zh']}: {item['old']} → {item['new']}")
        print()

    # Confirm with user
    print("⚠️  This will UPDATE the database!")
    print("   All saved teams will automatically use the new names.")
    response = input("   Continue? (yes/no): ")
    print()

    if response.lower() != 'yes':
        print("Aborted.")
        return

    # Apply updates
    print("Applying updates to database...")
    with Session(engine) as session:
        # Update monsters
        monster_updated = 0
        for item in monster_changes:
            result = session.execute(
                text("""
                    UPDATE monsters
                    SET name = :new_name
                    WHERE name = :old_name AND form = :form
                """),
                {
                    "new_name": item["new"],
                    "old_name": item["old"],
                    "form": item["form"]
                }
            )

            if result.rowcount > 0:
                monster_updated += 1
                print(f"  ✓ Monster: {item['old']} → {item['new']}")
            else:
                print(f"  ⚠️  Monster not found: {item['old']} (form: {item['form']})")

        # Update species
        species_updated = 0
        if species_changes:
            print()
            print("Updating species...")
            for item in species_changes:
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
                    species_updated += 1
                    print(f"  ✓ Species: {item['old']} → {item['new']}")
                else:
                    print(f"  ⚠️  Species not found: {item['old']}")

        session.commit()

    print()
    print("=" * 70)
    print("✅ SUCCESS!")
    print("=" * 70)
    print(f"Updated {monster_updated} monsters in database")
    if species_changes:
        print(f"Updated {species_updated} species in database")
    print()
    print("IMPORTANT: Now sync your JSON files to match:")
    print("  python3 -m backend.scripts.sync_monsters_json")
    print()
    print("=" * 70)


def main():
    apply_changes()


if __name__ == "__main__":
    main()
