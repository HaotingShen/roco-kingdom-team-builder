"""
Team Popularity Analysis Report
================================
Queries the production database and outputs a structured Markdown report
covering every analyzable dimension of user team-building behavior.

Usage (from project root):
    # Local (with .env)
    source ~/.venvs/rktb310/bin/activate
    python3 -m backend.scripts.analysis.team_popularity_report

    # On EC2 (inside backend container, DATABASE_URL already in env)
    docker compose -f docker-compose.prod.yml exec backend \
        python3 -m backend.scripts.analysis.team_popularity_report

Output: team_popularity_report.md (in current working directory)
"""

import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

from sqlalchemy import create_engine, text, func, and_, case
from sqlalchemy.orm import sessionmaker, joinedload

from backend.config import DATABASE_URL
from backend.models import (
    User, Team, UserMonster, Monster, MonsterSpecies, Move, MagicItem,
    Personality, Type, Trait, Talent, TeamAnalysis, LegacyMove,
    monster_moves as monster_moves_table,
)

# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pct(n: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{n / total * 100:.1f}%"


def bar(n: int, total: int, width: int = 20) -> str:
    filled = int(n / total * width) if total > 0 else 0
    return "█" * filled + "░" * (width - filled)


def zh(obj, field: str = "name") -> str:
    """Return Chinese localized name if available, else English name."""
    if hasattr(obj, "localized") and obj.localized:
        zh_data = obj.localized.get("zh", {})
        if isinstance(zh_data, dict) and zh_data.get(field):
            return zh_data[field]
    return getattr(obj, field, str(obj))


