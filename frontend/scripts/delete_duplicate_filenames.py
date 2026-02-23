#!/usr/bin/env python3
"""
Delete images from 180/270/360 folders that have the same filename as images in resize folder.
Does NOT delete anything from the resize folder.
"""

import os
from pathlib import Path
from typing import List, Dict


def get_image_files(folder_path: Path) -> set[str]:
    """Get set of image filenames in a folder."""
    if not folder_path.exists():
        print(f"⚠️  Folder not found: {folder_path}")
        return set()

    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

    filenames = set()
    for file_path in folder_path.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in image_extensions:
            filenames.add(file_path.name)

    return filenames


def find_matching_files(comparison_folders: List[Path], target_filenames: set[str]) -> Dict[str, List[Path]]:
    """Find files in comparison folders that match target filenames."""
    matches = {}

    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

    for folder in comparison_folders:
        if not folder.exists():
            continue

        for file_path in folder.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                if file_path.name in target_filenames:
                    if file_path.name not in matches:
                        matches[file_path.name] = []
                    matches[file_path.name].append(file_path)

    return matches


def delete_files(files_to_delete: Dict[str, List[Path]], dry_run: bool = False) -> tuple[int, int]:
    """Delete the matched files. Returns (deleted_count, failed_count)."""
    deleted = 0
    failed = 0

    for filename, file_paths in sorted(files_to_delete.items()):
        for file_path in file_paths:
            try:
                if dry_run:
                    print(f"   [DRY RUN] Would delete: {file_path}")
                    deleted += 1
                else:
                    file_path.unlink()
                    print(f"   ✓ Deleted: {file_path.parent.name}/{file_path.name}")
                    deleted += 1
            except Exception as e:
                print(f"   ✗ Failed to delete {file_path}: {e}")
                failed += 1

    return deleted, failed


def main():
    # Define base path (WSL format)
    base_path = Path("/mnt/d/Alan/Github Projects/roco-kingdom-team-builder/frontend/public/monster-images")

    # Define folders
    resize_folder = base_path / "resize"
    comparison_folders = [
        base_path / "180",
        base_path / "270",
        base_path / "360"
    ]

    print("=" * 80)
    print("Delete Duplicate Filenames from 180/270/360 Folders")
    print("=" * 80)
    print(f"\nReference folder: {resize_folder}")
    print(f"Will search in: {', '.join([f.name for f in comparison_folders])}")
    print()

    # Get filenames from resize folder
    print("📂 Scanning resize folder for filenames...")
    resize_filenames = get_image_files(resize_folder)
    print(f"   Found {len(resize_filenames)} image files")

    if not resize_filenames:
        print("\n⚠️  No images found in resize folder. Exiting.")
        return

    # Find matching files in comparison folders
    print("\n🔍 Searching for matching filenames in 180/270/360 folders...")
    matches = find_matching_files(comparison_folders, resize_filenames)

    total_matches = sum(len(paths) for paths in matches.values())

    if not matches:
        print("   ✅ No matching filenames found. Nothing to delete.")
        return

    # Show what will be deleted
    print(f"\n⚠️  Found {total_matches} files with matching filenames:")
    print()

    for filename in sorted(matches.keys()):
        print(f"   📄 {filename}")
        for file_path in matches[filename]:
            print(f"      → {file_path.parent.name}/{file_path.name}")

    print()
    print("=" * 80)

    # Ask for confirmation
    print(f"\n⚠️  WARNING: This will DELETE {total_matches} files from 180/270/360 folders!")
    print("The resize folder will NOT be modified.")
    print()

    response = input("Do you want to proceed? Type 'yes' to confirm, 'dry-run' to preview, or anything else to cancel: ").strip().lower()

    if response == "dry-run":
        print("\n🔍 DRY RUN MODE - No files will be deleted\n")
        deleted, failed = delete_files(matches, dry_run=True)
        print(f"\n✅ Dry run complete: {deleted} files would be deleted")
    elif response == "yes":
        print("\n🗑️  Deleting files...\n")
        deleted, failed = delete_files(matches, dry_run=False)
        print()
        print("=" * 80)
        print(f"✅ Deletion complete: {deleted} files deleted, {failed} failed")
        print("=" * 80)
    else:
        print("\n❌ Operation cancelled. No files were deleted.")


if __name__ == "__main__":
    main()
