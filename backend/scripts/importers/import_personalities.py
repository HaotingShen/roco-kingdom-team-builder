import json
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from backend.models import Personality
from backend.config import DATABASE_URL
from sqlalchemy import create_engine

PERSONALITIES_JSON_PATH = "backend/data/personalities.json"

engine = create_engine(DATABASE_URL)

def load_personalities():
    with open(PERSONALITIES_JSON_PATH, encoding="utf-8") as f:
        personalities_data = json.load(f)

    with Session(engine) as session:
        for item in personalities_data:
            stmt = insert(Personality).values(
                name=item["name"],
                hp_mod_pct=item.get("hp_mod_pct", 0.0),
                phy_atk_mod_pct=item.get("phy_atk_mod_pct", 0.0),
                mag_atk_mod_pct=item.get("mag_atk_mod_pct", 0.0),
                phy_def_mod_pct=item.get("phy_def_mod_pct", 0.0),
                mag_def_mod_pct=item.get("mag_def_mod_pct", 0.0),
                spd_mod_pct=item.get("spd_mod_pct", 0.0),
                localized=item["localized"]
            ).on_conflict_do_update(
                index_elements=["name"],
                set_={
                    "hp_mod_pct": item.get("hp_mod_pct", 0.0),
                    "phy_atk_mod_pct": item.get("phy_atk_mod_pct", 0.0),
                    "mag_atk_mod_pct": item.get("mag_atk_mod_pct", 0.0),
                    "phy_def_mod_pct": item.get("phy_def_mod_pct", 0.0),
                    "mag_def_mod_pct": item.get("mag_def_mod_pct", 0.0),
                    "spd_mod_pct": item.get("spd_mod_pct", 0.0),
                    "localized": item["localized"]
                }
            )
            session.execute(stmt)
        session.commit()
        print("Personalities imported successfully!")

def main():
    load_personalities()

if __name__ == "__main__":
    main()