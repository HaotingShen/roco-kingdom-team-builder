import { monsterImageFallbackChain, monsterImageSrcSet, monsterPlaceholder } from "@/lib/images";

interface MonsterImageProps {
  monster: any;
  size?: 180 | 270 | 360;
  alt?: string;
  width?: number;
  height?: number;
  className?: string;
  loading?: "lazy" | "eager";
  /** Whether to use srcset for responsive images (default: true) */
  useSrcSet?: boolean;
}

export function MonsterImage({
  monster,
  size = 180,
  alt = "",
  width,
  height,
  className = "",
  loading = "lazy",
  useSrcSet = true,
}: MonsterImageProps) {
  const fallbackChain = monsterImageFallbackChain(monster, size);
  const initialSrc = fallbackChain[0] || monsterPlaceholder;

  // Generate srcset if enabled
  const srcSet = useSrcSet ? monsterImageSrcSet(monster) : undefined;

  // Compute sizes attribute based on width prop
  // This tells browser which image to download based on display size
  const sizes = useSrcSet && width
    ? `${width}px`
    : undefined;

  return (
    <img
      src={initialSrc}
      srcSet={srcSet}
      sizes={sizes}
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
        } else if (img.src !== monsterPlaceholder) {
          img.src = monsterPlaceholder;
        }
      }}
    />
  );
}
