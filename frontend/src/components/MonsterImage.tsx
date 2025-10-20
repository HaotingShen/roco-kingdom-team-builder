import { monsterImageFallbackChain } from "@/lib/images";

interface MonsterImageProps {
  monster: any;
  size?: 180 | 270 | 360;
  alt?: string;
  width?: number;
  height?: number;
  className?: string;
  loading?: "lazy" | "eager";
}

export function MonsterImage({
  monster,
  size = 180,
  alt = "",
  width,
  height,
  className = "",
  loading = "lazy",
}: MonsterImageProps) {
  const fallbackChain = monsterImageFallbackChain(monster, size);
  const initialSrc = fallbackChain[0] || "/monsters/placeholder.png";

  return (
    <img
      src={initialSrc}
      alt={alt}
      width={width}
      height={height}
      className={className}
      loading={loading}
      data-fallback-step="0"
      onError={(e) => {
        const img = e.currentTarget as HTMLImageElement;
        const step = Number(img.dataset.fallbackStep || "0");
        const next = step + 1;
        if (next < fallbackChain.length) {
          img.dataset.fallbackStep = String(next);
          img.src = fallbackChain[next]!;
        } else if (img.src !== "/monsters/placeholder.png") {
          img.src = "/monsters/placeholder.png";
        }
      }}
    />
  );
}
