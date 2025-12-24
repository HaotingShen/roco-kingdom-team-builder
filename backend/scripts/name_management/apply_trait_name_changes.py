#!/usr/bin/env python3
"""
Apply trait name changes from trait_name_mapping.json back to traits.json.
Also updates trait references in monsters.json.

Allows you to quickly update English trait names by editing the mapping file.

Workflow:
  1. Generate mapping: python3 -m backend.scripts.name_management.generate_trait_name_mapping
  2. Edit trait_name_mapping.json with new English names
  3. Apply changes: python3 -m backend.scripts.name_management.apply_trait_name_changes
"""
import json
from pathlib import Path
from typing import Dict, List

# File paths
TRAITS_JSON = Path("backend/data/traits.json")
MONSTERS_JSON = Path("backend/data/monsters.json")
MAPPING_FILE = Path("backend/data/trait_name_mapping.json")
TRAITS_BACKUP = Path("backend/data/traits.json.backup_name_changes")
MONSTERS_BACKUP = Path("backend/data/monsters.json.backup_trait_changes")


def load_json(path: Path) -> any:
    """Load JSON file."""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: File not found: {path}")
        exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {path}")
        print(f"   {e}")
        exit(1)


def save_json(data: any, path: Path):
    """Save data to JSON file with pretty formatting."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Saved to: {path}")
    except Exception as e:
        print(f"❌ Error saving file: {e}")
        exit(1)


def create_backup(source: Path, backup: Path):
    """Create backup of source file."""
    try:
        import shutil
        shutil.copy2(source, backup)
        print(f"💾 Backup created: {backup}")
    except Exception as e:
        print(f"❌ Error creating backup: {e}")
        exit(1)


def apply_name_changes(traits: List[dict], mapping: Dict[str, str]) -> tuple:
    """
    Apply name changes from mapping to traits.

    Args:
        traits: List of trait dictionaries from traits.json
        mapping: Dictionary mapping {chinese_name: new_english_name}

    Returns:
        (updated_traits, changes_count, changes_list, old_to_new_mapping)
    """
    changes = []
    not_found = []
    old_to_new = {}  # Track old_english -> new_english for updating monsters

    for trait in traits:
        chinese_name = trait.get('localized', {}).get('zh', {}).get('name', '')
        current_english = trait.get('name', '')

        if not chinese_name:
            continue

        if chinese_name not in mapping:
            not_found.append(f"{chinese_name} ({current_english})")
            continue

        new_english = mapping[chinese_name]

        # Check if name actually changed
        if current_english != new_english:
            changes.append({
                'chinese_name': chinese_name,
                'old_english': current_english,
                'new_english': new_english
            })
            # Track old -> new mapping for monsters.json update
            old_to_new[current_english] = new_english
            # Update the trait
            trait['name'] = new_english

    # Report not found
    if not_found:
        print(f"⚠️  Warning: {len(not_found)} traits in traits.json not found in mapping:")
        for msg in not_found[:5]:
            print(f"   - {msg}")
        if len(not_found) > 5:
            print(f"   ... and {len(not_found) - 5} more")
        print()

    return traits, len(changes), changes, old_to_new


def update_monsters_traits(monsters: List[dict], old_to_new: Dict[str, str]) -> tuple:
    """
    Update trait references in monsters.json.

    Args:
        monsters: List of monster dictionaries from monsters.json
        old_to_new: Dictionary mapping {old_trait_name: new_trait_name}

    Returns:
        (updated_monsters, updates_count, affected_monsters)
    """
    updated_monsters_list = []
    update_count = 0

    for monster in monsters:
        current_trait = monster.get('trait', '')

        if current_trait in old_to_new:
            new_trait = old_to_new[current_trait]
            monster_name = monster.get('localized', {}).get('zh', {}).get('name', monster.get('name', 'Unknown'))
            updated_monsters_list.append({
                'monster': monster_name,
                'old_trait': current_trait,
                'new_trait': new_trait
            })
            # Update the monster's trait
            monster['trait'] = new_trait
            update_count += 1

    return monsters, update_count, updated_monsters_list


def main():
    """Apply trait name changes from mapping file."""
    print("=" * 80)
    print("APPLY TRAIT NAME CHANGES")
    print("=" * 80)
    print()

    # Load mapping
    print(f"📖 Loading mapping from: {MAPPING_FILE}")
    mapping = load_json(MAPPING_FILE)
    print(f"   Found {len(mapping)} mappings")
    print()

    # Load traits
    print(f"📖 Loading traits from: {TRAITS_JSON}")
    traits = load_json(TRAITS_JSON)
    print(f"   Found {len(traits)} traits")
    print()

    # Load monsters
    print(f"📖 Loading monsters from: {MONSTERS_JSON}")
    monsters = load_json(MONSTERS_JSON)
    print(f"   Found {len(monsters)} monsters")
    print()

    # Apply changes to traits
    print("🔄 Analyzing trait name changes...")
    updated_traits, changes_count, changes, old_to_new = apply_name_changes(traits, mapping)
    print(f"   {changes_count} trait name changes detected")
    print()

    if changes_count == 0:
        print("✅ No changes needed. All names are already up to date!")
        print()
        return

    # Check monster updates
    print("🔄 Checking monster trait references...")
    updated_monsters, monster_updates, affected_monsters = update_monsters_traits(monsters, old_to_new)
    print(f"   {monster_updates} monsters will be updated")
    print()

    # Show trait changes
    print(f"📋 Trait name changes ({changes_count} traits):")
    print("=" * 80)
    for i, change in enumerate(changes[:10], 1):
        print(f"{i}. {change['chinese_name']}")
        print(f"   Old: {change['old_english']}")
        print(f"   New: {change['new_english']}")
    if len(changes) > 10:
        print(f"... and {len(changes) - 10} more changes")
    print()

    # Show monster updates
    if monster_updates > 0:
        print(f"📋 Affected monsters ({monster_updates} monsters):")
        print("=" * 80)
        for i, update in enumerate(affected_monsters[:10], 1):
            print(f"{i}. {update['monster']}")
            print(f"   Trait: {update['old_trait']} → {update['new_trait']}")
        if len(affected_monsters) > 10:
            print(f"... and {len(affected_monsters) - 10} more monsters")
        print()

    # Confirm
    response = input("Apply these changes to traits.json and monsters.json? (yes/no): ")
    if response.lower() != 'yes':
        print("❌ Aborted. No changes were made.")
        return

    print()

    # Create backups
    print(f"💾 Creating backups...")
    create_backup(TRAITS_JSON, TRAITS_BACKUP)
    if monster_updates > 0:
        create_backup(MONSTERS_JSON, MONSTERS_BACKUP)
    print()

    # Save updated traits
    print(f"💾 Saving updated traits to: {TRAITS_JSON}")
    save_json(updated_traits, TRAITS_JSON)
    print()

    # Save updated monsters
    if monster_updates > 0:
        print(f"💾 Saving updated monsters to: {MONSTERS_JSON}")
        save_json(updated_monsters, MONSTERS_JSON)
        print()

    # Save change log
    log_file = Path("backend/data/trait_name_changes_log.json")
    log_data = {
        'trait_changes': changes,
        'monster_updates': affected_monsters
    }
    print(f"📋 Saving change log to: {log_file}")
    save_json(log_data, log_file)
    print()

    # Summary
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print(f"Total traits processed: {len(traits)}")
    print(f"Trait names updated: {changes_count}")
    print(f"Total monsters processed: {len(monsters)}")
    print(f"Monster trait references updated: {monster_updates}")
    print(f"Trait backup saved to: {TRAITS_BACKUP}")
    if monster_updates > 0:
        print(f"Monster backup saved to: {MONSTERS_BACKUP}")
    print(f"Change log saved to: {log_file}")
    print()
    print("✅ Trait names and monster references updated successfully!")
    print()


if __name__ == "__main__":
    main()
