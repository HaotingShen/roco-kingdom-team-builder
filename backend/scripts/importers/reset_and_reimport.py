import sys
from sqlalchemy import create_engine, inspect, text
from backend.models import Base
from backend.config import DATABASE_URL
from backend.scripts.importers import (
    import_types, import_traits, import_personalities, import_monster_species,
    import_magic_items, import_game_terms, import_moves, import_monsters,
    import_monster_moves, import_legacy_moves, import_statuses
)

engine = create_engine(DATABASE_URL)

def drop_all_except(engine, keep_tables):
    insp = inspect(engine)
    all_tables = insp.get_table_names()
    to_drop = [t for t in all_tables if t not in keep_tables]
    with engine.connect() as conn:
        for table in to_drop:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE;'))
        conn.commit()

def recreate_schema():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    # WARNING: This script is DESTRUCTIVE and drops all user data!
    # Only use during development. For production, use Alembic migrations.

    # Keep only migration history to avoid migration conflicts
    keep_tables = ['alembic_version']

    print("⚠️  WARNING: This will DELETE all data including saved teams!")
    print("   Only alembic_version table will be preserved.")
    response = input("   Continue? (yes/no): ")

    if response.lower() != 'yes':
        print("Aborted.")
        sys.exit(0)

    drop_all_except(engine, keep_tables)
    recreate_schema()

    # Run import scripts in order
    import_game_terms.main()
    import_types.main()
    import_traits.main()
    import_personalities.main()
    import_monster_species.main()
    import_magic_items.main()
    import_moves.main()
    import_monsters.main()
    import_monster_moves.main()
    import_legacy_moves.main()
    import_statuses.main()
    print("Database has been reset and core data imported!")