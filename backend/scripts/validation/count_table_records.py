"""
Script to count and display the number of records in all database tables.
Useful for verifying data imports and getting an overview of the database state.
"""
from sqlalchemy import create_engine, inspect, text
from backend.config import DATABASE_URL

engine = create_engine(DATABASE_URL)

def count_all_tables():
    """Count records in all tables and display results."""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    # Sort tables alphabetically
    table_names.sort()

    print("\n" + "="*60)
    print("DATABASE TABLE RECORD COUNTS")
    print("="*60)

    total_records = 0
    results = []

    with engine.connect() as conn:
        for table_name in table_names:
            try:
                result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
                count = result.scalar()
                results.append((table_name, count))
                total_records += count
            except Exception as e:
                results.append((table_name, f"Error: {e}"))

    # Print results in a formatted table
    print(f"\n{'Table Name':<30} {'Record Count':>15}")
    print("-"*60)

    for table_name, count in results:
        if isinstance(count, int):
            print(f"{table_name:<30} {count:>15,}")
        else:
            print(f"{table_name:<30} {count:>15}")

    print("-"*60)
    print(f"{'TOTAL RECORDS':<30} {total_records:>15,}")
    print("="*60 + "\n")

def main():
    count_all_tables()

if __name__ == "__main__":
    main()
