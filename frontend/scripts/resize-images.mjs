// Resize monster images to multiple square sizes (180, 270, 360) with padding as needed.
// There must be a "resize" subfolder in the public/monster-images/ folder containing source PNG images.
import sharp from "sharp";
import fs from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Base directory = frontend/
const BASE_DIR = __dirname + "/..";

const INPUT_DIR = path.resolve(BASE_DIR, "public/monster-images/resize");
const OUTPUT_BASE = path.resolve(BASE_DIR, "public/monster-images");

const SIZES = [180, 270, 360];

// Only process PNG files
function isPng(file) {
  return path.extname(file).toLowerCase() === ".png";
}

// Ensure output directory exists
async function ensureDir(dirPath) {
  await fs.mkdir(dirPath, { recursive: true });
}

/**
 * Pads an image to a square canvas with transparent background if needed.
 * Returns:
 *  - buffer: image buffer (padded to square)
 *  - squareSize: final square edge length
 *  - didPad: whether padding was applied
 *  - origW / origH: original dimensions
 *  - density: DPI/resolution of original image
 */
async function padToSquareIfNeeded(inputPath, fileName) {
  const img = sharp(inputPath).rotate();
  const meta = await img.metadata();

  if (!meta.width || !meta.height) {
    throw new Error(`Unreadable image: ${fileName}`);
  }

  const w = meta.width;
  const h = meta.height;
  // Preserve original DPI (defaults to 96 if not specified)
  const density = meta.density || 96;

  // Already square → no padding needed
  if (w === h) {
    const buffer = await img.png().toBuffer();
    return { buffer, squareSize: w, didPad: false, origW: w, origH: h, density };
  }

  // Compute padding to make it square
  const size = Math.max(w, h);
  const left = Math.floor((size - w) / 2);
  const right = size - w - left;
  const top = Math.floor((size - h) / 2);
  const bottom = size - h - top;

  const buffer = await img
    .extend({
      top,
      bottom,
      left,
      right,
      background: { r: 0, g: 0, b: 0, alpha: 0 }, // fully transparent padding
    })
    .png()
    .toBuffer();

  // Verify the padded size is actually square
  const verifyMeta = await sharp(buffer).metadata();
  console.log(
    `🧩 Padded to square: ${fileName}  ${w}x${h} -> ${verifyMeta.width}x${verifyMeta.height}`
  );

  return { buffer, squareSize: size, didPad: true, origW: w, origH: h, density };
}

async function main() {
  // Create output directories if they don't exist
  for (const s of SIZES) {
    await ensureDir(path.join(OUTPUT_BASE, String(s)));
  }

  const files = await fs.readdir(INPUT_DIR);
  const pngFiles = files.filter(isPng);

  console.log(`Found ${pngFiles.length} PNG(s) in: ${INPUT_DIR}`);

  for (const file of pngFiles) {
    const inputPath = path.join(INPUT_DIR, file);

    let baseInfo;
    try {
      baseInfo = await padToSquareIfNeeded(inputPath, file);
    } catch (e) {
      console.warn(`⚠️ Skip ${file}: ${e.message}`);
      continue;
    }

    // Generate each target size
    for (const size of SIZES) {
      // Do not enlarge images smaller than target size
      if (baseInfo.squareSize < size) {
        console.log(
          `  - Skip ${file} -> ${size}px (source ${baseInfo.squareSize}px too small)`
        );
        continue;
      }

      const outDir = path.join(OUTPUT_BASE, String(size));
      const outPath = path.join(outDir, file); // keep original file name

      // Create fresh sharp instance from buffer and resize to exact square dimensions
      await sharp(baseInfo.buffer)
        .resize(size, size, {
          fit: "fill",              // force exact square dimensions
          kernel: "lanczos3",       // high-quality downscaling
        })
        .withMetadata({
          density: 96               // force 96 DPI to match existing images
        })
        .png({
          compressionLevel: 9,      // compression only, does not affect transparency
          adaptiveFiltering: true,
        })
        .toFile(outPath);
    }
  }

  console.log("🎉 Done. Output folders:", SIZES.map(String).join(", "));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});