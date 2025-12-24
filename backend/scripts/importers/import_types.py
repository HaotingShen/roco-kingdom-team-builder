import json
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from backend.models import Base, Type
from backend.config import DATABASE_URL
from sqlalchemy import create_engine

TYPES_JSON_PATH = "backend/data/types.json"

engine = create_engine(DATABASE_URL)

def load_types():
    with open(TYPES_JSON_PATH, encoding="utf-8") as f:
        types_data = json.load(f)

    # Step 1: Insert/update all types (idempotent upsert)
    with Session(engine) as session:
        name_to_id = {}
        for item in types_data:
            stmt = insert(Type).values(
                name=item["name"],
                localized=item["localized"]
            ).on_conflict_do_update(
                index_elements=["name"],
                set_={"localized": item["localized"]}
            ).returning(Type.id, Type.name)
            result = session.execute(stmt)
            row = result.first()
            name_to_id[item["name"]] = row[0]  # Map type name to DB id

        session.commit()

        # Step 2: Now handle the association tables (idempotent)
        session.execute(text("DELETE FROM type_effective_against"))
        session.execute(text("DELETE FROM type_weak_against"))
        session.commit()

        # Re-create associations based on JSON
        for item in types_data:
            this_id = name_to_id[item["name"]]
            for eff in item.get("effective_against", []):
                target_id = name_to_id.get(eff)
                if target_id:
                    session.execute(
                        text("INSERT INTO type_effective_against (type_id, target_type_id) VALUES (:tid, :tid2) ON CONFLICT DO NOTHING"),
                        {"tid": this_id, "tid2": target_id}
                    )
            for weak in item.get("weak_against", []):
                target_id = name_to_id.get(weak)
                if target_id:
                    session.execute(
                        text("INSERT INTO type_weak_against (type_id, target_type_id) VALUES (:tid, :tid2) ON CONFLICT DO NOTHING"),
                        {"tid": this_id, "tid2": target_id}
                    )
        session.commit()
        print("Types and associations imported successfully!")

def main():
    load_types()

if __name__ == "__main__":
    main()