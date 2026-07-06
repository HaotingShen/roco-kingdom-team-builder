"""Localization helpers for the analysis system.

Extracted verbatim from main.py (2026-07-06 behavior-preserving refactor).
Pull localized name/description/move-category from an entity's JSONB
`localized` column, falling back to the English base fields.
"""


def get_localized_name(entity, language="en"):
    """Extract localized name from entity's localized field, falling back to English name."""
    # Get fallback name (GameTerm uses 'key' instead of 'name')
    fallback_name = getattr(entity, "name", None) or getattr(entity, "key", str(entity))

    if hasattr(entity, "localized") and entity.localized:
        try:
            if language == "zh" and "zh" in entity.localized:
                zh_data = entity.localized["zh"]
                if isinstance(zh_data, dict):
                    return zh_data.get("name", fallback_name)
                # If zh_data is a string, it might be the name itself
                elif isinstance(zh_data, str):
                    return zh_data
            if "en" in entity.localized:
                en_data = entity.localized["en"]
                if isinstance(en_data, dict):
                    return en_data.get("name", fallback_name)
                elif isinstance(en_data, str):
                    return en_data
        except (KeyError, TypeError, AttributeError):
            pass
    return fallback_name


def get_localized_description(entity, language="en"):
    """Extract localized description from entity's localized field, falling back to English description."""
    if hasattr(entity, "localized") and entity.localized:
        try:
            if language == "zh" and "zh" in entity.localized:
                zh_data = entity.localized["zh"]
                if isinstance(zh_data, dict):
                    return zh_data.get("description", getattr(entity, "description", ""))
            if "en" in entity.localized:
                en_data = entity.localized["en"]
                if isinstance(en_data, dict):
                    return en_data.get("description", getattr(entity, "description", ""))
        except (KeyError, TypeError, AttributeError):
            pass
    return getattr(entity, "description", "")


def get_localized_move_category(move_category, language="en"):
    """Convert MoveCategory enum/string to localized string representation."""
    category_map = {
        "en": {
            "PHY_ATTACK": "Physical Attack",
            "MAG_ATTACK": "Magic Attack",
            "DEFENSE": "Defense",
            "STATUS": "Status"
        },
        "zh": {
            "PHY_ATTACK": "物攻",
            "MAG_ATTACK": "魔攻",
            "DEFENSE": "防御",
            "STATUS": "状态"
        }
    }

    if not move_category:
        return "Unknown" if language == "en" else "未知"

    # Handle enum object
    if hasattr(move_category, 'name'):
        category_key = move_category.name
    # Handle string (from database/API)
    elif isinstance(move_category, str):
        # Map string values to enum names
        string_to_enum = {
            "Physical Attack": "PHY_ATTACK",
            "Magic Attack": "MAG_ATTACK",
            "Status": "STATUS",
            "Defense": "DEFENSE"
        }
        category_key = string_to_enum.get(move_category, None)
    else:
        category_key = None

    if category_key:
        return category_map.get(language, category_map["en"]).get(category_key, "Unknown" if language == "en" else "未知")
    return "Unknown" if language == "en" else "未知"
