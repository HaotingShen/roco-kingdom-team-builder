#!/usr/bin/env python3
"""
Local Data Consistency Checker for Roco Kingdom Team Builder

This script validates the consistency of monsters.json against other local data files.
It checks:
- Cross-references with monster_species.json, types.json, traits.json, monster_moves.json
- Evolution chain consistency
- Form naming conventions
- Legacy type rules
- Leader potential and is_leader_form flags
- Moveset key naming rules and existence
- Base stats and preferred attack style
- Localization completeness
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict


class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


class ConsistencyChecker:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

        # Load all data files
        self.monsters = self._load_json("monsters.json")
        self.species = self._load_json("monster_species.json")
        self.types = self._load_json("types.json")
        self.traits = self._load_json("traits.json")
        self.monster_moves = self._load_json("monster_moves.json")
        self.moves = self._load_json("moves.json")

        # Build lookup sets and maps for efficient validation
        self.species_names_en = {s["name"] for s in self.species}
        self.species_names_zh = {s["localized"]["zh"] for s in self.species}
        self.type_names = {t["name"] for t in self.types}
        self.trait_names_en = {t["name"] for t in self.traits}
        self.trait_names_zh = {t["localized"]["zh"]["name"] for t in self.traits}
        self.moveset_keys = set(self.monster_moves.keys())

        # Build move name lookups
        self.move_names_en = {m["name"] for m in self.moves}
        self.move_names_zh = {m["localized"]["zh"]["name"] for m in self.moves}

        # Build monster name lookup
        self.monster_names = {m["name"] for m in self.monsters}
        self.monster_names_zh = {m["localized"]["zh"]["name"] for m in self.monsters}

    def _load_json(self, filename: str) -> any:
        """Load and parse a JSON file."""
        filepath = self.data_dir / filename
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            self.error(f"File not found: {filename}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            self.error(f"Invalid JSON in {filename}: {e}")
            sys.exit(1)

    def error(self, msg: str):
        """Record an error message."""
        self.errors.append(msg)

    def warning(self, msg: str):
        """Record a warning message."""
        self.warnings.append(msg)

    def info_msg(self, msg: str):
        """Record an info message."""
        self.info.append(msg)

    def check_all(self):
        """Run all consistency checks."""
        print(f"{Colors.BOLD}{Colors.CYAN}Starting Local Data Consistency Checks...{Colors.RESET}\n")

        self.check_species_consistency()
        self.check_type_consistency()
        self.check_trait_consistency()
        self.check_monster_data()
        self.check_moveset_keys()
        self.check_move_references()

        return self.print_summary()

    def check_species_consistency(self):
        """Check monster_species.json consistency."""
        print(f"{Colors.BOLD}Checking monster_species.json consistency...{Colors.RESET}")

        # Find species referenced in monsters.json but missing from monster_species.json
        monster_species_used = {m["species"] for m in self.monsters}
        missing_species = monster_species_used - self.species_names_en

        if missing_species:
            for species in sorted(missing_species):
                self.error(f"Species '{species}' used in monsters.json but not found in monster_species.json")

        # Find species defined but never used
        unused_species = self.species_names_en - monster_species_used
        if unused_species:
            for species in sorted(unused_species):
                self.warning(f"Species '{species}' defined in monster_species.json but never used in monsters.json")

        print(f"  ✓ Checked {len(self.species)} species definitions\n")

    def check_type_consistency(self):
        """Check types.json consistency."""
        print(f"{Colors.BOLD}Checking types.json consistency...{Colors.RESET}")

        # Collect all types used in monsters
        types_used = set()
        for monster in self.monsters:
            types_used.add(monster["main_type"])
            if monster["sub_type"]:
                types_used.add(monster["sub_type"])
            # Don't check default_legacy_type as it can be "Leader"

        # Find missing types
        missing_types = types_used - self.type_names
        if missing_types:
            for type_name in sorted(missing_types):
                self.error(f"Type '{type_name}' used in monsters.json but not found in types.json")

        print(f"  ✓ Checked {len(self.types)} type definitions\n")

    def check_trait_consistency(self):
        """Check traits.json consistency."""
        print(f"{Colors.BOLD}Checking traits.json consistency...{Colors.RESET}")

        # Collect all traits used (filter out None values)
        traits_used = {m["trait"] for m in self.monsters if m.get("trait") is not None}

        # Find missing traits
        missing_traits = traits_used - self.trait_names_en
        if missing_traits:
            for trait in sorted(missing_traits):
                self.error(f"Trait '{trait}' used in monsters.json but not found in traits.json")

        # Find unused traits
        unused_traits = self.trait_names_en - traits_used
        if unused_traits:
            for trait in sorted(unused_traits):
                self.info_msg(f"Trait '{trait}' defined in traits.json but never used in monsters.json")

        print(f"  ✓ Checked {len(self.traits)} trait definitions\n")

    def check_monster_data(self):
        """Comprehensive validation of monsters.json."""
        print(f"{Colors.BOLD}Checking monsters.json data integrity...{Colors.RESET}")

        # Group monsters by species for evolution chain validation
        species_groups = defaultdict(list)
        for i, monster in enumerate(self.monsters):
            species_groups[monster["species"]].append((i, monster))

        for i, monster in enumerate(self.monsters):
            monster_id = f"{monster['name']} (index {i})"

            # Check 1: Localization exists
            self._check_localization(monster, monster_id)

            # Check 2: Evolution chain consistency
            self._check_evolution(monster, monster_id, i)

            # Check 3: Species validation
            self._check_species(monster, monster_id)

            # Check 4: Form validation
            self._check_form(monster, monster_id)

            # Check 5: Type validation
            self._check_types(monster, monster_id)

            # Check 6: Legacy type validation
            self._check_legacy_type(monster, monster_id)

            # Check 7: Trait validation (already checked in check_trait_consistency)

            # Check 8 & 9: Leader potential and is_leader_form
            self._check_leader_flags(monster, monster_id, i, species_groups[monster["species"]])

            # Check 10: Base stats validation
            self._check_base_stats(monster, monster_id)

            # Check 11: Preferred attack style
            self._check_preferred_attack_style(monster, monster_id)

        print(f"  ✓ Checked {len(self.monsters)} monster entries\n")

    def _check_localization(self, monster: dict, monster_id: str):
        """Check localization fields."""
        if "localized" not in monster:
            self.error(f"{monster_id}: Missing 'localized' field")
            return

        if "zh" not in monster["localized"]:
            self.error(f"{monster_id}: Missing 'localized.zh' field")
            return

        if "name" not in monster["localized"]["zh"]:
            self.error(f"{monster_id}: Missing 'localized.zh.name' field")

    def _check_evolution(self, monster: dict, monster_id: str, index: int):
        """Check evolution chain consistency."""
        evolves_from = monster["evolves_from"]

        if evolves_from is not None:
            # Check if the evolution source exists
            if evolves_from not in self.monster_names:
                self.error(f"{monster_id}: evolves_from '{evolves_from}' does not exist in monsters.json")

            # Check if there's a monster with that name before this one in the same species
            found_prev = False
            for j in range(index):
                prev_monster = self.monsters[j]
                if prev_monster["name"] == evolves_from and prev_monster["species"] == monster["species"]:
                    found_prev = True
                    break

            if not found_prev:
                self.warning(f"{monster_id}: evolves_from '{evolves_from}' not found before this entry in same species")

    def _check_species(self, monster: dict, monster_id: str):
        """Check species field."""
        species = monster["species"]

        if species is None:
            self.error(f"{monster_id}: 'species' field is null")
            return

        if species not in self.species_names_en:
            self.error(f"{monster_id}: species '{species}' not found in monster_species.json")

    def _check_form(self, monster: dict, monster_id: str):
        """Check form field consistency."""
        form = monster["form"]
        zh_form = monster.get("localized", {}).get("zh", {}).get("form")

        # If there's no Chinese form name, form should be "default"
        if zh_form is None:
            if form != "default":
                self.warning(f"{monster_id}: No Chinese form name but 'form' is '{form}' (expected 'default')")
        else:
            # If there is a Chinese form name, form should NOT be "default"
            if form == "default":
                self.warning(f"{monster_id}: Has Chinese form name '{zh_form}' but 'form' is 'default'")

    def _check_types(self, monster: dict, monster_id: str):
        """Check type fields."""
        main_type = monster["main_type"]
        sub_type = monster["sub_type"]

        if main_type not in self.type_names:
            self.error(f"{monster_id}: main_type '{main_type}' not found in types.json")

        if sub_type is not None:
            if sub_type not in self.type_names:
                self.error(f"{monster_id}: sub_type '{sub_type}' not found in types.json")

            if sub_type == main_type:
                self.warning(f"{monster_id}: sub_type is same as main_type ('{main_type}')")

    def _check_legacy_type(self, monster: dict, monster_id: str):
        """Check default_legacy_type field."""
        legacy_type = monster["default_legacy_type"]
        main_type = monster["main_type"]
        is_leader = monster["is_leader_form"]

        if is_leader:
            if legacy_type != "Leader":
                self.error(f"{monster_id}: is_leader_form is True but default_legacy_type is '{legacy_type}' (expected 'Leader')")
        else:
            if legacy_type != main_type:
                self.error(f"{monster_id}: is_leader_form is False but default_legacy_type is '{legacy_type}' (expected '{main_type}')")

    def _check_leader_flags(self, monster: dict, monster_id: str, index: int, species_group: List[Tuple[int, dict]]):
        """Check leader_potential and is_leader_form flags."""
        leader_potential = monster["leader_potential"]
        is_leader = monster["is_leader_form"]
        current_trait = monster["trait"]
        current_name = monster["name"]
        evolves_from = monster.get("evolves_from")

        # Check if any monster in this species evolved FROM this monster as a leader
        has_leader_evolution = False
        for _, other_monster in species_group:
            if (other_monster.get("is_leader_form") and
                other_monster.get("evolves_from") == current_name):
                has_leader_evolution = True
                break

        # Validate leader_potential
        # leader_potential should be True if and only if this monster can evolve into a leader
        if leader_potential and not has_leader_evolution:
            self.warning(f"{monster_id}: leader_potential is True but no leader form evolves from this monster")

        if not leader_potential and has_leader_evolution:
            self.error(f"{monster_id}: leader_potential is False but a leader form DOES evolve from this monster")

        # Validate is_leader_form based on trait changes
        # A leader should have a different trait than the monster it evolved from
        if is_leader and evolves_from:
            # Find the monster this leader evolved from
            evolved_from_monster = None
            for _, other_monster in species_group:
                if other_monster["name"] == evolves_from:
                    evolved_from_monster = other_monster
                    break

            if evolved_from_monster:
                evolved_from_trait = evolved_from_monster["trait"]

                if current_trait == evolved_from_trait:
                    self.warning(f"{monster_id}: is_leader_form is True but has same trait '{current_trait}' as the monster it evolved from ('{evolves_from}')")

    def _check_base_stats(self, monster: dict, monster_id: str):
        """Check base stats are present and valid."""
        required_stats = ["base_hp", "base_phy_atk", "base_mag_atk",
                         "base_phy_def", "base_mag_def", "base_spd"]

        for stat in required_stats:
            if stat not in monster:
                self.error(f"{monster_id}: Missing '{stat}' field")
            elif not isinstance(monster[stat], (int, float)):
                self.error(f"{monster_id}: '{stat}' is not a number: {monster[stat]}")
            elif monster[stat] < 0:
                self.error(f"{monster_id}: '{stat}' is negative: {monster[stat]}")

    def _check_preferred_attack_style(self, monster: dict, monster_id: str):
        """Check if preferred_attack_style matches stats."""
        phy_atk = monster.get("base_phy_atk", 0)
        mag_atk = monster.get("base_mag_atk", 0)
        preferred = monster.get("preferred_attack_style")

        if preferred is None:
            self.error(f"{monster_id}: Missing 'preferred_attack_style' field")
            return

        if phy_atk > mag_atk:
            expected = "Physical"
        elif mag_atk > phy_atk:
            expected = "Magic"
        else:
            expected = "Both"

        if preferred != expected:
            self.error(f"{monster_id}: preferred_attack_style is '{preferred}' but stats suggest '{expected}' (phy_atk={phy_atk}, mag_atk={mag_atk})")

    def check_moveset_keys(self):
        """Check moveset_key naming rules and existence in monster_moves.json."""
        print(f"{Colors.BOLD}Checking moveset_key validity...{Colors.RESET}")

        # Build a map of monster name -> monster data for quick lookup
        monster_map = {m["name"]: m for m in self.monsters}

        # Group monsters by species (ignoring form) and track highest evo stages
        species_highest_evo = {}  # species -> highest_evo_name

        for monster in self.monsters:
            species = monster["species"]
            name = monster["name"]
            is_leader = monster["is_leader_form"]

            # Skip leaders for highest evo tracking
            if is_leader:
                continue

            # Always update to latest (assuming file is ordered by evolution)
            species_highest_evo[species] = name

        # Now validate each monster's moveset_key
        for i, monster in enumerate(self.monsters):
            monster_id = f"{monster['name']} (index {i})"
            species = monster["species"]
            form = monster["form"]
            moveset_key = monster.get("moveset_key")
            is_leader = monster["is_leader_form"]
            zh_form = monster.get("localized", {}).get("zh", {}).get("form")

            if not moveset_key:
                self.error(f"{monster_id}: Missing 'moveset_key' field")
                continue

            # Check if moveset_key exists in monster_moves.json
            if moveset_key not in self.moveset_keys:
                self.error(f"{monster_id}: moveset_key '{moveset_key}' not found in monster_moves.json")

            # Validate naming rules based on whether this is a base form or evolved form
            # Base forms (form="default", no Chinese form) inherit moveset_key from their first evolution
            # Evolved forms should follow the pattern: {highest_evo_zh_name}-{form_zh_name}

            if form == "default" and zh_form is None:
                # This is a base form - find its first evolution to validate moveset_key
                first_evolution = None
                for potential_evo in self.monsters:
                    if potential_evo["evolves_from"] == monster["name"]:
                        first_evolution = potential_evo
                        break

                if first_evolution:
                    # Base form should use the same moveset_key as its first evolution
                    expected_key = first_evolution["moveset_key"]
                    if moveset_key != expected_key:
                        self.warning(f"{monster_id}: moveset_key is '{moveset_key}', expected '{expected_key}' (inherited from first evolution '{first_evolution['name']}')")
                # If no evolution found, skip validation (standalone monster)

            else:
                # This is an evolved form with a specific form name - validate against highest evo
                if species in species_highest_evo:
                    highest_evo_name = species_highest_evo[species]
                    highest_evo_monster = monster_map.get(highest_evo_name)

                    if highest_evo_monster:
                        expected_base = highest_evo_monster["localized"]["zh"]["name"]

                        if zh_form:
                            expected_key = f"{expected_base}-{zh_form}"
                        else:
                            # Evolved form without Chinese form name (rare case)
                            expected_key = expected_base

                        if moveset_key != expected_key:
                            self.warning(f"{monster_id}: moveset_key is '{moveset_key}', expected '{expected_key}' based on naming rules")

        print(f"  ✓ Checked {len(self.monsters)} moveset keys\n")

    def check_move_references(self):
        """Check that all moves in monster_moves.json exist in moves.json and vice versa."""
        print(f"{Colors.BOLD}Checking move references between monster_moves.json and moves.json...{Colors.RESET}")

        # Collect all Chinese move names used in monster_moves.json
        used_moves = set()
        for moveset_key, moveset in self.monster_moves.items():
            # Collect from learnable moves
            if "learnable_moves" in moveset:
                used_moves.update(moveset["learnable_moves"])

            # Collect from move stones
            if "move_stones" in moveset:
                used_moves.update(moveset["move_stones"])

            # Collect from legacy moves
            if "legacy_moves" in moveset:
                used_moves.update(moveset["legacy_moves"])

        # Check 1: All moves used in monster_moves.json should exist in moves.json
        invalid_moves = used_moves - self.move_names_zh
        if invalid_moves:
            for move in sorted(invalid_moves):
                self.error(f"Move '{move}' used in monster_moves.json but not found in moves.json")

        # Check 2: All moves defined in moves.json should be used somewhere in monster_moves.json
        unused_moves = self.move_names_zh - used_moves
        if unused_moves:
            for move in sorted(unused_moves):
                self.warning(f"Move '{move}' defined in moves.json but never used in monster_moves.json")

        print(f"  Total moves in moves.json: {len(self.move_names_zh)}")
        print(f"  Total moves used in monster_moves.json: {len(used_moves)}")
        print(f"  Invalid move references: {len(invalid_moves)}")
        print(f"  Unused moves: {len(unused_moves)}")
        print(f"  ✓ Move reference check complete\n")

    def print_summary(self):
        """Print summary of all checks."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}SUMMARY{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}\n")

        if self.errors:
            print(f"{Colors.BOLD}{Colors.RED}ERRORS ({len(self.errors)}):{Colors.RESET}")
            for error in self.errors:
                print(f"  {Colors.RED}✗{Colors.RESET} {error}")
            print()

        if self.warnings:
            print(f"{Colors.BOLD}{Colors.YELLOW}WARNINGS ({len(self.warnings)}):{Colors.RESET}")
            for warning in self.warnings:
                print(f"  {Colors.YELLOW}⚠{Colors.RESET} {warning}")
            print()

        if self.info:
            print(f"{Colors.BOLD}{Colors.BLUE}INFO ({len(self.info)}):{Colors.RESET}")
            for info in self.info:
                print(f"  {Colors.BLUE}ℹ{Colors.RESET} {info}")
            print()

        # Final verdict
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
        if self.errors:
            print(f"{Colors.BOLD}{Colors.RED}❌ VALIDATION FAILED with {len(self.errors)} error(s){Colors.RESET}")
            return 1
        elif self.warnings:
            print(f"{Colors.BOLD}{Colors.YELLOW}⚠️  VALIDATION PASSED with {len(self.warnings)} warning(s){Colors.RESET}")
            return 0
        else:
            print(f"{Colors.BOLD}{Colors.GREEN}✅ VALIDATION PASSED - All checks successful!{Colors.RESET}")
            return 0


def main():
    """Main entry point."""
    # Determine data directory
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent.parent / "data"

    if not data_dir.exists():
        print(f"{Colors.RED}Error: Data directory not found at {data_dir}{Colors.RESET}")
        return 1

    print(f"{Colors.BOLD}Data directory: {data_dir}{Colors.RESET}\n")

    checker = ConsistencyChecker(data_dir)
    exit_code = checker.check_all()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
