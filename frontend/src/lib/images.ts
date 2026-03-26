function safeBaseName(s: string): string {
  // remove characters illegal on Windows filesystems
  return s.replace(/[\\/:*?"<>|]/g, "").trim();
}

export function monsterImageUrlByCN(monster: any, size: 180 | 270 | 360 = 360): string | null {
  const zh = monster?.localized?.zh;
  const cnName = typeof zh === "object" && typeof zh.name === "string" ? zh.name.trim() : null;
  if (!cnName) return null;

  // For leader forms, omit form suffix to use shared base image
  const isLeader = monster?.is_leader_form === true;
  const cnForm =
    !isLeader && typeof zh === "object" && typeof zh.form === "string" && zh.form.trim()
      ? zh.form.trim()
      : null;

  const base = safeBaseName(cnForm ? `${cnName}(${cnForm})` : cnName);
  // URL-encode for the request path
  const encoded = encodeURIComponent(base);
  return `/monster-images/${size}/${encoded}.png`;
}

export function monsterImageUrlByEN(monster: any, size: 180 | 270 | 360 = 360): string | null {
  const enName = monster?.name ? String(monster.name).trim() : null;
  if (!enName) return null;

  // For leader forms, omit form suffix
  const isLeader = monster?.is_leader_form === true;
  const form = !isLeader && monster?.form && String(monster.form).trim().toLowerCase() !== "default"
    ? String(monster.form).trim()
    : null;

  const base = safeBaseName(form ? `${enName}(${form})` : enName);
  const encoded = encodeURIComponent(base);
  return `/monster-images/${size}/${encoded}.png`;
}

export function monsterImageUrlById(monster: any, size: 180 | 270 | 360 = 360): string | null {
  return monster?.id ? `/monster-images/${size}/${monster.id}.png` : null;
}

export function typeIconUrl(name?: string, size: 30 | 45 | 60 = 60): string | null {
  if (!name) return null;
  const slug = name.toLowerCase().replace(/\s+/g, "-");
  return `/type-icons/${size}/${slug}.png`;
}

export function magicItemImageUrl(item: any): string | null {
  if (!item) return null;
  const zh = item?.localized?.zh;
  const cnName = zh && typeof zh.name === "string" ? zh.name : null;
  if (cnName) return `/magic-items/${encodeURI(cnName)}.png`;
  if (item.name) return `/magic-items/${encodeURI(item.name)}.png`;
  return null;
}

export function monsterImageFallbackChain(monster: any, size: 180 | 270 | 360 = 360): string[] {
  return [
    monsterImageUrlByCN(monster, size),
    monsterImageUrlByEN(monster, size),
    monsterImageUrlById(monster, size),
    "/monster-images/placeholder.png",
  ].filter(Boolean) as string[];
}

/**
 * Generate srcset string for monster images with multiple resolutions
 * @param monster - Monster object
 * @returns srcset string for use in <img srcSet={...} />
 */
export function moveIconUrl(move: any): string | null {
  const zh = move?.localized?.zh;
  const cnName = typeof zh === 'object' && typeof zh?.name === 'string' ? zh.name.trim() : null;
  if (cnName) return `/move-icons/${encodeURIComponent(cnName)}.png`;
  return null;
}

export function monsterImageSrcSet(monster: any): string {
  const sizes: (180 | 270 | 360)[] = [180, 270, 360];
  const srcSets: string[] = [];

  for (const size of sizes) {
    const url = monsterImageUrlByCN(monster, size) ||
                monsterImageUrlByEN(monster, size) ||
                monsterImageUrlById(monster, size);
    if (url) {
      srcSets.push(`${url} ${size}w`);
    }
  }

  return srcSets.join(", ");
}