"""
Phase 6: Validate Transformed Data

This script validates the transformed monsters.json, monster_moves.json,
and monster_species.json files before database import.

Usage:
    python3 -m backend.scripts.validate_transformed_data

Requirements:
    - monsters.json, monster_moves.json, monster_species.json must exist
"""

import json
from pathlib import Path
from collections import defaultdict
import re

# File paths
BACKEND_DIR = Path(__file__).parent.parent.parent
MONSTERS_JSON = BACKEND_DIR / "data" / "monsters.json"
MONSTER_MOVES_JSON = BACKEND_DIR / "data" / "monster_moves.json"
SPECIES_JSON = BACKEND_DIR / "data" / "monster_species.json"
TYPES_JSON = BACKEND_DIR / "data" / "types.json"
TRAITS_JSON = BACKEND_DIR / "data" / "traits.json"


def validate_data():
    """Validate all transformed data files."""
    print("=" * 70)
    print("Phase 6: Validating Transformed Data")
    print("=" * 70)
    print()

    errors = []
    warnings = []

    # Load all data files
    print("Loading data files...")

    try:
        with open(MONSTERS_JSON, encoding="utf-8") as f:
            monsters = json.load(f)
        print(f"✓ Loaded {len(monsters)} monsters")
    except FileNotFoundError:
        print(f"❌ Error: {MONSTERS_JSON} not found!")
        return False

    try:
        with open(MONSTER_MOVES_JSON, encoding="utf-8") as f:
            monster_moves = json.load(f)
        print(f"✓ Loaded {len(monster_moves)} moveset entries")
    except FileNotFoundError:
        print(f"❌ Error: {MONSTER_MOVES_JSON} not found!")
        return False

    try:
        with open(SPECIES_JSON, encoding="utf-8") as f:
            species_list = json.load(f)
        species_names = {s['name'] for s in species_list}
        print(f"✓ Loaded {len(species_names)} species")
    except FileNotFoundError:
        print(f"❌ Error: {SPECIES_JSON} not found!")
        return False

    try:
        with open(TYPES_JSON, encoding="utf-8") as f:
            types_list = json.load(f)
        type_names = {t['name'] for t in types_list}
        print(f"✓ Loaded {len(type_names)} types")
    except FileNotFoundError:
        print(f"❌ Error: {TYPES_JSON} not found!")
        return False

    try:
        with open(TRAITS_JSON, encoding="utf-8") as f:
            traits_list = json.load(f)
        trait_names = {t['name'] for t in traits_list}
        print(f"✓ Loaded {len(trait_names)} traits")
    except FileNotFoundError:
        print(f"❌ Error: {TRAITS_JSON} not found!")
        return False

    print()

    # Validation checks
    print("Running validation checks...")
    print()

    # Check 1: Valid English names
    print("Check 1: Validating English monster names...")
    name_pattern = re.compile(r'^[A-Za-z0-9\s\-\']+$')
    invalid_names = []

    for idx, monster in enumerate(monsters):
        name = monster['name']

        if not name or not name.strip():
            errors.append(f"Monster #{idx+1}: Empty name")
            continue

        if len(name) > 32:
            errors.append(f"Monster #{idx+1}: Name too long (>32 chars): '{name}'")

        if not name_pattern.match(name):
            invalid_names.append(f"Monster #{idx+1}: Invalid characters in name: '{name}'")

    if invalid_names:
        errors.extend(invalid_names[:5])  # Show first 5
        if len(invalid_names) > 5:
            errors.append(f"... and {len(invalid_names) - 5} more invalid names")

    print(f"  {'✓' if not invalid_names else '❌'} {len(invalid_names)} invalid names found")

    # Check 2: Unique (name, form) pairs
    print("Check 2: Checking for duplicate (name, form) pairs...")
    name_form_pairs = defaultdict(list)

    for idx, monster in enumerate(monsters):
        key = (monster['name'], monster['form'])
        name_form_pairs[key].append(idx + 1)

    duplicates = {k: v for k, v in name_form_pairs.items() if len(v) > 1}

    if duplicates:
        for (name, form), indices in list(duplicates.items())[:5]:
            errors.append(f"Duplicate (name, form): ('{name}', '{form}') at lines {indices}")
        if len(duplicates) > 5:
            errors.append(f"... and {len(duplicates) - 5} more duplicates")

    print(f"  {'✓' if not duplicates else '❌'} {len(duplicates)} duplicate pairs found")

    # Check 3: Valid types
    print("Check 3: Validating types...")
    invalid_types = []

    for idx, monster in enumerate(monsters):
        main_type = monster.get('main_type')
        sub_type = monster.get('sub_type')
        legacy_type = monster.get('default_legacy_type')

        if main_type and main_type not in type_names:
            invalid_types.append(f"Monster #{idx+1} ('{monster['name']}'): Invalid main_type '{main_type}'")

        if sub_type and sub_type not in type_names:
            invalid_types.append(f"Monster #{idx+1} ('{monster['name']}'): Invalid sub_type '{sub_type}'")

        if legacy_type and legacy_type not in type_names:
            invalid_types.append(f"Monster #{idx+1} ('{monster['name']}'): Invalid default_legacy_type '{legacy_type}'")

    if invalid_types:
        errors.extend(invalid_types[:5])
        if len(invalid_types) > 5:
            errors.append(f"... and {len(invalid_types) - 5} more invalid types")

    print(f"  {'✓' if not invalid_types else '❌'} {len(invalid_types)} invalid types found")

    # Check 4: Valid traits
    print("Check 4: Validating traits...")
    invalid_traits = []

    for idx, monster in enumerate(monsters):
        trait = monster.get('trait')

        if trait and trait not in trait_names:
            invalid_traits.append(f"Monster #{idx+1} ('{monster['name']}'): Invalid trait '{trait}'")

    if invalid_traits:
        errors.extend(invalid_traits[:5])
        if len(invalid_traits) > 5:
            errors.append(f"... and {len(invalid_traits) - 5} more invalid traits")

    print(f"  {'✓' if not invalid_traits else '❌'} {len(invalid_traits)} invalid traits found")

    # Check 5: Valid species
    print("Check 5: Validating species...")
    invalid_species = []

    for idx, monster in enumerate(monsters):
        species = monster.get('species')

        if species and species not in species_names:
            invalid_species.append(f"Monster #{idx+1} ('{monster['name']}'): Species '{species}' not in species list")

    if invalid_species:
        errors.extend(invalid_species[:5])
        if len(invalid_species) > 5:
            errors.append(f"... and {len(invalid_species) - 5} more invalid species")

    print(f"  {'✓' if not invalid_species else '❌'} {len(invalid_species)} invalid species found")

    # Check 6: Valid evolves_from references
    print("Check 6: Validating evolves_from references...")
    monster_names = {m['name'] for m in monsters}
    invalid_evolutions = []

    for idx, monster in enumerate(monsters):
        evolves_from = monster.get('evolves_from')

        if evolves_from and evolves_from not in monster_names:
            invalid_evolutions.append(f"Monster #{idx+1} ('{monster['name']}'): evolves_from '{evolves_from}' not found")

    if invalid_evolutions:
        errors.extend(invalid_evolutions[:5])
        if len(invalid_evolutions) > 5:
            errors.append(f"... and {len(invalid_evolutions) - 5} more invalid evolution references")

    print(f"  {'✓' if not invalid_evolutions else '❌'} {len(invalid_evolutions)} invalid evolution references")

    # Check 7: No cycles in evolution chains
    print("Check 7: Checking for evolution cycles...")
    evolution_map = {m['name']: m.get('evolves_from') for m in monsters}

    def has_cycle(name, visited):
        """Check if there's a cycle starting from this name."""
        if name in visited:
            return True
        if not evolution_map.get(name):
            return False

        visited.add(name)
        parent = evolution_map[name]
        result = has_cycle(parent, visited)
        visited.remove(name)
        return result

    cycles = []
    for monster in monsters:
        name = monster['name']
        if has_cycle(name, set()):
            cycles.append(name)

    if cycles:
        for name in cycles[:5]:
            errors.append(f"Evolution cycle detected involving '{name}'")
        if len(cycles) > 5:
            errors.append(f"... and {len(cycles) - 5} more cycles")

    print(f"  {'✓' if not cycles else '❌'} {len(cycles)} evolution cycles found")

    # Check 8: Valid moveset_keys
    print("Check 8: Validating moveset_keys...")
    moveset_keys = set(monster_moves.keys())
    missing_movesets = []

    for idx, monster in enumerate(monsters):
        moveset_key = monster.get('moveset_key')

        if moveset_key and moveset_key not in moveset_keys:
            missing_movesets.append(f"Monster #{idx+1} ('{monster['name']}'): moveset_key '{moveset_key}' not found in monster_moves.json")

    if missing_movesets:
        warnings.extend(missing_movesets[:5])
        if len(missing_movesets) > 5:
            warnings.append(f"... and {len(missing_movesets) - 5} more missing moveset keys")

    print(f"  {'✓' if not missing_movesets else '⚠️ '} {len(missing_movesets)} missing moveset keys")

    # Check 9: Order preservation (check t_id from source if available)
    print("Check 9: Checking order preservation...")
    # This check requires comparing with source, skipping for now
    print("  ⏭️  Skipped (requires source comparison)")

    print()

    # Display errors and warnings
    if errors:
        print("=" * 70)
        print(f"ERRORS ({len(errors)}):")
        print("=" * 70)
        for error in errors:
            print(f"  ❌ {error}")
        print()

    if warnings:
        print("=" * 70)
        print(f"WARNINGS ({len(warnings)}):")
        print("=" * 70)
        for warning in warnings:
            print(f"  ⚠️  {warning}")
        print()

    # Summary
    print("=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    print(f"Errors:   {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    print()

    if errors:
        print("❌ VALIDATION FAILED")
        print("Please fix the errors above before proceeding to database import.")
    elif warnings:
        print("⚠️  VALIDATION PASSED WITH WARNINGS")
        print("You may proceed, but consider reviewing the warnings.")
        print()
        print("NEXT STEP: Run generate_import_preview.py to see what will change")
    else:
        print("✅ VALIDATION PASSED")
        print("All checks passed successfully!")
        print()
        print("NEXT STEP: Run generate_import_preview.py to see what will change")

    print("=" * 70)

    return len(errors) == 0


def main():
    success = validate_data()
    if not success:
        exit(1)


if __name__ == "__main__":
    main()
