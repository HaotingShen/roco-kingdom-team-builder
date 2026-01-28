"""
Reset all user-related tables and their ID sequences.

Usage:
    source ~/.venvs/rktb310/bin/activate
    python -m backend.scripts.reset_users

This will truncate:
    - users
    - teams
    - user_monsters
    - talents
    - team_analyses
    - deleted_emails

And reset all their ID sequences to 1.
"""

from sqlalchemy import create_engine, text
from backend.config import DATABASE_URL

engine = create_engine(DATABASE_URL)


def reset_users():
    """Truncate all user-related tables and reset ID sequences."""
    with engine.connect() as conn:
        # Use TRUNCATE with CASCADE to handle FK dependencies
        # RESTART IDENTITY resets the auto-increment sequences
        conn.execute(text("""
            TRUNCATE TABLE
                talents,
                team_analyses,
                user_monsters,
                teams,
                deleted_emails,
                users
            RESTART IDENTITY CASCADE;
        """))
        conn.commit()

        # Verify tables are empty
        result = conn.execute(text("""
            SELECT 'users' AS table_name, COUNT(*) AS count FROM users
            UNION ALL
            SELECT 'teams', COUNT(*) FROM teams
            UNION ALL
            SELECT 'user_monsters', COUNT(*) FROM user_monsters
            UNION ALL
            SELECT 'talents', COUNT(*) FROM talents
            UNION ALL
            SELECT 'team_analyses', COUNT(*) FROM team_analyses
            UNION ALL
            SELECT 'deleted_emails', COUNT(*) FROM deleted_emails;
        """))

        print("Tables reset successfully:")
        for row in result:
            print(f"  {row.table_name}: {row.count} rows")


if __name__ == "__main__":
    confirm = input("This will DELETE ALL USERS and related data. Type 'yes' to confirm: ")
    if confirm.lower() == "yes":
        reset_users()
        print("\nDone! All user-related tables have been truncated and sequences reset.")
    else:
        print("Aborted.")