def rank_table(rows, headers, total=None) -> list[str]:
    """Return a Markdown table from a list of row tuples."""
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return lines


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect(db) -> dict:
    data = {}

    # ── 0. Scope ─────────────────────────────────────────────────────────────
    # Exclude featured (admin-curated) teams.
    # All valid saved teams have exactly 6 monsters (enforced by frontend before save),
    # no leader-form monsters (MonsterPicker hardcodes is_leader_form=false),
    # a magic item, and at least 1 talent stat nonzero per monster.
    # We still filter to exactly 6 monsters as a data-integrity guard.
    user_team_ids_q = (
        db.query(Team.id)
        .join(UserMonster, UserMonster.team_id == Team.id)
        .filter(Team.is_featured == False)
        .group_by(Team.id)
        .having(func.count(UserMonster.id) == 6)
    )
    user_team_ids = [r[0] for r in user_team_ids_q.all()]
    T = len(user_team_ids)  # total qualifying user teams

    data["scope"] = {
        "total_teams_all": db.query(func.count(Team.id)).scalar(),
        "total_teams_user": T,
        "total_featured": db.query(func.count(Team.id)).filter(Team.is_featured == True).scalar(),
        "total_users": db.query(func.count(User.id)).scalar(),
        "total_users_with_teams": db.query(func.count(func.distinct(Team.owner_id)))
            .filter(Team.id.in_(user_team_ids)).scalar(),
        "total_registered": db.query(func.count(User.id)).filter(User.is_guest == False).scalar(),
        "total_guest": db.query(func.count(User.id)).filter(User.is_guest == True).scalar(),
    }

    # ── 1. Monster popularity ─────────────────────────────────────────────────
    # Safety: filter is_leader_form=false (guaranteed by frontend, but explicit here)
    monster_usage = db.execute(text("""
        SELECT
            m.id,
            m.name,
            m.form,
            ms.name AS species_name,
            t1.name AS main_type,
            t2.name AS sub_type,
            COUNT(um.id) AS usage_count,
            COUNT(DISTINCT um.team_id) AS team_count
        FROM user_monsters um
        JOIN monsters m ON um.monster_id = m.id AND m.is_leader_form = false
        JOIN monster_species ms ON m.species_id = ms.id
        JOIN types t1 ON m.main_type_id = t1.id
        LEFT JOIN types t2 ON m.sub_type_id = t2.id
        WHERE um.team_id = ANY(:ids)
        GROUP BY m.id, m.name, m.form, ms.name, t1.name, t2.name
        ORDER BY usage_count DESC
    """), {"ids": user_team_ids}).fetchall()
    data["monster_usage"] = monster_usage

    # ── 2. Monster species popularity (collapses forms) ───────────────────────
    species_usage = db.execute(text("""
        SELECT
            ms.name AS species_name,
            COUNT(um.id) AS usage_count,
            COUNT(DISTINCT um.team_id) AS team_count,
            COUNT(DISTINCT um.monster_id) AS form_count
        FROM user_monsters um
        JOIN monsters m ON um.monster_id = m.id AND m.is_leader_form = false
        JOIN monster_species ms ON m.species_id = ms.id
        WHERE um.team_id = ANY(:ids)
        GROUP BY ms.name
        ORDER BY usage_count DESC
    """), {"ids": user_team_ids}).fetchall()
    data["species_usage"] = species_usage

    # ── 3. Monster pairs ──────────────────────────────────────────────────────
    pairs = db.execute(text("""
        SELECT
            LEAST(m1.name, m2.name) AS mon_a,
            GREATEST(m1.name, m2.name) AS mon_b,
            COUNT(*) AS pair_count
        FROM user_monsters um1
        JOIN user_monsters um2
            ON um1.team_id = um2.team_id AND um1.id < um2.id
        JOIN monsters m1 ON um1.monster_id = m1.id
        JOIN monsters m2 ON um2.monster_id = m2.id
        WHERE um1.team_id = ANY(:ids)
        GROUP BY 1, 2
        ORDER BY pair_count DESC
        LIMIT 20
    """), {"ids": user_team_ids}).fetchall()
    data["pairs"] = pairs

    # ── 4. Monster trios ──────────────────────────────────────────────────────
    trios = db.execute(text("""
        SELECT
            mon_a, mon_b, mon_c, trio_count
        FROM (
            SELECT
                m1.name AS n1, m2.name AS n2, m3.name AS n3,
                LEAST(m1.name, m2.name, m3.name) AS mon_a,
                GREATEST(m1.name, m2.name, m3.name) AS mon_c,
                CASE
                    WHEN m1.name NOT IN (LEAST(m1.name,m2.name,m3.name), GREATEST(m1.name,m2.name,m3.name)) THEN m1.name
                    WHEN m2.name NOT IN (LEAST(m1.name,m2.name,m3.name), GREATEST(m1.name,m2.name,m3.name)) THEN m2.name
                    ELSE m3.name
                END AS mon_b,
                COUNT(*) AS trio_count
            FROM user_monsters um1
            JOIN user_monsters um2 ON um1.team_id = um2.team_id AND um1.id < um2.id
            JOIN user_monsters um3 ON um1.team_id = um3.team_id AND um2.id < um3.id
            JOIN monsters m1 ON um1.monster_id = m1.id
            JOIN monsters m2 ON um2.monster_id = m2.id
            JOIN monsters m3 ON um3.monster_id = m3.id
            WHERE um1.team_id = ANY(:ids)
            GROUP BY m1.name, m2.name, m3.name
        ) ranked
        GROUP BY mon_a, mon_b, mon_c, trio_count
        ORDER BY trio_count DESC
        LIMIT 15
    """), {"ids": user_team_ids}).fetchall()
    data["trios"] = trios

    # ── 5. Magic item popularity ──────────────────────────────────────────────
    # All valid teams have a magic item (enforced by canAnalyze), so no NULL case.
    magic_items = db.execute(text("""
        SELECT
            mi.name,
            mi.effect_code,
            COUNT(t.id) AS usage_count,
            COUNT(t.id) * 100.0 / :total AS pct
        FROM teams t
        JOIN magic_items mi ON t.magic_item_id = mi.id
        WHERE t.id = ANY(:ids)
        GROUP BY mi.id, mi.name, mi.effect_code
        ORDER BY usage_count DESC
    """), {"ids": user_team_ids, "total": T or 1}).fetchall()
    data["magic_items"] = magic_items

    # ── 6. Move popularity ────────────────────────────────────────────────────
    moves_pop = db.execute(text("""
        SELECT
            mv.name,
            mt.name AS move_type,
            mv.move_category,
            mv.energy_cost,
            mv.power,
            COUNT(*) AS slot_usage,
            COUNT(DISTINCT um.team_id) AS team_count
        FROM user_monsters um
        JOIN moves mv ON mv.id IN (um.move1_id, um.move2_id, um.move3_id, um.move4_id)
        JOIN types mt ON mv.move_type_id = mt.id
        WHERE um.team_id = ANY(:ids)
        GROUP BY mv.id, mv.name, mt.name, mv.move_category, mv.energy_cost, mv.power
        ORDER BY slot_usage DESC
        LIMIT 30
    """), {"ids": user_team_ids}).fetchall()
    data["moves"] = moves_pop

    # ── 7. Personality popularity ──────────────────────────────────────────────
    personalities = db.execute(text("""
        SELECT
            p.name,
            COUNT(um.id) AS usage_count
        FROM user_monsters um
        JOIN personalities p ON um.personality_id = p.id
        WHERE um.team_id = ANY(:ids)
        GROUP BY p.id, p.name
        ORDER BY usage_count DESC
    """), {"ids": user_team_ids}).fetchall()
    data["personalities"] = personalities

    # ── 8. Per-monster personality breakdown (top 10 monsters only) ───────────
    # Which personality does each popular monster most often use?
    per_monster_personality = db.execute(text("""
        SELECT monster_name, personality, cnt, rnk FROM (
            SELECT
                m.name AS monster_name,
                p.name AS personality,
                COUNT(*) AS cnt,
                SUM(COUNT(*)) OVER (PARTITION BY m.name) AS monster_total,
                RANK() OVER (PARTITION BY m.name ORDER BY COUNT(*) DESC) AS rnk
            FROM user_monsters um
            JOIN monsters m ON um.monster_id = m.id
            JOIN personalities p ON um.personality_id = p.id
            WHERE um.team_id = ANY(:ids)
              AND m.name IN (
                SELECT m2.name
                FROM user_monsters um2
                JOIN monsters m2 ON um2.monster_id = m2.id
                WHERE um2.team_id = ANY(:ids)
                GROUP BY m2.name
                ORDER BY COUNT(*) DESC
                LIMIT 20
              )
            GROUP BY m.name, p.name
        ) sub
        WHERE rnk <= 3
        ORDER BY monster_total DESC, monster_name, rnk
    """), {"ids": user_team_ids}).fetchall()
    data["per_monster_personality"] = per_monster_personality

    # ── 9. Legacy type popularity ────────────────────────────────────────────
    legacy_types = db.execute(text("""
        SELECT
            t.name AS legacy_type,
            COUNT(um.id) AS usage_count
        FROM user_monsters um
        JOIN types t ON um.legacy_type_id = t.id
        WHERE um.team_id = ANY(:ids)
        GROUP BY t.id, t.name
        ORDER BY usage_count DESC
    """), {"ids": user_team_ids}).fetchall()
    data["legacy_types"] = legacy_types

    # ── 10. Per-monster legacy type choice ────────────────────────────────────
    per_monster_legacy = db.execute(text("""
        SELECT monster_name, legacy_type, cnt, rnk FROM (
            SELECT
                m.name AS monster_name,
                t.name AS legacy_type,
                COUNT(*) AS cnt,
                SUM(COUNT(*)) OVER (PARTITION BY m.name) AS monster_total,
                RANK() OVER (PARTITION BY m.name ORDER BY COUNT(*) DESC) AS rnk
            FROM user_monsters um
            JOIN monsters m ON um.monster_id = m.id
            JOIN types t ON um.legacy_type_id = t.id
            WHERE um.team_id = ANY(:ids)
              AND m.name IN (
                SELECT m2.name FROM user_monsters um2
                JOIN monsters m2 ON um2.monster_id = m2.id
                WHERE um2.team_id = ANY(:ids)
                GROUP BY m2.name ORDER BY COUNT(*) DESC LIMIT 20
              )
            GROUP BY m.name, t.name
        ) sub
        WHERE rnk <= 3
        ORDER BY monster_total DESC, monster_name, rnk
    """), {"ids": user_team_ids}).fetchall()
    data["per_monster_legacy"] = per_monster_legacy

    # ── 11. Move choices per popular monster ──────────────────────────────────
    per_monster_moves = db.execute(text("""
        SELECT monster_name, move_name, move_type, move_category, cnt, rnk FROM (
            SELECT
                m.name AS monster_name,
                mv.name AS move_name,
                mt.name AS move_type,
                mv.move_category,
                COUNT(*) AS cnt,
                SUM(COUNT(*)) OVER (PARTITION BY m.name) AS monster_total,
                RANK() OVER (PARTITION BY m.name ORDER BY COUNT(*) DESC) AS rnk
            FROM user_monsters um
            JOIN monsters m ON um.monster_id = m.id
            JOIN moves mv ON mv.id IN (um.move1_id, um.move2_id, um.move3_id, um.move4_id)
            JOIN types mt ON mv.move_type_id = mt.id
            WHERE um.team_id = ANY(:ids)
              AND m.name IN (
                SELECT m2.name FROM user_monsters um2
                JOIN monsters m2 ON um2.monster_id = m2.id
                WHERE um2.team_id = ANY(:ids)
                GROUP BY m2.name ORDER BY COUNT(*) DESC LIMIT 20
              )
            GROUP BY m.name, mv.name, mt.name, mv.move_category
        ) sub
        WHERE rnk <= 5
        ORDER BY monster_total DESC, monster_name, rnk
    """), {"ids": user_team_ids}).fetchall()
    data["per_monster_moves"] = per_monster_moves

    # ── 12. Type coverage on teams ────────────────────────────────────────────
    # Group by team first, then aggregate the combo strings across teams.
    type_coverage2 = db.execute(text("""
        SELECT type_combo, COUNT(*) AS team_count
        FROM (
            SELECT team_id, STRING_AGG(type_name, ',' ORDER BY type_name) AS type_combo
            FROM (
                SELECT DISTINCT um.team_id, t.name AS type_name
                FROM user_monsters um
                JOIN monsters m ON um.monster_id = m.id
                JOIN types t ON m.main_type_id = t.id
                WHERE um.team_id = ANY(:ids)
            ) deduped
            GROUP BY team_id
        ) sub
        GROUP BY type_combo
        ORDER BY team_count DESC
        LIMIT 20
    """), {"ids": user_team_ids}).fetchall()
    data["type_coverage"] = type_coverage2

    # ── 13. Talent allocation patterns ────────────────────────────────────────
    # All valid monsters have at least 1 stat boosted and at most 3 (enforced by
    # validateSlot: b===0 → error, b>3 → error). So we analyze:
    #   a) Which stats are most often chosen to receive any boost (binary frequency)
    #   b) How many stats per monster (1, 2, or 3) — budget spread preference
    #   c) Average boost value per stat, excluding monsters that left that stat at 0

    # a) Per-stat "chosen" frequency (how many monsters boosted that stat at all)
    talent_freq = db.execute(text("""
        SELECT
            SUM(CASE WHEN tl.hp_boost      > 0 THEN 1 ELSE 0 END) AS hp_chosen,
            SUM(CASE WHEN tl.phy_atk_boost > 0 THEN 1 ELSE 0 END) AS phy_atk_chosen,
            SUM(CASE WHEN tl.mag_atk_boost > 0 THEN 1 ELSE 0 END) AS mag_atk_chosen,
            SUM(CASE WHEN tl.phy_def_boost > 0 THEN 1 ELSE 0 END) AS phy_def_chosen,
            SUM(CASE WHEN tl.mag_def_boost > 0 THEN 1 ELSE 0 END) AS mag_def_chosen,
            SUM(CASE WHEN tl.spd_boost     > 0 THEN 1 ELSE 0 END) AS spd_chosen,
            COUNT(tl.id) AS total_monsters
        FROM talents tl
        JOIN user_monsters um ON tl.monster_instance_id = um.id
        WHERE um.team_id = ANY(:ids)
    """), {"ids": user_team_ids}).fetchone()
    data["talent_freq"] = talent_freq

    # b) Distribution: how many stats does each monster boost (1, 2, or 3)?
    talent_spread = db.execute(text("""
        SELECT stats_boosted, COUNT(*) AS monster_count
        FROM (
            SELECT tl.id,
                (CASE WHEN tl.hp_boost      > 0 THEN 1 ELSE 0 END +
                 CASE WHEN tl.phy_atk_boost > 0 THEN 1 ELSE 0 END +
                 CASE WHEN tl.mag_atk_boost > 0 THEN 1 ELSE 0 END +
                 CASE WHEN tl.phy_def_boost > 0 THEN 1 ELSE 0 END +
                 CASE WHEN tl.mag_def_boost > 0 THEN 1 ELSE 0 END +
                 CASE WHEN tl.spd_boost     > 0 THEN 1 ELSE 0 END) AS stats_boosted
            FROM talents tl
            JOIN user_monsters um ON tl.monster_instance_id = um.id
            WHERE um.team_id = ANY(:ids)
        ) sub
        GROUP BY stats_boosted
        ORDER BY stats_boosted
    """), {"ids": user_team_ids}).fetchall()
    data["talent_spread"] = talent_spread

    # c) Average boost amount per stat, only among monsters that chose that stat
    talent_avg = db.execute(text("""
        SELECT
            ROUND(AVG(CASE WHEN hp_boost      > 0 THEN hp_boost      END), 1) AS avg_hp_when_chosen,
            ROUND(AVG(CASE WHEN phy_atk_boost > 0 THEN phy_atk_boost END), 1) AS avg_phy_atk_when_chosen,
            ROUND(AVG(CASE WHEN mag_atk_boost > 0 THEN mag_atk_boost END), 1) AS avg_mag_atk_when_chosen,
            ROUND(AVG(CASE WHEN phy_def_boost > 0 THEN phy_def_boost END), 1) AS avg_phy_def_when_chosen,
            ROUND(AVG(CASE WHEN mag_def_boost > 0 THEN mag_def_boost END), 1) AS avg_mag_def_when_chosen,
            ROUND(AVG(CASE WHEN spd_boost     > 0 THEN spd_boost     END), 1) AS avg_spd_when_chosen
        FROM talents tl
        JOIN user_monsters um ON tl.monster_instance_id = um.id
        WHERE um.team_id = ANY(:ids)
    """), {"ids": user_team_ids}).fetchone()
    data["talent_avg"] = talent_avg

    # ── 14. User behavior: team counts ────────────────────────────────────────
    teams_per_user = db.execute(text("""
        SELECT
            owner_id,
            COUNT(*) AS team_count
        FROM teams
        WHERE id = ANY(:ids)
        GROUP BY owner_id
        ORDER BY team_count DESC
    """), {"ids": user_team_ids}).fetchall()
    data["teams_per_user"] = teams_per_user

    # ── 15. Meta teams ────────────────────────────────────────────────────────
    # Level 1: Most common 6-monster compositions (monsters only, order-insensitive).
    # We sort the 6 monster names alphabetically to canonicalize order before grouping.
    meta_teams_loose = db.execute(text("""
        SELECT monster_combo, COUNT(*) AS team_count
        FROM (
            SELECT team_id,
                STRING_AGG(m.name, ',' ORDER BY m.name) AS monster_combo
            FROM user_monsters um
            JOIN monsters m ON um.monster_id = m.id
            WHERE um.team_id = ANY(:ids)
            GROUP BY team_id
        ) sub
        GROUP BY monster_combo
        ORDER BY team_count DESC
        LIMIT 20
    """), {"ids": user_team_ids}).fetchall()
    data["meta_teams_loose"] = meta_teams_loose

    # Level 2: Exact composition — monster + magic item + all 6 move sets +
    # personality + legacy type per slot (talents excluded as too granular).
    # Slots are canonicalized by sorting on monster name so order doesn't matter.
    meta_teams_exact = db.execute(text("""
        SELECT full_combo, magic_item, COUNT(*) AS team_count
        FROM (
            SELECT
                t.id AS team_id,
                mi.name AS magic_item,
                STRING_AGG(
                    m.name || '|' ||
                    p.name || '|' ||
                    lt.name || '|' ||
                    COALESCE(mv1.name,'') || '|' ||
                    COALESCE(mv2.name,'') || '|' ||
                    COALESCE(mv3.name,'') || '|' ||
                    COALESCE(mv4.name,''),
                    ';;'
                    ORDER BY m.name, p.name
                ) AS full_combo
            FROM teams t
            JOIN magic_items mi ON t.magic_item_id = mi.id
            JOIN user_monsters um ON um.team_id = t.id
            JOIN monsters m ON um.monster_id = m.id
            JOIN personalities p ON um.personality_id = p.id
            JOIN types lt ON um.legacy_type_id = lt.id
            LEFT JOIN moves mv1 ON mv1.id = um.move1_id
            LEFT JOIN moves mv2 ON mv2.id = um.move2_id
            LEFT JOIN moves mv3 ON mv3.id = um.move3_id
            LEFT JOIN moves mv4 ON mv4.id = um.move4_id
            WHERE t.id = ANY(:ids)
            GROUP BY t.id, mi.name
        ) combos
        GROUP BY full_combo, magic_item
        HAVING COUNT(*) > 1
        ORDER BY team_count DESC
        LIMIT 20
    """), {"ids": user_team_ids}).fetchall()
    data["meta_teams_exact"] = meta_teams_exact

    # ── 16. User tier distribution ────────────────────────────────────────────
    tier_dist = db.execute(text("""
        SELECT subscription_tier, COUNT(*) FROM users
        WHERE is_guest = false
        GROUP BY subscription_tier ORDER BY COUNT(*) DESC
    """)).fetchall()
    data["tier_dist"] = tier_dist

    # ── 18. User language preferences ─────────────────────────────────────────
    lang_pref = db.execute(text("""
        SELECT preferred_language, COUNT(*) FROM users
        WHERE is_guest = false
        GROUP BY preferred_language ORDER BY COUNT(*) DESC
    """)).fetchall()
    data["lang_pref"] = lang_pref

    data["_total_user_teams"] = T
    data["_generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return data


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def render(data: dict) -> str:
    T = data["_total_user_teams"]
    s = data["scope"]
    lines = []

    def h1(title): lines.append(f"\n# {title}\n")
    def h2(title): lines.append(f"\n## {title}\n")
    def h3(title): lines.append(f"\n### {title}\n")
    def p(text):   lines.append(text)
    def blank():   lines.append("")

    # ── Header ────────────────────────────────────────────────────────────────
    lines.append(f"# Roco Kingdom Team Builder — Popularity Analysis Report")
    lines.append(f"")
    lines.append(f"Generated: **{data['_generated_at']}**  ")
    lines.append(f"Analysis scope: **user-created teams with exactly 6 monsters, magic item, ≥1 talent stat nonzero per monster** (featured/admin teams excluded)")
    lines.append(f"")

    # ── 0. Overview ───────────────────────────────────────────────────────────
    h1("0. Overview")
    p(f"| Metric | Value |")
    p(f"| --- | --- |")
    p(f"| Total teams (all, incl. featured) | {s['total_teams_all']} |")
    p(f"| User teams (scope of this report) | {s['total_teams_user']} |")
    p(f"| Featured (admin-curated) teams | {s['total_featured']} |")
    p(f"| Total registered users | {s['total_registered']} |")
    p(f"| Total guest users | {s['total_guest']} |")
    p(f"| Users who have saved ≥1 team | {s['total_users_with_teams']} |")
    blank()

    # ── 1. Monster popularity (top 30) ────────────────────────────────────────
    h1("1. Monster Popularity")
    h2("1a. By Monster Form (exact)")
    total_um = T * 6 or 1  # all teams have exactly 6 monsters
    p(f"Total user monster slots: **{total_um}**")
    blank()
    p("| Rank | Monster | Form | Types | Used in slots | % of slots | Teams using |")
    p("| --- | --- | --- | --- | --- | --- | --- |")
    for i, r in enumerate(data["monster_usage"][:30], 1):
        types = r.main_type + (f"/{r.sub_type}" if r.sub_type else "")
        p(f"| {i} | {r.name} | {r.form} | {types} | {r.usage_count} | {pct(r.usage_count, total_um)} | {r.team_count} |")
    blank()

    h2("1b. By Species (all forms combined)")
    p("| Rank | Species | Used in slots | % of slots | # distinct teams | # forms used |")
    p("| --- | --- | --- | --- | --- | --- |")
    for i, r in enumerate(data["species_usage"][:20], 1):
        p(f"| {i} | {r.species_name} | {r.usage_count} | {pct(r.usage_count, total_um)} | {r.team_count} | {r.form_count} |")
    blank()

    # ── 2. Pairings & Trios ───────────────────────────────────────────────────
    h1("2. Team Composition Patterns")
    h2("2a. Most Common Monster Pairs")
    p("| Rank | Monster A | Monster B | Times together |")
    p("| --- | --- | --- | --- |")
    for i, r in enumerate(data["pairs"], 1):
        p(f"| {i} | {r.mon_a} | {r.mon_b} | {r.pair_count} |")
    blank()

    h2("2b. Most Common Monster Trios (full team combos)")
    p("| Rank | A | B | C | Times together |")
    p("| --- | --- | --- | --- | --- |")
    for i, r in enumerate(data["trios"], 1):
        p(f"| {i} | {r.mon_a} | {r.mon_b} | {r.mon_c} | {r.trio_count} |")
    blank()

    # ── 3. Type Coverage ──────────────────────────────────────────────────────
    h1("3. Team Type Coverage Patterns")
    p("Main type combinations used in the same team (sorted by frequency).")
    blank()
    p("| Rank | Types in team | # Teams | % |")
    p("| --- | --- | --- | --- |")
    for i, r in enumerate(data["type_coverage"][:15], 1):
        p(f"| {i} | {r.type_combo} | {r.team_count} | {pct(r.team_count, T)} |")
    blank()

    # ── 4. Magic Items ────────────────────────────────────────────────────────
    h1("4. Magic Item Usage")
    p("All teams have a magic item (required before saving).")
    blank()
    p("| Rank | Magic Item | Effect Code | # Teams | % of all teams |")
    p("| --- | --- | --- | --- | --- |")
    for i, r in enumerate(data["magic_items"], 1):
        p(f"| {i} | {r.name} | {r.effect_code} | {r.usage_count} | {float(r.pct):.1f}% |")
    blank()

    # ── 5. Moves ──────────────────────────────────────────────────────────────
    h1("5. Move Popularity (Top 30)")
    p("Counts how many move slots across all monsters use each move (one monster can use a move in at most 1 slot).")
    blank()
    p("| Rank | Move | Type | Category | Energy | Power | Slot uses | Teams |")
    p("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for i, r in enumerate(data["moves"], 1):
        power = r.power if r.power else "—"
        p(f"| {i} | {r.name} | {r.move_type} | {r.move_category} | {r.energy_cost} | {power} | {r.slot_usage} | {r.team_count} |")
    blank()

    # ── 6. Per-monster move preferences ───────────────────────────────────────
    h1("6. Per-Monster Move Preferences (Top 20 monsters)")
    p("Top 5 most-chosen moves for each of the 20 most popular monsters, ordered by monster popularity.")
    blank()
    current_monster = None
    for r in data["per_monster_moves"]:
        if r.monster_name != current_monster:
            current_monster = r.monster_name
            h3(f"{current_monster}")
            p("| Rank | Move | Type | Category | # Times chosen |")
            p("| --- | --- | --- | --- | --- |")
        p(f"| {r.rnk} | {r.move_name} | {r.move_type} | {r.move_category} | {r.cnt} |")
    blank()

    # ── 7. Personalities ──────────────────────────────────────────────────────
    h1("7. Personality Usage")
    h2("7a. Overall personality popularity")
    p("| Rank | Personality | # Monster slots | % |")
    p("| --- | --- | --- | --- |")
    for i, r in enumerate(data["personalities"], 1):
        p(f"| {i} | {r.name} | {r.usage_count} | {pct(r.usage_count, total_um)} |")
    blank()

    h2("7b. Per-monster top personalities (Top 20 monsters, ordered by popularity)")
    current_monster = None
    for r in data["per_monster_personality"]:
        if r.monster_name != current_monster:
            current_monster = r.monster_name
            h3(f"{current_monster}")
            p("| Rank | Personality | # Times chosen |")
            p("| --- | --- | --- |")
        p(f"| {r.rnk} | {r.personality} | {r.cnt} |")
    blank()

    # ── 8. Legacy Types ───────────────────────────────────────────────────────
    h1("8. Legacy Type Choices")
    h2("8a. Overall legacy type popularity")
    p("| Rank | Legacy Type | # Monster slots | % |")
    p("| --- | --- | --- | --- |")
    for i, r in enumerate(data["legacy_types"], 1):
        p(f"| {i} | {r.legacy_type} | {r.usage_count} | {pct(r.usage_count, total_um)} |")
    blank()

    h2("8b. Per-monster top legacy type choices (Top 20 monsters, ordered by popularity)")
    current_monster = None
    for r in data["per_monster_legacy"]:
        if r.monster_name != current_monster:
            current_monster = r.monster_name
            h3(f"{current_monster}")
            p("| Rank | Legacy Type | # Times chosen |")
            p("| --- | --- | --- |")
        p(f"| {r.rnk} | {r.legacy_type} | {r.cnt} |")
    blank()

    # ── 9. Talent Allocation ─────────────────────────────────────────────────
    h1("9. Talent Allocation")
    p("Rules: each monster must boost ≥1 stat and ≤3 stats (enforced at save time).")
    blank()

    tf = data["talent_freq"]
    if tf and tf.total_monsters:
        N = tf.total_monsters
        h2("9a. Which stats do users boost? (% of all monsters that boosted each stat)")
        p("| Stat | # Monsters boosted it | % |")
        p("| --- | --- | --- |")
        p(f"| HP | {tf.hp_chosen} | {pct(tf.hp_chosen, N)} |")
        p(f"| Phys ATK | {tf.phy_atk_chosen} | {pct(tf.phy_atk_chosen, N)} |")
        p(f"| Magic ATK | {tf.mag_atk_chosen} | {pct(tf.mag_atk_chosen, N)} |")
        p(f"| Phys DEF | {tf.phy_def_chosen} | {pct(tf.phy_def_chosen, N)} |")
        p(f"| Magic DEF | {tf.mag_def_chosen} | {pct(tf.mag_def_chosen, N)} |")
        p(f"| Speed | {tf.spd_chosen} | {pct(tf.spd_chosen, N)} |")
        blank()

        h2("9b. How many stats per monster? (budget spread preference)")
        p("| Stats boosted | # Monsters | % |")
        p("| --- | --- | --- |")
        for r in data["talent_spread"]:
            p(f"| {r[0]} | {r[1]} | {pct(r[1], N)} |")
        blank()

        ta = data["talent_avg"]
        h2("9c. Average boost amount (only among monsters that chose each stat)")
        p("*Excludes zeros — shows how much users invest when they do pick a stat.*")
        blank()
        p("| Stat | Avg boost when chosen |")
        p("| --- | --- |")
        p(f"| HP | {ta.avg_hp_when_chosen} |")
        p(f"| Phys ATK | {ta.avg_phy_atk_when_chosen} |")
        p(f"| Magic ATK | {ta.avg_mag_atk_when_chosen} |")
        p(f"| Phys DEF | {ta.avg_phy_def_when_chosen} |")
        p(f"| Magic DEF | {ta.avg_mag_def_when_chosen} |")
        p(f"| Speed | {ta.avg_spd_when_chosen} |")
    blank()

    # ── 10. User Behavior ────────────────────────────────────────────────────
    h1("10. User Behavior")
    tpu = [r.team_count for r in data["teams_per_user"]]
    total_users = s["total_registered"] + s["total_guest"]
    users_with_zero = total_users - len(tpu)
    p(f"- Total users: **{total_users}**")
    p(f"- Users with ≥1 qualifying team: **{len(tpu)}**")
    if tpu:
        p(f"- Max teams by one user: **{max(tpu)}**")
        p(f"- Avg teams per user (among those with teams): **{sum(tpu)/len(tpu):.1f}**")
        p(f"- Median teams per user (among those with teams): **{sorted(tpu)[len(tpu)//2]}**")
    blank()
    buckets = [(0,0),(1,1),(2,3),(4,9),(10,20)]
    p("| Teams saved | # Users | % of all users |")
    p("| --- | --- | --- |")
    zero_c = users_with_zero
    p(f"| 0 | {zero_c} | {pct(zero_c, total_users)} |")
    for lo, hi in buckets[1:]:
        c = sum(1 for x in tpu if lo <= x <= hi)
        label = str(lo) if lo == hi else f"{lo}–{hi}"
        p(f"| {label} | {c} | {pct(c, total_users)} |")
    blank()

    # ── 11. User Demographics ────────────────────────────────────────────────
    h1("11. User Demographics")
    h2("11a. Subscription tiers (registered users only)")
    p("| Tier | # Users |")
    p("| --- | --- |")
    for r in data["tier_dist"]:
        p(f"| {r[0]} | {r[1]} |")
    blank()

    h2("11b. Language preference (registered users only)")
    p("| Language | # Users |")
    p("| --- | --- |")
    for r in data["lang_pref"]:
        p(f"| {r[0]} | {r[1]} |")
    blank()

    # ── 12. Meta Teams ───────────────────────────────────────────────────────
    h1("12. Meta Teams")
    p("Identifies teams that appear frequently across the player base.")
    blank()

    h2("12a. Most Common 6-Monster Rosters (monsters only, order-insensitive)")
    p("Two teams match if they contain the same 6 monsters regardless of slot order, personality, moves, or magic item.")
    blank()
    ml = data["meta_teams_loose"]
    if ml:
        p("| Rank | Monsters (alphabetical) | # Teams |  % of all teams |")
        p("| --- | --- | --- | --- |")
        for i, r in enumerate(ml, 1):
            # Format: comma-separated monster names from the aggregated string
            monsters = r.monster_combo  # already comma-separated from STRING_AGG
            p(f"| {i} | {monsters} | {r.team_count} | {pct(r.team_count, T)} |")
    else:
        p("*No repeated rosters found.*")
    blank()

    h2("12b. Exact Duplicate Teams (same monsters + magic item + all movesets + personalities + legacy types)")
    p("Only teams appearing more than once are shown. Talents are excluded (too granular to expect exact matches).")
    blank()
    me = data["meta_teams_exact"]
    if me:
        for i, r in enumerate(me, 1):
            h3(f"#{i} — appears {r.team_count} times | Magic Item: {r.magic_item}")
            # full_combo: slots separated by ';;', fields within each slot separated by '|'
            # fields: monster|personality|legacy|mv1|mv2|mv3|mv4
            slots = r.full_combo.split(";;")
            p("| # | Monster | Personality | Legacy | Move 1 | Move 2 | Move 3 | Move 4 |")
            p("| --- | --- | --- | --- | --- | --- | --- | --- |")
            for j, slot in enumerate(slots, 1):
                parts = slot.split("|")
                mon  = parts[0] if len(parts) > 0 else "—"
                pers = parts[1] if len(parts) > 1 else "—"
                leg  = parts[2] if len(parts) > 2 else "—"
                mv1  = parts[3] if len(parts) > 3 and parts[3] else "—"
                mv2  = parts[4] if len(parts) > 4 and parts[4] else "—"
                mv3  = parts[5] if len(parts) > 5 and parts[5] else "—"
                mv4  = parts[6] if len(parts) > 6 and parts[6] else "—"
                p(f"| {j} | {mon} | {pers} | {leg} | {mv1} | {mv2} | {mv3} | {mv4} |")
            blank()
    else:
        p("*No exact duplicate teams found — all teams are unique at this detail level.*")
    blank()

    # ── Footer ────────────────────────────────────────────────────────────────
    lines.append("---")
    lines.append(f"*Generated by `backend/scripts/analysis/team_popularity_report.py` on {data['_generated_at']}*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    out_path = Path("team_popularity_report.md")
    print(f"Connecting to database...", flush=True)

    with Session() as db:
        print("Collecting data...", flush=True)
        try:
            data = collect(db)
        except Exception as e:
            print(f"ERROR during data collection: {e}", file=sys.stderr)
            raise

    print("Rendering report...", flush=True)
    report = render(data)

    out_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to: {out_path.resolve()}")
    print(f"  Scope: {data['_total_user_teams']} user teams")
    print(f"  Generated: {data['_generated_at']}")
