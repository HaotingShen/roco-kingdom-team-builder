import json
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from backend.models import MagicItem, Type, MagicEffectCode
from backend.config import DATABASE_URL
from sqlalchemy import create_engine

MAGIC_ITEMS_JSON_PATH = "backend/data/magic_items.json"

engine = create_engine(DATABASE_URL)

def load_magic_items():
    with open(MAGIC_ITEMS_JSON_PATH, encoding="utf-8") as f:
        items_data = json.load(f)

    with Session(engine) as session:
        # Build type name -> id map
        type_name_to_id = {t.name: t.id for t in session.query(Type).all()}

        for item in items_data:
            # Resolve type FK if present
            applies_to_type_id = None
            applies_to_type = item.get("applies_to_type")
            if applies_to_type:
                applies_to_type_id = type_name_to_id.get(applies_to_type)
                if not applies_to_type_id:
                    raise ValueError(f"Type '{applies_to_type}' in magic_items.json not found in DB.")

            stmt = insert(MagicItem).values(
                name=item["name"],
                description=item["description"],
                effect_code=MagicEffectCode[item["effect_code"]],
                applies_to_type_id=applies_to_type_id,
                effect_parameters=item.get("effect_parameters"),
                localized=item["localized"]
            ).on_conflict_do_update(
                index_elements=["name"],
                set_={
                    "description": item["description"],
                    "effect_code": MagicEffectCode[item["effect_code"]],
                    "applies_to_type_id": applies_to_type_id,
                    "effect_parameters": item.get("effect_parameters"),
                    "localized": item["localized"]
                }
            )
            session.execute(stmt)
        session.commit()
        print("Magic items imported successfully!")

def main():
    load_magic_items()

if __name__ == "__main__":
    main()