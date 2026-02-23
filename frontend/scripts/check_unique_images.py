#!/usr/bin/env python3
"""
Check if images in the resize folder are unique compared to images in 180/270/360 folders.
Uses MD5 hashing to compare file contents.
"""

import hashlib
from pathlib import Path
from collections import defaultdict


def compute_file_hash(file_path: Path) -> str:
    """Compute MD5 hash of a file."""
    md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            md5.update(chunk)
    return md5.hexdigest()


def scan_folder(folder_path: Path) -> tuple[dict[str, list[Path]], dict[str, list[Path]]]:
    """
    Scan folder and return two dicts:
    1. Mapping file hash to list of file paths (for content duplicates)
    2. Mapping filename to list of file paths (for filename duplicates)
    """
    hash_to_files = defaultdict(list)
    name_to_files = defaultdict(list)

    if not folder_path.exists():
        print(f"⚠️  Folder not found: {folder_path}")
        return hash_to_files, name_to_files

    image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

    for file_path in folder_path.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in image_extensions:
            file_hash = compute_file_hash(file_path)
            hash_to_files[file_hash].append(file_path)
            name_to_files[file_path.name].append(file_path)

    return hash_to_files, name_to_files


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
    print("Image Uniqueness Check")
    print("=" * 80)
    print(f"\nSource folder: {resize_folder}")
    print(f"Comparing against: {', '.join([f.name for f in comparison_folders])}")
    print()

    # Scan resize folder
    print(f"📂 Scanning {resize_folder.name} folder...")
    resize_hashes, resize_names = scan_folder(resize_folder)
    resize_files_count = sum(len(files) for files in resize_hashes.values())
    print(f"   Found {resize_files_count} images ({len(resize_hashes)} unique hashes)")

    # Scan comparison folders
    comparison_hashes = {}
    comparison_names = {}
    total_comparison_files = 0

    for folder in comparison_folders:
        print(f"📂 Scanning {folder.name} folder...")
        folder_hashes, folder_names = scan_folder(folder)
        files_count = sum(len(files) for files in folder_hashes.values())
        total_comparison_files += files_count
        print(f"   Found {files_count} images ({len(folder_hashes)} unique hashes)")
        comparison_hashes.update(folder_hashes)
        comparison_names.update(folder_names)

    print(f"\n📊 Total comparison images: {total_comparison_files} ({len(comparison_hashes)} unique hashes)")
    print()

    # Compare by content (hash)
    unique_images = []
    duplicate_content_images = []

    for file_hash, resize_files in resize_hashes.items():
        if file_hash in comparison_hashes:
            # Found duplicate content
            for resize_file in resize_files:
                duplicate_content_images.append({
                    'resize_file': resize_file,
                    'matches': comparison_hashes[file_hash]
                })
        else:
            # Unique content
            unique_images.extend(resize_files)

    # Compare by filename
    filename_conflicts = []

    for filename, resize_files in resize_names.items():
        if filename in comparison_names:
            # Found filename conflict
            for resize_file in resize_files:
                filename_conflicts.append({
                    'resize_file': resize_file,
                    'matches': comparison_names[filename]
                })

    # Print results
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)

    print(f"\n✅ UNIQUE IMAGES - Content & Filename ({len(unique_images)}):")
    print("   (Images that don't exist in 180/270/360 folders)")
    if unique_images:
        for file_path in sorted(unique_images):
            print(f"   • {file_path.name}")
    else:
        print("   (None - all images have content duplicates)")

    print(f"\n⚠️  FILENAME CONFLICTS ({len(filename_conflicts)}):")
    print("   (Same filename exists, but content may differ)")
    if filename_conflicts:
        for item in sorted(filename_conflicts, key=lambda x: x['resize_file'].name):
            print(f"   • {item['resize_file'].name}")
            for match in item['matches']:
                print(f"     ↳ Filename exists in: {match.parent.name}/{match.name}")
    else:
        print("   (None - all filenames are unique)")

    print(f"\n❌ DUPLICATE CONTENT ({len(duplicate_content_images)}):")
    print("   (Same file content, even if filename differs)")
    if duplicate_content_images:
        for item in sorted(duplicate_content_images, key=lambda x: x['resize_file'].name):
            print(f"   • {item['resize_file'].name}")
            for match in item['matches']:
                print(f"     ↳ Content matches: {match.parent.name}/{match.name}")
    else:
        print("   (None - all content is unique)")

    print()
    print("=" * 80)
    print(f"Summary: {len(unique_images)} unique | {len(filename_conflicts)} filename conflicts | {len(duplicate_content_images)} content duplicates")
    print(f"Total images in resize folder: {resize_files_count}")
    print("=" * 80)


if __name__ == "__main__":
    main()
