"""
Normalize all Chinese descriptions to use Chinese punctuation marks.
Processes: moves.json, game_terms.json, magic_items.json, traits.json
"""
import json
from pathlib import Path
from typing import List, Dict, Tuple

# File paths
DATA_DIR = Path("backend/data")
FILES_TO_PROCESS = [
    ("moves.json", "moves"),
    ("game_terms.json", "game terms"),
    ("magic_items.json", "magic items"),
    ("traits.json", "traits")
]

def normalize_chinese_punctuation(text: str) -> str:
    """
    Convert English punctuation to Chinese punctuation in Chinese text.
    Also removes extra spaces after Chinese punctuation marks.

    English → Chinese:
    , → ，(comma)
    . → 。(period)
    : → ：(colon)
    ; → ；(semicolon)
    ! → ！(exclamation)
    ? → ？(question mark)
    ( → （(left paren)
    ) → ）(right paren)
    """
    if not text:
        return ''

    # Convert English punctuation to Chinese
    text = text.replace(',', '，')
    text = text.replace(';', '；')
    text = text.replace(':', '：')
    text = text.replace('!', '！')
    text = text.replace('?', '？')
    text = text.replace('(', '（')
    text = text.replace(')', '）')

    # Replace English periods with Chinese periods
    text = text.replace('. ', '。')
    text = text.replace('.', '。')

    # Remove spaces after Chinese punctuation marks
    text = text.replace('， ', '，')
    text = text.replace('。 ', '。')
    text = text.replace('： ', '：')
    text = text.replace('； ', '；')
    text = text.replace('！ ', '！')
    text = text.replace('？ ', '？')
    text = text.replace('） ', '）')

    # Ensure it ends with Chinese period
    if text and not text.endswith('。'):
        text = text + '。'

    return text

def normalize_file(file_path: Path, file_type: str) -> Tuple[List[dict], int, List[dict]]:
    """
    Normalize punctuation in a single file.

    Returns:
        (data, updated_count, changes)
    """
    # Load data
    with open(file_path, encoding='utf-8') as f:
        data = json.load(f)

    # Track changes
    updated_count = 0
    changes = []

    # Update each item
    for item in data:
        if 'localized' not in item or 'zh' not in item['localized']:
            continue

        zh = item['localized']['zh']
        if 'description' not in zh:
            continue

        old_desc = zh['description']
        new_desc = normalize_chinese_punctuation(old_desc)

        if old_desc != new_desc:
            zh['description'] = new_desc
            updated_count += 1
            changes.append({
                'name': item.get('name', item.get('key', '')),
                'chinese_name': zh.get('name', ''),
                'old': old_desc,
                'new': new_desc
            })

    return data, updated_count, changes

def normalize_all_files():
    """Normalize punctuation in all data files."""
    print("=" * 80)
    print("🔧 PUNCTUATION NORMALIZATION")
    print("=" * 80)
    print()

    all_results = {}
    total_files_updated = 0
    total_items_updated = 0

    # Process each file
    for filename, file_type in FILES_TO_PROCESS:
        file_path = DATA_DIR / filename

        print(f"Processing {file_type}... ", end='', flush=True)

        if not file_path.exists():
            print(f"❌ File not found: {file_path}")
            continue

        data, updated_count, changes = normalize_file(file_path, file_type)

        all_results[filename] = {
            'path': file_path,
            'data': data,
            'total': len(data),
            'updated': updated_count,
            'changes': changes
        }

        if updated_count > 0:
            total_files_updated += 1
            total_items_updated += updated_count
            print(f"✅ {updated_count} items updated")
        else:
            print("✅ Already normalized")

    print()
    print("=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)

    # Show summary for each file
    for filename, file_type in FILES_TO_PROCESS:
        if filename not in all_results:
            continue

        result = all_results[filename]
        status = "✅" if result['updated'] == 0 else f"🔧 {result['updated']} updated"
        print(f"{file_type.ljust(15)}: {result['total']} items, {status}")

    print()
    print(f"Total files to update: {total_files_updated}")
    print(f"Total items to update: {total_items_updated}")
    print()

    # If nothing to update, exit
    if total_items_updated == 0:
        print("✅ All punctuation is already normalized!")
        return

    # Show sample changes from each file
    print("Sample changes per file:")
    print()
    for filename, file_type in FILES_TO_PROCESS:
        if filename not in all_results:
            continue

        result = all_results[filename]
        if result['updated'] == 0:
            continue

        print(f"📄 {file_type.upper()}:")
        for i, change in enumerate(result['changes'][:3], 1):
            print(f"  {i}. {change['chinese_name']} ({change['name']})")
            print(f"     Old: {change['old']}")
            print(f"     New: {change['new']}")

        if len(result['changes']) > 3:
            print(f"     ... and {len(result['changes']) - 3} more")
        print()

    # Confirm
    response = input("⚠️  Update all files with normalized punctuation? (yes/no): ")
    if response.lower() != 'yes':
        print("Aborted.")
        return

    print()

    # Process each file
    for filename, file_type in FILES_TO_PROCESS:
        if filename not in all_results:
            continue

        result = all_results[filename]
        if result['updated'] == 0:
            continue

        file_path = result['path']

        # Backup
        backup_path = file_path.with_suffix('.json.backup_punctuation')
        print(f"💾 Creating backup: {backup_path}")
        with open(backup_path, 'w', encoding='utf-8') as f:
            with open(file_path, encoding='utf-8') as original:
                f.write(original.read())

        # Save
        print(f"💾 Saving normalized {file_type} to: {file_path}")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(result['data'], f, indent=2, ensure_ascii=False)

        # Save change log
        log_dir = Path("backend/data/normalization_reports")
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / f"{file_path.stem}_punctuation_changes.json"
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(result['changes'], f, indent=2, ensure_ascii=False)
        print(f"📋 Change log saved to: {log_path}")
        print()

    print("=" * 80)
    print("✅ NORMALIZATION COMPLETE")
    print("=" * 80)
    print(f"Updated {total_files_updated} files")
    print(f"Updated {total_items_updated} total items")
    print()
    print("All Chinese descriptions now use Chinese punctuation marks!")
    print()

if __name__ == "__main__":
    normalize_all_files()
