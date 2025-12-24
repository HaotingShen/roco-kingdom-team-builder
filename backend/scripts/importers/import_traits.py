import json
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from backend.models import Trait
from backend.config import DATABASE_URL
from sqlalchemy import create_engine

TRAITS_JSON_PATH = "backend/data/traits.json"

engine = create_engine(DATABASE_URL)

def load_traits():
    with open(TRAITS_JSON_PATH, encoding="utf-8") as f:
        traits_data = json.load(f)

    with Session(engine) as session:
        for item in traits_data:
            stmt = insert(Trait).values(
                name=item["name"],
                description=item["description"],
                localized=item["localized"]
            ).on_conflict_do_update(
                index_elements=["name"],
                set_={
                    "description": item["description"],
                    "localized": item["localized"]
                }
            )
            session.execute(stmt)
        session.commit()
        print("Traits imported successfully!")

def main():
    load_traits()

if __name__ == "__main__":
    main()