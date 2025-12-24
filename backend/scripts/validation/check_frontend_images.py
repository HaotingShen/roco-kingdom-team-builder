#!/usr/bin/env python3
"""
Frontend Image Validation Script

Validates that all required frontend images exist for:
1. Monster images (in three sizes: 180, 270, 360)
2. Move icons
3. Magic item images

Author: Generated for Roco Kingdom Team Builder
Date: 2024-12-18
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Set, Tuple
from datetime import datetime


# Path constants
SCRIPT_DIR = Path(__file__).parent  # validation folder
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent  # Up to project root
BACKEND_DATA = PROJECT_ROOT / "backend" / "data"
FRONTEND_PUBLIC = PROJECT_ROOT / "frontend" / "public"

MONSTERS_DATA = BACKEND_DATA / "monsters.json"
MOVES_DATA = BACKEND_DATA / "moves.json"
MAGIC_ITEMS_DATA = BACKEND_DATA / "magic_items.json"

MONSTER_IMAGE_DIRS = [
    FRONTEND_PUBLIC / "monsters" / "180",
    FRONTEND_PUBLIC / "monsters" / "270",
    FRONTEND_PUBLIC / "monsters" / "360",
]
MOVE_ICONS_DIR = FRONTEND_PUBLIC / "move-icons"
MAGIC_ITEMS_DIR = FRONTEND_PUBLIC / "magic-items"


class ImageValidator:
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.notes: List[str] = []
        self.stats: Dict[str, int] = {}

    def safe_basename(self, s: str) -> str:
        """Remove characters illegal on Windows filesystems."""
        return s.replace('\\', '').replace('/', '').replace(':', '').replace('*', '') \
                .replace('?', '').replace('"', '').replace('<', '').replace('>', '') \
                .replace('|', '').strip()

    def get_monster_image_name(self, monster: dict) -> str:
        """
        Generate expected monster image filename based on Chinese name and form.
        For leader forms, omit the form suffix to use shared base image.
        Matches frontend logic in images.ts:monsterImageUrlByCN()
        """
        zh = monster.get("localized", {}).get("zh", {})
        cn_name = zh.get("name", "").strip()
        cn_form = zh.get("form", "").strip()
        is_leader = monster.get("is_leader_form", False)

        if not cn_name:
            return ""

        # For leader forms, omit form suffix
        if is_leader:
            base = self.safe_basename(cn_name)
        elif cn_form:
            base = self.safe_basename(f"{cn_name}({cn_form})")
        else:
            base = self.safe_basename(cn_name)

        return f"{base}.png"

    def validate_monster_images(self):
        """Validate that all monsters have corresponding images in all three sizes."""
        print("\n" + "="*80)
        print("VALIDATING MONSTER IMAGES")
        print("="*80)

        if not MONSTERS_DATA.exists():
            self.errors.append(f"Monsters data file not found: {MONSTERS_DATA}")
            return

        with open(MONSTERS_DATA, 'r', encoding='utf-8') as f:
            monsters = json.load(f)

        self.stats['total_monsters'] = len(monsters)

        # Get actual image files for each size
        actual_images: Dict[str, Set[str]] = {}
        for img_dir in MONSTER_IMAGE_DIRS:
            size = img_dir.name
            if not img_dir.exists():
                self.errors.append(f"Monster image directory not found: {img_dir}")
                actual_images[size] = set()
            else:
                actual_images[size] = {f.name for f in img_dir.iterdir() if f.is_file()}

        # Track shiny variants
        shiny_images: Dict[str, List[str]] = {size: [] for size in ['180', '270', '360']}

        # Check each monster
        missing_by_size: Dict[str, List[Tuple[str, str]]] = {'180': [], '270': [], '360': []}
        found_count = 0

        for monster in monsters:
            expected_name = self.get_monster_image_name(monster)
            if not expected_name:
                self.warnings.append(
                    f"Monster {monster.get('name', 'UNKNOWN')} has no Chinese name"
                )
                continue

            # Check all three sizes
            all_sizes_present = True
            for img_dir in MONSTER_IMAGE_DIRS:
                size = img_dir.name
                if expected_name not in actual_images[size]:
                    missing_by_size[size].append((
                        monster.get('name', 'UNKNOWN'),
                        expected_name
                    ))
                    all_sizes_present = False

            if all_sizes_present:
                found_count += 1

        # Report missing images by size
        for size in ['180', '270', '360']:
            if missing_by_size[size]:
                self.errors.append(
                    f"\n{len(missing_by_size[size])} monsters missing images in {size}/ folder:"
                )
                for en_name, cn_filename in missing_by_size[size]:
                    self.errors.append(f"  - {en_name} → {cn_filename}")

        # Find shiny variant images (异色)
        for size in ['180', '270', '360']:
            shiny = [img for img in actual_images[size] if '异色' in img]
            shiny_images[size] = shiny

        if any(shiny_images.values()):
            self.notes.append("\nShiny variant images found (异色):")
            for size in ['180', '270', '360']:
                if shiny_images[size]:
                    self.notes.append(f"  {size}/: {len(shiny_images[size])} shiny variants")
            self.notes.append("  Note: These are not currently displayed on frontend")

        # Find orphaned images (images without corresponding monsters)
        expected_names = {self.get_monster_image_name(m) for m in monsters if self.get_monster_image_name(m)}
        for size in ['180', '270', '360']:
            orphaned = actual_images[size] - expected_names
            # Exclude shiny variants from orphaned count
            orphaned = {img for img in orphaned if '异色' not in img}
            if orphaned:
                self.warnings.append(f"\n{len(orphaned)} orphaned images in {size}/ (not in monsters.json):")
                for img in sorted(orphaned):
                    self.warnings.append(f"  - {img}")

        self.stats['monsters_with_all_images'] = found_count
        print(f"✓ Monsters with all images: {found_count}/{len(monsters)}")

    def validate_move_icons(self):
        """Validate that all moves have corresponding icon images."""
        print("\n" + "="*80)
        print("VALIDATING MOVE ICONS")
        print("="*80)

        if not MOVES_DATA.exists():
            self.errors.append(f"Moves data file not found: {MOVES_DATA}")
            return

        if not MOVE_ICONS_DIR.exists():
            self.errors.append(f"Move icons directory not found: {MOVE_ICONS_DIR}")
            return

        with open(MOVES_DATA, 'r', encoding='utf-8') as f:
            moves = json.load(f)

        self.stats['total_moves'] = len(moves)

        # Get actual icon files
        actual_icons = {f.name for f in MOVE_ICONS_DIR.iterdir() if f.is_file()}

        # Expected icon filenames (using Chinese names)
        expected_icons = set()
        missing_icons = []

        for move in moves:
            cn_name = move.get("localized", {}).get("zh", {}).get("name", "").strip()
            if not cn_name:
                self.warnings.append(f"Move {move.get('name', 'UNKNOWN')} has no Chinese name")
                continue

            expected_filename = f"{cn_name}.png"
            expected_icons.add(expected_filename)

            if expected_filename not in actual_icons:
                missing_icons.append((move.get('name', 'UNKNOWN'), expected_filename))

        # Report missing icons
        if missing_icons:
            self.errors.append(f"\n{len(missing_icons)} moves missing icon images:")
            for en_name, cn_filename in missing_icons:
                self.errors.append(f"  - {en_name} → {cn_filename}")

        # Find orphaned icons (icons without corresponding moves)
        orphaned_icons = actual_icons - expected_icons
        if orphaned_icons:
            self.warnings.append(f"\n{len(orphaned_icons)} orphaned move icons (not in moves.json):")
            for icon in sorted(orphaned_icons):
                self.warnings.append(f"  - {icon}")

        self.stats['moves_with_icons'] = len(expected_icons & actual_icons)
        self.stats['moves_missing_icons'] = len(missing_icons)
        self.stats['orphaned_icons'] = len(orphaned_icons)

        print(f"✓ Moves with icons: {self.stats['moves_with_icons']}/{len(moves)}")
        if missing_icons:
            print(f"✗ Missing icons: {len(missing_icons)}")
        if orphaned_icons:
            print(f"⚠ Orphaned icons: {len(orphaned_icons)}")

    def validate_magic_item_images(self):
        """Validate that all magic items have corresponding images."""
        print("\n" + "="*80)
        print("VALIDATING MAGIC ITEM IMAGES")
        print("="*80)

        if not MAGIC_ITEMS_DATA.exists():
            self.errors.append(f"Magic items data file not found: {MAGIC_ITEMS_DATA}")
            return

        if not MAGIC_ITEMS_DIR.exists():
            self.errors.append(f"Magic items directory not found: {MAGIC_ITEMS_DIR}")
            return

        with open(MAGIC_ITEMS_DATA, 'r', encoding='utf-8') as f:
            magic_items = json.load(f)

        self.stats['total_magic_items'] = len(magic_items)

        # Get actual image files
        actual_images = {f.name for f in MAGIC_ITEMS_DIR.iterdir() if f.is_file()}

        missing_images = []
        for i, item in enumerate(magic_items):
            cn_name = item.get("localized", {}).get("zh", {}).get("name", "").strip()
            en_name = item.get("name", "").strip()

            # Frontend logic: prefer Chinese name, fallback to English
            expected_filename = f"{cn_name}.png" if cn_name else f"{en_name}.png"

            if expected_filename not in actual_images:
                missing_images.append((
                    i + 1,  # 1-indexed for user clarity
                    en_name,
                    cn_name,
                    expected_filename
                ))

        if missing_images:
            self.errors.append(f"\n{len(missing_images)} magic items missing images:")
            for idx, en_name, cn_name, filename in missing_images:
                self.errors.append(
                    f"  - Item #{idx}: {en_name} (Chinese: {cn_name or 'N/A'}) → {filename}"
                )

        # Find orphaned images
        expected_filenames = set()
        for item in magic_items:
            cn_name = item.get("localized", {}).get("zh", {}).get("name", "").strip()
            en_name = item.get("name", "").strip()
            expected_filenames.add(f"{cn_name}.png" if cn_name else f"{en_name}.png")

        orphaned = actual_images - expected_filenames
        if orphaned:
            self.warnings.append(f"\n{len(orphaned)} orphaned magic item images:")
            for img in sorted(orphaned):
                self.warnings.append(f"  - {img}")

        self.stats['magic_items_with_images'] = len(magic_items) - len(missing_images)

        print(f"✓ Magic items with images: {self.stats['magic_items_with_images']}/{len(magic_items)}")
        if missing_images:
            print(f"✗ Missing images: {len(missing_images)}")
        if orphaned:
            print(f"⚠ Orphaned images: {len(orphaned)}")

    def generate_report(self, output_path: Path):
        """Generate a detailed validation report."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = output_path / f"image_validation_report_{timestamp}.txt"

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("FRONTEND IMAGE VALIDATION REPORT\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*80 + "\n\n")

            # Summary statistics
            f.write("SUMMARY STATISTICS\n")
            f.write("-"*80 + "\n")
            for key, value in self.stats.items():
                f.write(f"{key}: {value}\n")
            f.write("\n")

            # Errors
            if self.errors:
                f.write("ERRORS\n")
                f.write("-"*80 + "\n")
                for error in self.errors:
                    f.write(f"{error}\n")
                f.write("\n")
            else:
                f.write("ERRORS\n")
                f.write("-"*80 + "\n")
                f.write("No errors found!\n\n")

            # Warnings
            if self.warnings:
                f.write("WARNINGS\n")
                f.write("-"*80 + "\n")
                for warning in self.warnings:
                    f.write(f"{warning}\n")
                f.write("\n")
            else:
                f.write("WARNINGS\n")
                f.write("-"*80 + "\n")
                f.write("No warnings.\n\n")

            # Notes
            if self.notes:
                f.write("NOTES\n")
                f.write("-"*80 + "\n")
                for note in self.notes:
                    f.write(f"{note}\n")
                f.write("\n")

        print(f"\n✓ Report saved to: {report_file}")
        return report_file

    def print_summary(self):
        """Print detailed summary of all errors, warnings, and notes."""
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80 + "\n")

        # Errors
        if self.errors:
            print(f"ERRORS ({len(self.errors)}):")
            print("-"*80)
            for error in self.errors:
                print(error)
            print()

        # Warnings
        if self.warnings:
            print(f"WARNINGS ({len(self.warnings)}):")
            print("-"*80)
            for warning in self.warnings:
                print(warning)
            print()

        # Notes
        if self.notes:
            print(f"NOTES ({len(self.notes)}):")
            print("-"*80)
            for note in self.notes:
                print(note)
            print()

    def run(self):
        """Run all validations."""
        print("\n" + "="*80)
        print("FRONTEND IMAGE VALIDATION")
        print("="*80)
        print(f"Project root: {PROJECT_ROOT}")
        print(f"Data directory: {BACKEND_DATA}")
        print(f"Frontend public: {FRONTEND_PUBLIC}")

        self.validate_monster_images()
        self.validate_move_icons()
        self.validate_magic_item_images()

        # Print detailed summary
        self.print_summary()

        # Final summary
        print("="*80)
        print("VALIDATION COMPLETE")
        print("="*80)
        print(f"Errors: {len(self.errors)}")
        print(f"Warnings: {len(self.warnings)}")
        print(f"Notes: {len(self.notes)}")

        return len(self.errors) == 0


def main():
    validator = ImageValidator()
    success = validator.run()
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
