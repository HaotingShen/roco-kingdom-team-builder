"""
Backend Scripts Module

Scripts are organized into the following categories:

📁 importers/           - Database import scripts
📁 transform/           - English translation workflow scripts
📁 maintenance/         - Data update and maintenance scripts
📁 name_management/     - Name change utility scripts
📁 utils/               - Miscellaneous utility scripts

Usage Examples:
    # Run a script as a module:
    python3 -m backend.scripts.importers.import_monsters
    python3 -m backend.scripts.transform.check_translation_progress
    python3 -m backend.scripts.name_management.detect_name_changes

    # Import in code (backward compatible - old paths still work):
    from backend.scripts.importers import import_monsters
    from backend.scripts.transform import transform_monsters_to_english
    from backend.scripts.name_management import detect_name_changes
"""
