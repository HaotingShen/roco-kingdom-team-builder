"""
Phase 3: Transform Monster Data to English Format

This script converts monsters_all.json (Chinese) to monsters.json (English format)
using the monster_name_mapping.json file for name translations.

Usage:
    python3 -m backend.scripts.transform_monsters_to_english

Requirements:
    - monster_name_mapping.json must be complete (all names translated)
    - traits.json and types.json must exist with proper localization
    - Run check_translation_progress.py to verify before running this
"""

import json
import re
from pathlib import Path
from collections import defaultdict

# File paths
BACKEND_DIR = Path(__file__).parent.parent.parent
MONSTERS_ALL_JSON = BACKEND_DIR / "data" / "monsters_all.json"
MAPPING_JSON = BACKEND_DIR / "data" / "monster_name_mapping.json"
TYPES_JSON = BACKEND_DIR / "data" / "types.json"
TRAITS_JSON = BACKEND_DIR / "data" / "traits.json"
OUTPUT_JSON = BACKEND_DIR / "data" / "monsters.json"

# Attack style mapping
def determine_attack_style(attack, special_attack):
    """Determine preferred attack style based on stats."""
    # Handle None values (some monsters have null stats)
    attack = attack or 0
    special_attack = special_attack or 0

    if attack > special_attack:
        return "Physical"
    elif special_attack > attack:
        return "Magic"
    else:
        return "Both"


def extract_trait_name(abilities_text):
    """
    Extract trait name from abilities_text field.
    Handles both Chinese "：" (U+FF1A) and English ":" (U+003A) punctuation.

    Example:
        "最好的伙伴：每学会一个不同系别的技能，获得攻防+5%" → "最好的伙伴"
        "最好的伙伴:每学会..." → "最好的伙伴"
    """
    if not abilities_text:
        return None

    # Try Chinese colon first
    if '：' in abilities_text:
        return abilities_text.split('：')[0].strip()
    # Fallback to English colon
    elif ':' in abilities_text:
        return abilities_text.split(':')[0].strip()
    else:
        # No colon found - use full text
        return abilities_text.strip()


def build_type_lookup_map_from_json() -> dict:
    """
    Build a type lookup map from types.json.
    Maps both English and Chinese type names to English names.

    Returns:
        dict: {type_name -> English name}
        Example: {"Light": "Light", "光": "Light"}
    """
    with open(TYPES_JSON, encoding='utf-8') as f:
        types_data = json.load(f)

    type_map = {}

    for type_entry in types_data:
        english_name = type_entry['name']

        # Map English name to itself
        type_map[english_name] = english_name

        # Map Chinese name to English name
        # Note: types.json has structure {"localized": {"zh": "中文"}}
        zh_name = type_entry.get('localized', {}).get('zh')
        if zh_name and isinstance(zh_name, str):
            type_map[zh_name] = english_name

    return type_map


def build_trait_lookup_map_from_json() -> dict:
    """
    Build a trait lookup map from traits.json.
    Maps both English and Chinese trait names to English names.

    Returns:
        dict: {trait_name -> English name}
        Example: {"The Best Buddy": "The Best Buddy", "最好的伙伴": "The Best Buddy"}
    """
    with open(TRAITS_JSON, encoding='utf-8') as f:
        traits_data = json.load(f)

    trait_map = {}

    for trait_entry in traits_data:
        english_name = trait_entry['name']

        # Map English name to itself
        trait_map[english_name] = english_name

        # Map Chinese name to English name
        # Note: traits.json has structure {"localized": {"zh": {"name": "中文名"}}}
        zh_name = trait_entry.get('localized', {}).get('zh', {}).get('name')
        if zh_name and isinstance(zh_name, str):
            trait_map[zh_name] = english_name

    return trait_map


def parse_evolution_condition(raw):
    """
    Parse the evolution_condition string from monsters_all.json.

    Source format examples:
        "40级,15次滚雪球"  -> level=40, condition="15次滚雪球"
        "28级,成长1星"     -> level=28, condition="成长1星"
        "36级"            -> level=36, condition=None
        "亲密度进化"        -> level=None, condition="亲密度进化"
        ""/None           -> level=None, condition=None

    Returns:
        (evolution_level: Optional[int], evolution_condition: Optional[str])
    """
    if not raw:
        return None, None

    level_match = re.search(r'(\d+)\s*级', raw)
    level = int(level_match.group(1)) if level_match else None

    if level is not None:
        remaining = re.sub(r'\d+\s*级\s*,?\s*', '', raw, count=1).strip(' ,，')
        condition = remaining if remaining else None
    else:
        condition = raw.strip() or None

    return level, condition


