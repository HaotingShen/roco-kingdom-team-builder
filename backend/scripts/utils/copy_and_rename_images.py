from pathlib import Path
import shutil, re

# repo root = ../../ from this file (backend/scripts/… -> backend -> root)
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "frontend" / "images"
DST = ROOT / "frontend" / "public" / "monsters" / "360"

IMAGE_EXTS = {'.png','.jpg','.jpeg','.webp','.gif','.bmp','.tif','.tiff','.svg','.avif','.apng','.jfif','.ico'}
STEM_RE = re.compile(r'^360px-页面_宠物_立绘_(.+?)(?:_\d+)?$')

def sanitize(name: str) -> str:
    # Convert full-width Chinese parentheses to ASCII and strip illegal chars
    name = name.replace('（','(').replace('）',')')
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, '')
    return name.strip()

def unique(p: Path) -> Path:
    if not p.exists(): return p
    i = 1
    while True:
        q = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not q.exists(): return q
        i += 1

def main():
    print(f"[INFO] SRC: {SRC}")
    print(f"[INFO] DST: {DST}")
    if not SRC.exists():
        print("[ERROR] Source path does not exist."); return
    DST.mkdir(parents=True, exist_ok=True)

    copied = skipped = 0
    for p in SRC.rglob('*'):
        if not p.is_file(): continue
        if p.suffix.lower() not in IMAGE_EXTS: continue
        if not p.name.startswith('360px'): continue

        m = STEM_RE.match(p.stem)
        if not m:
            skipped += 1
            print(f"[WARN] Pattern mismatch: {p.name}")
            continue

        out = unique(DST / f"{sanitize(m.group(1))}{p.suffix.lower()}")
        shutil.copy2(p, out)
        copied += 1
        print(f"Copied: {p.name} -> {out.name}")

    print(f"\n[RESULT] Copied: {copied}, Skipped: {skipped}, Output: {DST}")
    print(f"[IMPORTANT] Change file naming for 化蝶，棋棋黑白子，钻石蜗首领！")

if __name__ == "__main__":
    main()