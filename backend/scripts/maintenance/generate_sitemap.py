"""
Generate frontend/public/sitemap.xml from the live database.

Lists every indexable URL (homepage, dex, all jingling detail pages, all
move detail pages) so search engines can discover them without crawling
the SPA.

Workflow:
    1. Run this script against your local dev DB (or against prod via SSH tunnel)
    2. Commit the updated frontend/public/sitemap.xml
    3. Rebuild + deploy the frontend — Vite bundles public/ into the build

Re-run whenever jinglings or moves are added/removed. Pointless to run
inside the prod backend container (writes to a path that doesn't reach
the CDN-served frontend).

Usage:
    python3 -m backend.scripts.maintenance.generate_sitemap
"""

from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.config import DATABASE_URL
from backend.models import Monster, Move

BASE_URL = "https://rkteambuilder.com"

# Output path: backend/scripts/maintenance/ -> ../../../frontend/public/sitemap.xml
OUTPUT_PATH = Path(__file__).resolve().parents[3] / "frontend" / "public" / "sitemap.xml"


def url_entry(loc: str, lastmod: str, changefreq: str, priority: str) -> str:
    return (
        "  <url>\n"
        f"    <loc>{escape(loc)}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <changefreq>{changefreq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        "  </url>\n"
    )


def main():
    engine = create_engine(DATABASE_URL)
    today = date.today().isoformat()

    with Session(engine) as session:
        monster_ids = [mid for (mid,) in session.query(Monster.id).order_by(Monster.id).all()]
        move_ids = [mid for (mid,) in session.query(Move.id).order_by(Move.id).all()]

    parts = ['<?xml version="1.0" encoding="UTF-8"?>\n',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n']

    parts.append(url_entry(f"{BASE_URL}/", today, "weekly", "1.0"))
    parts.append(url_entry(f"{BASE_URL}/dex", today, "weekly", "0.9"))

    for mid in monster_ids:
        parts.append(url_entry(f"{BASE_URL}/dex/monsters/{mid}", today, "monthly", "0.8"))

    for mid in move_ids:
        parts.append(url_entry(f"{BASE_URL}/dex/moves/{mid}", today, "monthly", "0.6"))

    parts.append("</urlset>\n")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("".join(parts), encoding="utf-8")

    total = 2 + len(monster_ids) + len(move_ids)
    print(f"Wrote {total} URLs to {OUTPUT_PATH}")
    print(f"  /                       1")
    print(f"  /dex                    1")
    print(f"  /dex/monsters/{{id}}      {len(monster_ids)}")
    print(f"  /dex/moves/{{id}}         {len(move_ids)}")


if __name__ == "__main__":
    main()