def derive_species_and_parent(monster, name_mapping, monsters_by_chain_group):
    """
    Derive (species_en, evolves_from_en) from chain_group + evolution_stage.

    Rules:
      - Species = English name of the lowest-stage monster in this chain_group.
      - Evolves_from = English name of the stage-(N-1) monster in the same
        chain_group, where N is this monster's evolution_stage. None for stage 1.
      - For branching evolutions (multiple monsters at the same stage), match
        on `attributes` (Chinese type string) to disambiguate; fall back to the
        first candidate when nothing matches.
    """
    chain_group = monster.get('chain_group')
    current_stage = int(monster.get('evolution_stage') or 1)
    current_name = monster['name']
    current_attrs = monster.get('attributes', '') or ''

    if not chain_group:
        return name_mapping.get(current_name), None

    family = monsters_by_chain_group.get(chain_group, [])

    def pick_best(candidates):
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]
        for cand in candidates:
            if (cand.get('attributes') or '') == current_attrs:
                return cand
        return candidates[0]

    # Species: lowest evolution_stage in the chain_group
    if family:
        min_stage = min(int(m.get('evolution_stage') or 1) for m in family)
        base_candidates = [m for m in family if int(m.get('evolution_stage') or 1) == min_stage]
        base = pick_best(base_candidates)
        species_en = name_mapping.get(base['name']) if base else name_mapping.get(current_name)
    else:
        species_en = name_mapping.get(current_name)

    # Evolves_from: stage N-1 in the same chain_group, only if N > min_stage
    evolves_from_en = None
    if family and current_stage > 1:
        parent_candidates = [m for m in family if int(m.get('evolution_stage') or 1) == current_stage - 1]
        parent = pick_best(parent_candidates)
        if parent:
            evolves_from_en = name_mapping.get(parent['name'])

    return species_en, evolves_from_en


def determine_moveset_key(monster, evolution_chain, name_mapping, monsters_by_chain_group):
    """
    Determine the moveset_key for a monster based on evolution chain.

    Rules:
    - Linear evolution: All use highest stage's CHINESE name
    - Branching evolution: Each branch uses its own highest stage's CHINESE name

    Args:
        monster: Current monster dict from monsters_all.json
        evolution_chain: Evolution chain list for this monster
        name_mapping: Chinese→English name mapping
        monsters_by_chain_group: All monsters grouped by chain_group

    Returns:
        Chinese name to use as moveset_key
    """
    current_name = monster['name']
    current_stage = monster['evolution_stage']
    chain_group = monster.get('chain_group')

    # Get all monsters in this evolution family
    family_monsters = monsters_by_chain_group.get(chain_group, [])

    # Group by evolution stage
    stages = defaultdict(list)
    for m in family_monsters:
        stages[m['evolution_stage']].append(m)

    # Find highest stage
    max_stage = max(stages.keys()) if stages else current_stage

    # Check if highest stage has branching (multiple monsters at same stage)
    highest_stage_monsters = stages[max_stage]

    if len(highest_stage_monsters) == 1:
        # Linear evolution - all use the highest stage's Chinese name
        return highest_stage_monsters[0]['name']
    else:
        # Branching evolution - need to determine which branch this monster belongs to
        if current_stage == max_stage:
            # This IS one of the highest stage monsters - use its own Chinese name
            return current_name
        else:
            # This is a lower stage - need to determine which branch it leads to
            # For now, use a simple heuristic: find the highest stage monster that
            # shares the same type as current monster, or just use first one

            # Try to match by type
            current_types = monster.get('attributes', '')
            for high_stage_monster in highest_stage_monsters:
                high_types = high_stage_monster.get('attributes', '')
                if current_types and high_types and current_types == high_types:
                    return high_stage_monster['name']

            # Fallback: For stage 1 monsters with branching stage 2,
            # we need better logic. For now, use the first branch.
            # In reality, we might need to look at evolution_condition or other hints.
            return highest_stage_monsters[0]['name']


