"""
Generate frontend/public/sitemap.xml from the live database.

Lists every indexable URL in BOTH locales (/en/... and /zh/...) with
reciprocal xhtml:link hreflang annotations, so search engines can discover
and correctly pair the English and Chinese versions of every page
(homepage, dex, announcements, all jingling detail pages, all move detail
pages) without crawling the SPA.

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
LANGS = ["en", "zh"]

# Output path: backend/scripts/maintenance/ -> ../../../frontend/public/sitemap.xml
OUTPUT_PATH = Path(__file__).resolve().parents[3] / "frontend" / "public" / "sitemap.xml"


def url_entry(loc: str, lastmod: str, changefreq: str, priority: str,
              alternates: list[tuple[str, str]] | None = None) -> str:
    inner = ""
    if alternates:
        for hreflang, href in alternates:
            inner += f'    <xhtml:link rel="alternate" hreflang="{hreflang}" href="{escape(href)}"/>\n'
    return (
        "  <url>\n"
        f"    <loc>{escape(loc)}</loc>\n"
        f"{inner}"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <changefreq>{changefreq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        "  </url>\n"
    )


def alts(path: str) -> list[tuple[str, str]]:
    """Reciprocal hreflang set for a locale-neutral path ("/" or "/dex/...").

    The homepage keeps its trailing slash (/en/), matching the canonical form
    used by useSeoMeta and the CloudFront redirects; deeper paths carry none.
    """
    suffix = "/" if path == "/" else path
    return [
        ("en", f"{BASE_URL}/en{suffix}"),
        ("zh", f"{BASE_URL}/zh{suffix}"),
        ("x-default", f"{BASE_URL}/en{suffix}"),
    ]


def main():
    engine = create_engine(DATABASE_URL)
    today = date.today().isoformat()

    with Session(engine) as session:
        monster_ids = [mid for (mid,) in session.query(Monster.id).order_by(Monster.id).all()]
        move_ids = [mid for (mid,) in session.query(Move.id).order_by(Move.id).all()]

    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n',
    ]

    for lang in LANGS:
        parts.append(url_entry(f"{BASE_URL}/{lang}/", today, "weekly", "1.0", alts("/")))
        parts.append(url_entry(f"{BASE_URL}/{lang}/dex", today, "weekly", "0.9", alts("/dex")))
        parts.append(url_entry(f"{BASE_URL}/{lang}/announcements", today, "weekly", "0.5",
                               alts("/announcements")))
        for mid in monster_ids:
            parts.append(url_entry(f"{BASE_URL}/{lang}/dex/monsters/{mid}", today, "monthly", "0.8",
                                   alts(f"/dex/monsters/{mid}")))
        for mid in move_ids:
            parts.append(url_entry(f"{BASE_URL}/{lang}/dex/moves/{mid}", today, "monthly", "0.6",
                                   alts(f"/dex/moves/{mid}")))

    parts.append("</urlset>\n")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("".join(parts), encoding="utf-8")

    per_lang = 3 + len(monster_ids) + len(move_ids)
    total = len(LANGS) * per_lang
    print(f"Wrote {total} URLs to {OUTPUT_PATH}")
    print(f"  per locale ({'/'.join(LANGS)}):")
    print(f"    /                       1")
    print(f"    /dex                    1")
    print(f"    /announcements          1")
    print(f"    /dex/monsters/{{id}}      {len(monster_ids)}")
    print(f"    /dex/moves/{{id}}         {len(move_ids)}")


if __name__ == "__main__":
    main()
