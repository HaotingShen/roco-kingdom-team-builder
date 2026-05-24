"""
Sync monsters.json and monster_species.json from Database

This script exports current database data to JSON files.
Useful after applying name changes directly to the database.

Usage:
    python3 -m backend.scripts.sync_monsters_json
"""

import json
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.models import Monster, Type, Trait, MonsterSpecies, AttackStyle
from backend.config import DATABASE_URL

BACKEND_DIR = Path(__file__).parent.parent.parent
MONSTERS_JSON = BACKEND_DIR / "data" / "monsters.json"
SPECIES_JSON = BACKEND_DIR / "data" / "monster_species.json"

engine = create_engine(DATABASE_URL)


def sync_monsters():
    """Export database monsters and species to JSON files."""
    print("=" * 70)
    print("Syncing JSON Files from Database")
    print("=" * 70)
    print()

    with Session(engine) as session:
        # Order by canonical dex_number first (matches monsters.json file order),
        # falling back to id for any rows where dex_number is NULL. Sorting by
        # raw id alone would corrupt the curated monsters.json sequence after
        # we introduced the dex_number column.
        from sqlalchemy import func as _func
        monsters = (
            session.query(Monster)
            .order_by(
                _func.coalesce(Monster.dex_number, Monster.id).asc(),
                Monster.id.asc(),
            )
            .all()
        )

        print(f"✓ Found {len(monsters)} monsters in database")
        print()

        # Build lookup maps
        type_map = {t.id: t.name for t in session.query(Type).all()}
        trait_map = {t.id: t.name for t in session.query(Trait).all()}
        species_map = {s.id: s.name for s in session.query(MonsterSpecies).all()}
        monster_map = {m.id: m.name for m in monsters}
        monster_form_map = {m.id: m.form for m in monsters}

        # Convert to JSON format
        monsters_data = []
        for monster in monsters:
            # Find evolves_from name (and form, for non-default parent forms)
            evolves_from = None
            evolves_from_form = None
            if monster.evolves_from_id:
                evolves_from = monster_map.get(monster.evolves_from_id)
                parent_form = monster_form_map.get(monster.evolves_from_id)
                # Only emit evolves_from_form when the parent isn't the default form,
                # so the importer's auto-detection can't find it via the normal path.
                if parent_form and parent_form != "default":
                    evolves_from_form = parent_form

            # Convert AttackStyle enum to string
            attack_style_map = {
                AttackStyle.PHYSICAL: "Physical",
                AttackStyle.MAGIC: "Magic",
                AttackStyle.BOTH: "Both"
            }

            entry = {
                "name": monster.name,
                "evolves_from": evolves_from,
                **({"evolves_from_form": evolves_from_form} if evolves_from_form else {}),
                "species": species_map[monster.species_id],
                "form": monster.form,
                "main_type": type_map[monster.main_type_id],
                "sub_type": type_map.get(monster.sub_type_id),
                "default_legacy_type": type_map[monster.default_legacy_type_id],
                "trait": trait_map.get(monster.trait_id),
                "leader_potential": monster.leader_potential,
                "is_leader_form": monster.is_leader_form,
                "base_hp": monster.base_hp,
                "base_phy_atk": monster.base_phy_atk,
                "base_mag_atk": monster.base_mag_atk,
                "base_phy_def": monster.base_phy_def,
                "base_mag_def": monster.base_mag_def,
                "base_spd": monster.base_spd,
                "preferred_attack_style": attack_style_map[monster.preferred_attack_style],
                "moveset_key": monster.localized.get("zh", {}).get("name") if isinstance(monster.localized.get("zh"), dict) else None,
                "localized": monster.localized,
                **({"evolution_level": monster.evolution_level} if monster.evolution_level is not None else {}),
                **({"evolution_condition": monster.evolution_condition} if monster.evolution_condition is not None else {}),
                **({"dex_number": monster.dex_number} if monster.dex_number is not None else {}),
            }

            monsters_data.append(entry)

        # Write monsters to file
        print("Writing to monsters.json...")
        with open(MONSTERS_JSON, "w", encoding="utf-8") as f:
            json.dump(monsters_data, f, ensure_ascii=False, indent=2)
        print(f"✓ Wrote {len(monsters_data)} monsters to {MONSTERS_JSON}")
        print()

        # Export species
        print("Exporting species...")
        species = session.query(MonsterSpecies).order_by(MonsterSpecies.id).all()

        species_data = []
        for sp in species:
            species_data.append({
                "name": sp.name,
                "localized": sp.localized
            })

        # Write species to file
        print("Writing to monster_species.json...")
        with open(SPECIES_JSON, "w", encoding="utf-8") as f:
            json.dump(species_data, f, ensure_ascii=False, indent=2)
        print(f"✓ Wrote {len(species_data)} species to {SPECIES_JSON}")
        print()

        print("=" * 70)
        print("✅ SUCCESS: JSON files are now in sync with database")
        print("=" * 70)
        print()


def main():
    sync_monsters()


if __name__ == "__main__":
    main()
