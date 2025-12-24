"""
Phase 5: Generate New Species Entries

This script reads the transformed monsters.json, identifies new species,
and updates monster_species.json with entries for evolution families.

Usage:
    python3 -m backend.scripts.generate_new_species

Requirements:
    - monsters.json must exist (run transform_monsters_to_english.py first)
"""

import json
from pathlib import Path
from collections import OrderedDict

# File paths
BACKEND_DIR = Path(__file__).parent.parent.parent
MONSTERS_JSON = BACKEND_DIR / "data" / "monsters.json"
SPECIES_JSON = BACKEND_DIR / "data" / "monster_species.json"


def generate_new_species():
    """Generate new species entries for monster_species.json."""
    print("=" * 70)
    print("Phase 5: Generating New Species Entries")
    print("=" * 70)
    print()

    # Step 1: Load transformed monsters
    print("Step 1: Loading monsters.json...")
    try:
        with open(MONSTERS_JSON, encoding="utf-8") as f:
            monsters = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: {MONSTERS_JSON} not found!")
        print("Please run transform_monsters_to_english.py first.")
        return False

    print(f"✓ Loaded {len(monsters)} monsters")
    print()

    # Step 2: Load existing species
    print("Step 2: Loading existing species from monster_species.json...")
    try:
        with open(SPECIES_JSON, encoding="utf-8") as f:
            existing_species = json.load(f)
    except FileNotFoundError:
        print("⚠️  monster_species.json not found - will create new file")
        existing_species = []

    existing_species_names = {s['name'] for s in existing_species}
    print(f"✓ Found {len(existing_species)} existing species")
    print()

    # Step 3: Collect unique species from monsters
    print("Step 3: Collecting unique species from transformed monsters...")

    # Build map: species_name -> first monster with that species
    species_map = OrderedDict()
    for monster in monsters:
        species_name = monster['species']
        if species_name not in species_map:
            species_map[species_name] = monster

    print(f"✓ Found {len(species_map)} unique species")
    print()

    # Step 4: Build species list in monsters.json order
    print("Step 4: Building species list in monsters.json order...")

    # Create a lookup map for existing species data
    existing_species_map = {s['name']: s for s in existing_species}

    # Build the complete species list in the order they appear in monsters.json
    all_species = []
    new_species_count = 0

    for species_name, first_monster in species_map.items():
        if species_name in existing_species_map:
            # Use existing species entry
            all_species.append(existing_species_map[species_name])
        else:
            # Create new species entry
            chinese_name = first_monster['localized']['zh']['name']
            new_species_entry = {
                "name": species_name,
                "localized": {"zh": chinese_name}
            }
            all_species.append(new_species_entry)
            new_species_count += 1

    print(f"✓ Total species: {len(all_species)}")
    print(f"  - Existing: {len(existing_species)}")
    print(f"  - New: {new_species_count}")
    print()

    if new_species_count > 0:
        print("New species added (in appearance order):")
        displayed = 0
        for sp in all_species:
            if sp['name'] not in existing_species_names and displayed < 10:
                print(f"  {sp['name']} ({sp['localized']['zh']})")
                displayed += 1
        if new_species_count > 10:
            print(f"  ... and {new_species_count - 10} more")
        print()

    # Step 5: Write output
    print("Step 5: Writing species list in monsters.json order...")

    # Write to file
    with open(SPECIES_JSON, "w", encoding="utf-8") as f:
        json.dump(all_species, f, ensure_ascii=False, indent=2)

    print(f"✓ Wrote {len(all_species)} species to {SPECIES_JSON}")
    print()

    # Summary
    print("=" * 70)
    print("SPECIES GENERATION COMPLETE")
    print("=" * 70)
    print(f"Existing species:   {len(existing_species)}")
    print(f"New species:        {new_species_count}")
    print(f"Total species:      {len(all_species)}")
    print()
    print("✓ Species are now organized in the order they first appear in monsters.json")
    print()
    print("NEXT STEP: Run validate_transformed_data.py to verify all data")
    print("=" * 70)

    return True


def main():
    success = generate_new_species()
    if not success:
        exit(1)


if __name__ == "__main__":
    main()
