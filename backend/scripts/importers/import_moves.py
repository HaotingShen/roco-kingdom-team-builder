import json
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from backend.models import Move, Type, MoveCategory
from backend.config import DATABASE_URL
from sqlalchemy import create_engine

MOVES_JSON_PATH = "backend/data/moves.json"

engine = create_engine(DATABASE_URL)

CATEGORY_MAP = {
    "Physical Attack": "PHY_ATTACK",
    "Magic Attack": "MAG_ATTACK",
    "Defense": "DEFENSE",
    "Status": "STATUS"
}

def load_moves():
    with open(MOVES_JSON_PATH, encoding="utf-8") as f:
        moves_data = json.load(f)

    with Session(engine) as session:
        # Build a type name -> id map for FK resolution
        type_name_to_id = {t.name: t.id for t in session.query(Type).all()}

        for item in moves_data:
            move_type_value = item.get("type")
            if move_type_value is None:
                move_type_id = None
            else:
                move_type_id = type_name_to_id.get(move_type_value)
                if move_type_id is None:
                    raise ValueError(f"Type '{move_type_value}' in moves.json not found in DB.")

            stmt = insert(Move).values(
                name=item["name"],
                move_type_id=move_type_id,
                move_category=MoveCategory[CATEGORY_MAP[item["category"]]],
                energy_cost=item["energy_cost"],
                power=item.get("power"),
                base_combo=item.get("base_combo"),
                description=item["description"],
                has_counter=item.get("has_counter", False),
                counter_power_multiplier=item.get("counter_power_multiplier"),
                alt_power_total=item.get("alt_power_total"),
                alt_condition_zh=item.get("alt_condition_zh"),
                alt_condition_en=item.get("alt_condition_en"),
                power_formula=item.get("power_formula"),
                localized=item["localized"]
            ).on_conflict_do_update(
                index_elements=["name"],
                set_={
                    "move_type_id": move_type_id,
                    "move_category": MoveCategory[CATEGORY_MAP[item["category"]]],
                    "energy_cost": item["energy_cost"],
                    "power": item.get("power"),
                    "base_combo": item.get("base_combo"),
                    "description": item["description"],
                    "has_counter": item.get("has_counter", False),
                    "counter_power_multiplier": item.get("counter_power_multiplier"),
                    "alt_power_total": item.get("alt_power_total"),
                    "alt_condition_zh": item.get("alt_condition_zh"),
                    "alt_condition_en": item.get("alt_condition_en"),
                    "power_formula": item.get("power_formula"),
                    "localized": item["localized"]
                }
            )
            session.execute(stmt)
        session.commit()
        print("Moves imported successfully!")

def main():
    load_moves()

if __name__ == "__main__":
    main()