import json
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, delete
from backend.models import Status, Move, move_statuses, StatusUsage, StatusAffect
from backend.config import DATABASE_URL

STATUSES_JSON_PATH = "backend/data/statuses.json"

engine = create_engine(DATABASE_URL)


def load_statuses():
    """
    Import move-centric statuses.json.

    Each entry has { "move": "...", "status_name": "...", "zh_name": "...", ...boosts, "usage": "...", "affect": "..." }.
    Multiple entries can share a status_name (same status granted by multiple moves).
    """
    with open(STATUSES_JSON_PATH, encoding="utf-8") as f:
        entries = json.load(f)

    # Group entries by status_name to dedupe statuses.
    # First occurrence defines the boost values; converter already validated consistency.
    unique_statuses: dict[str, dict] = {}
    status_moves: dict[str, list[str]] = {}

    for entry in entries:
        name = entry["status_name"]
        move = entry["move"]

        if name not in unique_statuses:
            unique_statuses[name] = entry
            status_moves[name] = []
        status_moves[name].append(move)

    with Session(engine) as session:
        move_name_to_id = {m.name: m.id for m in session.query(Move).all()}

        # Upsert each unique status
        for name, entry in unique_statuses.items():
            localized = {}
            zh_name = entry.get("zh_name")
            if zh_name:
                localized = {"zh": {"name": zh_name}}

            values = dict(
                name=name,
                localized=localized,
                hp_boost=0,
                phy_atk_boost=entry.get("phy_atk_boost", 0),
                mag_atk_boost=entry.get("mag_atk_boost", 0),
                phy_def_boost=entry.get("phy_def_boost", 0),
                mag_def_boost=entry.get("mag_def_boost", 0),
                spd_boost=entry.get("spd_boost", 0),
                flat_power_boost=entry.get("flat_power_boost", 0),
                pct_power_boost=entry.get("pct_power_boost", 0),
                combo_bonus=entry.get("combo_bonus", 0),
                dmg_reduction_pct=entry.get("dmg_reduction_pct", 0.0),
                dmg_bonus_pct=entry.get("dmg_bonus_pct", 0.0),
                usage=StatusUsage(entry.get("usage", "all")),
                affect=StatusAffect(entry.get("affect", "self")),
            )

            stmt = insert(Status).values(**values).on_conflict_do_update(
                index_elements=["name"],
                set_={k: v for k, v in values.items() if k != "name"},
            )
            session.execute(stmt)

        session.flush()

        # Rebuild move_statuses associations
        session.execute(delete(move_statuses))
        status_name_to_id = {s.name: s.id for s in session.query(Status).all()}

        links = 0
        for name, move_names in status_moves.items():
            status_id = status_name_to_id[name]
            for move_name in move_names:
                move_id = move_name_to_id.get(move_name)
                if move_id is None:
                    print(f"  WARNING: move '{move_name}' not found, skipping link to status '{name}'")
                    continue
                session.execute(
                    insert(move_statuses).values(
                        move_id=move_id, status_id=status_id
                    ).on_conflict_do_nothing()
                )
                links += 1

        session.commit()
        print(f"Statuses imported: {len(unique_statuses)} statuses, {links} move-status links.")


def main():
    load_statuses()


if __name__ == "__main__":
    main()
