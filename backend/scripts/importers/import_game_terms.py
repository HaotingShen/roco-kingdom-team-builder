import json
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from backend.models import GameTerm
from backend.config import DATABASE_URL
from sqlalchemy import create_engine

GAME_TERMS_JSON_PATH = "backend/data/game_terms.json"

engine = create_engine(DATABASE_URL)

def load_game_terms():
    with open(GAME_TERMS_JSON_PATH, encoding="utf-8") as f:
        terms_data = json.load(f)

    with Session(engine) as session:
        for item in terms_data:
            stmt = insert(GameTerm).values(
                key=item["key"],
                description=item["description"],
                localized=item["localized"]
            ).on_conflict_do_update(
                index_elements=["key"],
                set_={
                    "description": item["description"],
                    "localized": item["localized"]
                }
            )
            session.execute(stmt)
        session.commit()
        print("Game terms imported successfully!")

def main():
    load_game_terms()

if __name__ == "__main__":
    main()