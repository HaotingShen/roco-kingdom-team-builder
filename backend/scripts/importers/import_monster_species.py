import json
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from backend.models import MonsterSpecies
from backend.config import DATABASE_URL
from sqlalchemy import create_engine

SPECIES_JSON_PATH = "backend/data/monster_species.json"

engine = create_engine(DATABASE_URL)

def load_monster_species():
    with open(SPECIES_JSON_PATH, encoding="utf-8") as f:
        species_data = json.load(f)

    with Session(engine) as session:
        for item in species_data:
            stmt = insert(MonsterSpecies).values(
                name=item["name"],
                localized=item["localized"]
            ).on_conflict_do_update(
                index_elements=["name"],
                set_={
                    "localized": item["localized"]
                }
            )
            session.execute(stmt)
        session.commit()
        print("Monster species imported successfully!")

def main():
    load_monster_species()

if __name__ == "__main__":
    main()