#!/usr/bin/env python3
"""
Generate JSON entries for missing traits from monsters_all.json.

Extracts trait name + description from each monster's abilities_text field
and creates template entries with English placeholders for any trait that
is not already present in traits.json.

Output is written to backend/data/trait_reports/missing_traits_template.json
with [TODO: ...] markers for the English name and description fields.
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

MONSTERS_ALL_PATH = Path("backend/data/monsters_all.json")
TRAITS_PATH = Path("backend/data/traits.json")
OUTPUT_PATH = Path("backend/data/trait_reports/missing_traits_template.json")


def load_json(path: Path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def extract_trait_name_and_description(abilities_text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract (name, description) from a monster's abilities_text.

    Handles both Chinese "：" (U+FF1A) and English ":" (U+003A) separators.
    If no separator is found, the entire string is treated as the name.

    Example:
        "狂欢开始：在场时，背包里会变化出随机精灵..." -> ("狂欢开始", "在场时，背包里会变化出随机精灵...")
        "狂欢开始:在场时,..."                       -> ("狂欢开始", "在场时,...")
    """
    if not abilities_text:
        return None, None

    text = abilities_text.strip()
    sep = None
    if '：' in text:
        sep = '：'
    elif ':' in text:
        sep = ':'

    if sep is None:
        return text, None

    name, _, description = text.partition(sep)
    return name.strip(), description.strip()


def normalize_description(desc: str) -> str:
    """Ensure the description ends with a Chinese period."""
    if not desc:
        return ''
    if not desc.endswith('。'):
        desc = desc + '。'
    return desc


def collect_chinese_traits(monsters: List[dict]) -> Dict[str, str]:
    """
    Walk monsters_all.json and collect every distinct Chinese trait name
    together with the description seen most recently for that name.

    Returns a dict {chinese_name -> chinese_description}. Insertion order
    follows first appearance in monsters_all.json (Python dict guarantee).
    """
    seen: Dict[str, str] = {}
    for monster in monsters:
        name, desc = extract_trait_name_and_description(monster.get('abilities_text') or '')
        if not name:
            continue
        # Keep the longest description seen — later/more-detailed entries win.
        existing = seen.get(name, '')
        if len(desc or '') > len(existing):
            seen[name] = desc or ''
    return seen


def load_existing_trait_names() -> set:
    """Return the set of Chinese trait names already present in traits.json."""
    traits = load_json(TRAITS_PATH)
    names = set()
    for trait in traits:
        zh_name = trait.get('localized', {}).get('zh', {}).get('name')
        if zh_name:
            names.add(zh_name)
    return names


def build_template_entry(chinese_name: str, chinese_description: str) -> dict:
    """Build a traits.json-shaped entry with English TODO placeholders."""
    return {
        "name": f"[TODO: English name for '{chinese_name}']",
        "description": f"[TODO: English description for '{chinese_name}']",
        "localized": {
            "zh": {
                "name": chinese_name,
                "description": normalize_description(chinese_description)
            }
        }
    }


def generate_missing_traits() -> int:
    monsters_all = load_json(MONSTERS_ALL_PATH)
    chinese_traits = collect_chinese_traits(monsters_all)
    existing_names = load_existing_trait_names()

    missing_entries: List[dict] = []
    for zh_name, zh_desc in chinese_traits.items():
        if zh_name in existing_names:
            continue
        missing_entries.append(build_template_entry(zh_name, zh_desc))

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(missing_entries, f, indent=2, ensure_ascii=False)

    print(f"Scanned {len(monsters_all)} monsters")
    print(f"Found {len(chinese_traits)} distinct Chinese trait names in source")
    print(f"Already translated: {len(chinese_traits) - len(missing_entries)}")
    print(f"Missing: {len(missing_entries)}")
    print(f"Wrote template to: {OUTPUT_PATH}")

    if missing_entries:
        print()
        print("Missing trait names (paste into trait_name_mapping.json after translating):")
        for entry in missing_entries:
            zh_name = entry['localized']['zh']['name']
            print(f"  - {zh_name}")
        print()
        print("Next steps:")
        print("  1. Open the generated file and replace [TODO: ...] placeholders.")
        print("  2. Append the finished entries to traits.json (before the closing ']').")
        print("  3. Add ZH->EN entries to trait_name_mapping.json.")

    return len(missing_entries)


def main():
    generate_missing_traits()


if __name__ == "__main__":
    main()
