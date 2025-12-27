import json
from sqlalchemy.orm import Session
from backend.models import Monster, Move
from backend.config import DATABASE_URL
from sqlalchemy import create_engine, text

MONSTERS_JSON_PATH = "backend/data/monsters.json"
MONSTER_MOVES_JSON_PATH = "backend/data/monster_moves.json"

engine = create_engine(DATABASE_URL)

def build_move_lookup_map(session: Session) -> dict:
    """
    Build a move lookup map that accepts both English and Chinese move names.
    Returns a dict mapping move names (both EN and ZH) to move IDs.
    """
    moves = session.query(Move).all()
    move_map = {}

    for mv in moves:
        # Map English name
        move_map[mv.name] = mv.id

        # Also map Chinese name if available
        zh_name = mv.localized.get('zh', {}).get('name') if mv.localized else None
        if zh_name and isinstance(zh_name, str):
            move_map[zh_name] = mv.id

    return move_map

def load_monster_moves():
    with open(MONSTERS_JSON_PATH, encoding="utf-8") as f:
        monsters_data = json.load(f)
    with open(MONSTER_MOVES_JSON_PATH, encoding="utf-8") as f:
        monster_moves_data = json.load(f)

    with Session(engine) as session:
        # Clear old associations (idempotent)
        session.execute(text("DELETE FROM monster_moves"))

        # Build monster and move maps
        monster_by_name_and_form = {(m.name, m.form): m.id for m in session.query(Monster).all()}
        move_map = build_move_lookup_map(session)

        for monster in monsters_data:
            m_name = monster["name"]
            m_form = monster.get("form", "default")
            moveset_key = monster.get("moveset_key")
            monster_id = monster_by_name_and_form.get((m_name, m_form))
            if not moveset_key or moveset_key not in monster_moves_data:
                print(f"Warning: Monster '{m_name}' (form '{m_form}') has no valid moveset_key: {moveset_key}")
                continue

            # Collect moves separately: learnable moves and move stones
            moveset = monster_moves_data[moveset_key]

            # Insert learnable moves with position to preserve JSON order
            learnable_moves = moveset.get("learnable_moves", [])
            for position, move_name in enumerate(learnable_moves):
                move_id = move_map.get(move_name)
                if move_id is None:
                    print(f"Warning: Move '{move_name}' not found in DB for monster '{m_name}' (form '{m_form}')")
                    continue
                session.execute(
                    text("INSERT INTO monster_moves (monster_id, move_id, is_move_stone, position) VALUES (:mid, :moid, :is_stone, :pos) ON CONFLICT (monster_id, move_id) DO UPDATE SET position = :pos"),
                    {"mid": monster_id, "moid": move_id, "is_stone": False, "pos": position}
                )

            # Insert move stones with position to preserve JSON order
            move_stones = moveset.get("move_stones", [])
            for position, move_name in enumerate(move_stones):
                move_id = move_map.get(move_name)
                if move_id is None:
                    print(f"Warning: Move stone '{move_name}' not found in DB for monster '{m_name}' (form '{m_form}')")
                    continue
                session.execute(
                    text("INSERT INTO monster_moves (monster_id, move_id, is_move_stone, position) VALUES (:mid, :moid, :is_stone, :pos) ON CONFLICT (monster_id, move_id) DO UPDATE SET position = :pos"),
                    {"mid": monster_id, "moid": move_id, "is_stone": True, "pos": position}
                )
        session.commit()
        print("Monster-move associations imported successfully!")

def main():
    load_monster_moves()

if __name__ == "__main__":
    main()