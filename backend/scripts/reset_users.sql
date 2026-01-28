-- Reset all user-related tables and their ID sequences
-- Run this with: psql -d your_database -f reset_users.sql
-- Or via Python: python -m backend.scripts.reset_users

-- Use TRUNCATE with CASCADE to handle FK dependencies automatically
-- This also resets IDENTITY/SERIAL sequences (RESTART IDENTITY)

BEGIN;

-- Truncate all user-related tables with CASCADE and reset sequences
TRUNCATE TABLE
    talents,
    team_analyses,
    user_monsters,
    teams,
    deleted_emails,
    users
RESTART IDENTITY CASCADE;

COMMIT;

-- Verify tables are empty
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