def transform_monsters():
    """Main transformation function."""
    print("=" * 70)
    print("Phase 3: Transforming Monster Data to English Format")
    print("=" * 70)
    print()

    # Step 1: Load name mapping
    print("Step 1: Loading monster name mapping...")
    try:
        with open(MAPPING_JSON, encoding="utf-8") as f:
            name_mapping = json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: {MAPPING_JSON} not found!")
        print("Please run generate_monster_name_template.py first.")
        return False

    # Check for untranslated names
    untranslated = [cn for cn, en in name_mapping.items() if not en]
    if untranslated:
        print(f"❌ Error: {len(untranslated)} monster names are not translated yet!")
        print("Run check_translation_progress.py --show-missing to see them.")
        return False

    print(f"✓ Loaded {len(name_mapping)} name translations")
    print()

    # Step 2: Load source data
    print("Step 2: Loading source data from monsters_all.json...")
    with open(MONSTERS_ALL_JSON, encoding="utf-8") as f:
        monsters_all = json.load(f)
    print(f"✓ Loaded {len(monsters_all)} monsters from source")
    print()

    # Step 3: Build lookup maps from JSON files
    print("Step 3: Building type and trait lookup maps from JSON files...")
    type_map = build_type_lookup_map_from_json()
    trait_map = build_trait_lookup_map_from_json()
    print(f"✓ Loaded {len(type_map)} type mappings from types.json")
    print(f"✓ Loaded {len(trait_map)} trait mappings from traits.json")
    print()

    # Step 4: Group monsters by chain_group for moveset_key logic
    print("Step 4: Grouping monsters by evolution families...")
    monsters_by_chain_group = defaultdict(list)
    for monster in monsters_all:
        chain_group = monster.get('chain_group')
        if chain_group:
            monsters_by_chain_group[chain_group].append(monster)
    print(f"✓ Found {len(monsters_by_chain_group)} evolution families")
    print()

    # Build canonical Chinese name lookup (English -> first Chinese name in mapping).
    # When monster_name_mapping.json lists multiple Chinese names for the same
    # English name (e.g., a canonical name plus a wiki-typo alias), the first
    # entry is treated as canonical and used for the output's localized.zh.name.
    en_to_canonical_zh = {}
    for zh, en in name_mapping.items():
        if en and en not in en_to_canonical_zh:
            en_to_canonical_zh[en] = zh

    # Step 5: Transform each monster
    print("Step 5: Transforming monsters...")
    transformed = []
    errors = []
    warnings = []

    for idx, monster in enumerate(monsters_all, 1):
        chinese_name = monster['name']
        english_name = name_mapping.get(chinese_name)

        if not english_name:
            errors.append(f"Line {idx}: No English name for '{chinese_name}'")
            continue

        # Parse attributes (types)
        attributes = monster.get('attributes', '')
        type_list = [t.strip() for t in attributes.split(',') if t.strip()]

        main_type = None
        sub_type = None

        if len(type_list) > 0:
            main_type_zh = type_list[0]
            main_type = type_map.get(main_type_zh)
            if not main_type:
                errors.append(f"Line {idx}: Unknown type '{main_type_zh}' for '{chinese_name}'")
                continue

        if len(type_list) > 1:
            sub_type_zh = type_list[1]
            sub_type = type_map.get(sub_type_zh)
            if not sub_type:
                errors.append(f"Line {idx}: Unknown sub-type '{sub_type_zh}' for '{chinese_name}'")
                continue

        # Extract trait name
        abilities_text = monster.get('abilities_text', '')
        trait_name_zh = extract_trait_name(abilities_text)

        if not trait_name_zh:
            warnings.append(f"Line {idx}: No trait found for '{chinese_name}'")
            trait_name = None
        else:
            trait_name = trait_map.get(trait_name_zh)
            if not trait_name:
                errors.append(f"Line {idx}: Unknown trait '{trait_name_zh}' for '{chinese_name}'")
                continue

        # Determine form
        form_name = monster.get('form_name')
        form_display_name = monster.get('form_display_name')
        is_form = monster.get('is_form', False)

        if form_name and form_name.strip():
            form = form_name
        elif form_display_name and form_display_name.strip():
            form = form_display_name
        else:
            form = "default"

        # Derive species and evolves_from from chain_group + evolution_stage
        # (monsters_all.json has flat fields, not a nested evolution_chain array)
        species, evolves_from = derive_species_and_parent(
            monster, name_mapping, monsters_by_chain_group
        )

        if not species:
            # Fallback: use own English name as species
            species = english_name

        # Parse evolution_level (e.g., "40") and evolution_condition (e.g., "15次滚雪球")
        evolution_level, evolution_condition = parse_evolution_condition(
            monster.get('evolution_condition')
        )

        # Determine moveset_key (Chinese name), then canonicalize via English
        # roundtrip so any wiki-typo Chinese names are normalized to the
        # canonical form listed first in monster_name_mapping.json.
        moveset_key = determine_moveset_key(monster, None, name_mapping, monsters_by_chain_group)
        moveset_key_en = name_mapping.get(moveset_key)
        if moveset_key_en:
            moveset_key = en_to_canonical_zh.get(moveset_key_en, moveset_key)

        # Map stats (handle None values with 'or 0')
        base_hp = monster.get('hp') or 0
        base_phy_atk = monster.get('attack') or 0
        base_mag_atk = monster.get('special_attack') or 0
        base_phy_def = monster.get('defense') or 0
        base_mag_def = monster.get('special_defense') or 0
        base_spd = monster.get('speed') or 0

        # Determine preferred attack style
        preferred_attack_style = determine_attack_style(base_phy_atk, base_mag_atk)

        # Default legacy type (same as main type)
        default_legacy_type = main_type

        # Leader potential and form
        leader_potential = False  # Default, can be updated later if needed
        is_leader_form = (form.lower() == 'leader')

        # Build transformed entry
        transformed_entry = {
            "name": english_name,
            "evolves_from": evolves_from,
            "species": species,
            "form": form,
            "main_type": main_type,
            "sub_type": sub_type,
            "default_legacy_type": default_legacy_type,
            "trait": trait_name,
            "leader_potential": leader_potential,
            "is_leader_form": is_leader_form,
            "base_hp": base_hp,
            "base_phy_atk": base_phy_atk,
            "base_mag_atk": base_mag_atk,
            "base_phy_def": base_phy_def,
            "base_mag_def": base_mag_def,
            "base_spd": base_spd,
            "preferred_attack_style": preferred_attack_style,
            "moveset_key": moveset_key,
            "localized": {
                "zh": {
                    "name": en_to_canonical_zh.get(english_name, chinese_name)
                }
            }
        }

        # Append evolution fields only when present (mirrors monsters.json style)
        if evolution_level is not None:
            transformed_entry["evolution_level"] = evolution_level
        if evolution_condition:
            transformed_entry["evolution_condition"] = evolution_condition

        transformed.append(transformed_entry)

    print(f"✓ Transformed {len(transformed)} monsters")
    print(f"⚠️  {len(warnings)} warnings")
    print(f"❌ {len(errors)} errors")
    print()

    # Display errors and warnings
    if warnings:
        print("Warnings:")
        for w in warnings[:10]:  # Show first 10
            print(f"  {w}")
        if len(warnings) > 10:
            print(f"  ... and {len(warnings) - 10} more")
        print()

    if errors:
        print("Errors:")
        for e in errors[:10]:  # Show first 10
            print(f"  {e}")
        if len(errors) > 10:
            print(f"  ... and {len(errors) - 10} more")
        print()
        print("❌ Transformation failed due to errors. Please fix and retry.")
        return False

    # Step 6: Write output
    print("Step 6: Writing transformed data to monsters.json...")
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(transformed, f, ensure_ascii=False, indent=2)
    print(f"✓ Wrote {len(transformed)} monsters to {OUTPUT_JSON}")
    print()

    # Summary
    print("=" * 70)
    print("TRANSFORMATION COMPLETE")
    print("=" * 70)
    print(f"Input:  {len(monsters_all)} monsters from monsters_all.json")
    print(f"Output: {len(transformed)} monsters to monsters.json")
    print(f"Errors: {len(errors)}")
    print()
    print("NEXT STEP: Run python3 -m backend.scripts.transform.transform_monster_moves to transform moveset data")
    print("=" * 70)

    return True


def main():
    success = transform_monsters()
    if not success:
        exit(1)


if __name__ == "__main__":
    main()
