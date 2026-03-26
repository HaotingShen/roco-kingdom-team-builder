import { useRef, useEffect, useCallback } from 'react';
import { QRCodeCanvas } from 'qrcode.react';
import type { ShareDecodeResponse, PersonalityOut } from '@/types';
import { pickName, pickFormName, useI18n } from '@/i18n';
import { monsterImageFallbackChain, typeIconUrl, magicItemImageUrl, moveIconUrl } from '@/lib/images';

// ─── Layout constants ─────────────────────────────────────────────────────────

const W = 960, H = 720;

// Left zone (3 × 2 monster grid)
const LFT_X = 12;
const LFT_W = 664;

// Right sidebar
const SB_X   = LFT_X + LFT_W + 8;  // 684
const SB_W   = W - SB_X - 4;       // 272
const SB_PAD = 12;

// Grid: 2 columns × 3 rows
// COL_W = (664 − 6) / 2 = 329
// ROW_H and ROW_GAP_Y are language-dependent — computed inside renderCard.
//   ZH: ROW_GAP_Y=28 → ROW_H=216  (original spacing, unmodified)
//   EN: ROW_GAP_Y=7  → ROW_H=230  (tighter gaps to fit the extra legacy row)
const GRID_COLS  = 2;
const GRID_ROWS  = 3;
const COL_GAP    = 6;
const ROWS_TOP   = 8;
const COL_W      = (LFT_W - (GRID_COLS - 1) * COL_GAP) / GRID_COLS;   // 329

// Per-cell: accent stripe + portrait column
const STRIPE_W    = 4;
const PORT_PAD_L  = 7;   // gap between stripe and portrait
const PORT_PAD_T  = 10;  // portrait top-offset within cell
const PORT_SZ     = 88;  // sprite draw size (was 72)

// Per-cell: info text area (to the right of the portrait)
// INFO_X_OFF = stripe + gap + portrait + gap = 4+7+88+8 = 107
const INFO_X_OFF = STRIPE_W + PORT_PAD_L + PORT_SZ + 8;  // 107
const INFO_W     = COL_W - INFO_X_OFF - 8;                // 214

// Line y-offsets within info area (relative to cell_y)
// Name  18px font → ~18px tall; gap 6 → type at 37
// Types PILL_H=28        ; gap 6 → personality at 71
// Pers  CHIP_H=24        ; gap 5 → talents at 100
// Talent CHIP_H=24 ends at 124; move-divider=131; gap=7px ✓
const LINE_NAME   = 13;
const LINE_TYPE   = 37;   // 13 + 18(font) + 6(gap)
const LINE_PERS   = 71;   // 37 + 28(pill) + 6(gap)
const LINE_TALENT = 100;  // 71 + 24(chip) + 5(gap)

// Move band: bottom-anchored, spans full cell width (past stripe)
// MOVE_BAND_Y_OFF is language-dependent — computed inside renderCard.
//   ZH: ROW_H=216, MOVE_BOT_PAD=10 → MOVE_BAND_Y_OFF=136
//   EN: ROW_H=230, MOVE_BOT_PAD=4  → MOVE_BAND_Y_OFF=156
const MOVE_ICON_SZ  = 52;
const MOVE_BAR_H    = 22;
const MOVE_SLOT_H   = MOVE_ICON_SZ + MOVE_BAR_H;  // 74
const MOVE_SIDE_PAD = 10;
// MOVE_AVAIL_W = 329 − 4 − 2×10 = 305
// MOVE_SLOT_W  = ⌊(305 − 3×5) / 4⌋ = ⌊290 / 4⌋ = 72
const MOVE_AVAIL_W  = COL_W - STRIPE_W - 2 * MOVE_SIDE_PAD;   // 305
const MOVE_SLOT_GAP = 5;
const MOVE_SLOT_W   = Math.floor((MOVE_AVAIL_W - 3 * MOVE_SLOT_GAP) / 4);  // 72

// Pill / chip heights
const PILL_H = 28;   // fits 26px type icons
const CHIP_H = 24;   // matches 15px label size with comfortable padding

// ─── Color palette ────────────────────────────────────────────────────────────

const C = {
  // Backgrounds
  cardBg:     '#0b1120',
  headerBg:   '#07101e',
  sidebarBg:  '#0d1524',
  divider:    '#1a2d42',
  headerLine: '#1a3456',

  // Text
  text:       '#f1f5f9',
  textSub:    '#94a3b8',
  textMuted:  '#4a5572',
  textDim:    '#253245',

  // Personality (inline text, not a pill)
  persLabel:  '#a8c8e4',  // bright-ish cool blue — clearly readable on dark bg
  persFg:     '#c4b5fd',  // violet for the effect string

  // Talent chips
  talentLabel: '#a8c8e4',
  talentBg:    'rgba(110,231,183,0.18)',  // visible green tint
  talentFg:    '#6ee7b7',

  // Legacy type label (the "血脉：" prefix)
  legacyLabel: '#a8c8e4',

  // Invalid move
  invalidBg:  '#3d0a0a',
  invalidFg:  '#fca5a5',

  // Branding
  brandLine:  '#1e3a6e',
  white:      '#ffffff',
};

// ─── Type badge colors ────────────────────────────────────────────────────────

type TC = { bg: string; text: string };

const TYPE_COLORS: Record<string, TC> = {
  fire:       { bg: '#7f1d1d', text: '#fca5a5' },
  water:      { bg: '#1e3a8a', text: '#93c5fd' },
  grass:      { bg: '#14532d', text: '#86efac' },
  electric:   { bg: '#713f12', text: '#fde68a' },
  ice:        { bg: '#164e63', text: '#a5f3fc' },
  dragon:     { bg: '#4c1d95', text: '#c4b5fd' },
  dark:       { bg: '#1f2937', text: '#9ca3af' },
  ghost:      { bg: '#3b0764', text: '#d8b4fe' },
  fighting:   { bg: '#7c2d12', text: '#fdba74' },
  poison:     { bg: '#701a75', text: '#f0abfc' },
  ground:     { bg: '#78350f', text: '#fcd34d' },
  flying:     { bg: '#0c4a6e', text: '#7dd3fc' },
  bug:        { bg: '#365314', text: '#a3e635' },
  normal:     { bg: '#1f2937', text: '#9ca3af' },
  light:      { bg: '#44350a', text: '#fef08a' },
  mechanical: { bg: '#1f2937', text: '#a0aec0' },
  illusion:   { bg: '#831843', text: '#fbcfe8' },
  cute:       { bg: '#831843', text: '#fbcfe8' },
  leader:     { bg: '#78350f', text: '#fcd34d' },
};
const DEF_TC: TC = { bg: '#1f2937', text: '#9ca3af' };
const tc = (name?: string | null): TC => TYPE_COLORS[(name ?? '').toLowerCase()] ?? DEF_TC;

// ─── Vivid stripe / tint colors (mirrors dex page border-l Tailwind mapping) ──

const STRIPE_COLORS: Record<string, string> = {
  normal:     '#64748b',  // slate-500
  grass:      '#4ade80',  // green-400
  fire:       '#ea580c',  // orange-600
  water:      '#3b82f6',  // blue-500
  light:      '#22d3ee',  // cyan-400
  ground:     '#ca8a04',  // yellow-600
  ice:        '#0ea5e9',  // sky-500
  dragon:     '#f43f5e',  // rose-500
  electric:   '#facc15',  // yellow-400
  poison:     '#c084fc',  // purple-400
  bug:        '#a3e635',  // lime-400
  fighting:   '#fb923c',  // orange-400
  flying:     '#2dd4bf',  // teal-400
  cute:       '#f472b6',  // pink-400
  ghost:      '#8b5cf6',  // violet-500
  dark:       '#db2777',  // pink-600
  mechanical: '#34d399',  // emerald-400
  illusion:   '#a5b4fc',  // indigo-300
  leader:     '#a1a1aa',  // zinc-400
};
const sc = (name?: string | null): string =>
  STRIPE_COLORS[(name ?? '').toLowerCase()] ?? '#a1a1aa';

function hexAlpha(hex: string, a: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${a})`;
}

// ─── Personality effects string ───────────────────────────────────────────────

const PERS_LABELS_ZH = ['生命', '物攻', '魔攻', '物防', '魔防', '速度'];
const PERS_LABELS_EN = ['HP', 'P.ATK', 'M.ATK', 'P.DEF', 'M.DEF', 'SPD'];

function personalityEffects(p: PersonalityOut, lang: 'en' | 'zh'): string {
  const labels = lang === 'zh' ? PERS_LABELS_ZH : PERS_LABELS_EN;
  const mods   = [p.hp_mod_pct, p.phy_atk_mod_pct, p.mag_atk_mod_pct,
                  p.phy_def_mod_pct, p.mag_def_mod_pct, p.spd_mod_pct];
  const parts  = mods.map((m, i) => m > 0 ? `${labels[i]}↑` : m < 0 ? `${labels[i]}↓` : null)
                     .filter(Boolean) as string[];
  // Boosts (↑) always shown before downgrades (↓)
  const boosts = parts.filter(s => s.endsWith('↑'));
  const downs  = parts.filter(s => s.endsWith('↓'));
  return [...boosts, ...downs].join(' ') || pickName(p, lang);
}

// ─── Talent label arrays ──────────────────────────────────────────────────────

const TALENT_LABELS_ZH = ['生命', '物攻', '魔攻', '物防', '魔防', '速度'];
const TALENT_LABELS_EN = ['HP', 'ATK', 'MATK', 'DEF', 'MDEF', 'SPD'];

// ─── Fallback note ────────────────────────────────────────────────────────────

const NOTE_FALLBACK: Record<'en' | 'zh', string> = {
  zh: '该队伍由玩家自行配置并分享。扫码后可在洛手配队器中保存此队伍或继续编辑。',
  en: 'This team was created and shared by a player. Scan to save this team or continue editing in RK Team Builder.',
};

// ─── Image loader ─────────────────────────────────────────────────────────────

async function loadImg(urls: string[]): Promise<HTMLImageElement | null> {
  for (const url of urls) {
    if (!url) continue;
    const result = await new Promise<HTMLImageElement | null>(resolve => {
      const el = new Image();
      el.onload  = () => resolve(el);
      el.onerror = () => resolve(null);
      el.src = url;
    });
    if (result) return result;
  }
  return null;
}

// ─── Canvas utils ─────────────────────────────────────────────────────────────

function trunc(ctx: CanvasRenderingContext2D, text: string, maxW: number): string {
  if (ctx.measureText(text).width <= maxW) return text;
  let s = text;
  while (s.length > 0 && ctx.measureText(s + '…').width > maxW) s = s.slice(0, -1);
  return s + '…';
}

function rrect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  if (w <= 0 || h <= 0) return;
  ctx.beginPath();
  ctx.roundRect(x, y, w, h, r);
  ctx.fill();
}

function rrectBottom(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number, r: number,
) {
  if (w <= 0 || h <= 0) return;
  const r2 = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x, y);
  ctx.lineTo(x + w, y);
  ctx.lineTo(x + w, y + h - r2);
  ctx.arcTo(x + w, y + h, x + w - r2, y + h, r2);
  ctx.lineTo(x + r2, y + h);
  ctx.arcTo(x, y + h, x, y + h - r2, r2);
  ctx.lineTo(x, y);
  ctx.closePath();
  ctx.fill();
}

function wrapLines(ctx: CanvasRenderingContext2D, text: string, maxW: number): string[] {
  if (ctx.measureText(text).width <= maxW) return [text];
  // Character-by-character splitting handles CJK text (no word boundaries) and
  // mixed CJK+Latin without overflowing a long Chinese word-token.
  const lines: string[] = [];
  let cur = '';
  for (const ch of Array.from(text)) {
    const test = cur + ch;
    if (ctx.measureText(test).width > maxW && cur) {
      lines.push(cur);
      cur = ch;
    } else {
      cur = test;
    }
  }
  if (cur) lines.push(cur);
  return lines;
}

// Filled pill with optional left icon. Returns right-edge x.
function drawPill(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, h: number,
  text: string, font: string,
  bg: string, fg: string, padH: number,
  icon?: HTMLImageElement | null, iconSz: number = 13,
): number {
  ctx.font = font;
  const iw    = icon ? iconSz + 3 : 0;
  const tw    = ctx.measureText(text).width;
  const total = padH * 2 + iw + tw;
  ctx.fillStyle = bg;
  rrect(ctx, x, y, total, h, 7);
  if (icon) ctx.drawImage(icon, x + padH, y + (h - iconSz) / 2, iconSz, iconSz);
  ctx.fillStyle = fg;
  ctx.textBaseline = 'middle';
  // +1 nudge: canvas 'middle' baseline is the em-box midpoint, which sits
  // ~1px above the visual glyph center for most fonts. Nudging +1 down aligns
  // the perceived glyph center with the icon center.
  ctx.fillText(text, x + padH + iw, y + h / 2 + 1);
  return x + total;
}

// Compact chip (no icon). Returns right-edge x.
function drawChip(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, h: number,
  text: string, font: string,
  bg: string, fg: string,
): number {
  const padH = 5;
  ctx.font = font;
  const tw    = ctx.measureText(text).width;
  const total = padH * 2 + tw;
  ctx.fillStyle = bg;
  rrect(ctx, x, y, total, h, 2);
  ctx.fillStyle = fg;
  ctx.textBaseline = 'middle';
  ctx.fillText(text, x + padH, y + h / 2 + 1);
  return x + total;
}

// ─── Asset loading ────────────────────────────────────────────────────────────

interface Assets {
  sprites:   (HTMLImageElement | null)[];
  typeIcons: Record<string, HTMLImageElement | null>;
  moveIcons: Record<string, HTMLImageElement | null>;
  magicIcon: HTMLImageElement | null;
  logoIcon:  HTMLImageElement | null;
}

async function loadAssets(data: ShareDecodeResponse): Promise<Assets> {
  const typeNames = new Set<string>();
  data.monsters.forEach(e => {
    if (e.monster.main_type?.name) typeNames.add(e.monster.main_type.name);
    if (e.monster.sub_type?.name)  typeNames.add(e.monster.sub_type.name);
    if (e.legacy_type?.name)       typeNames.add(e.legacy_type.name);
    e.moves.forEach(m => {
      const mt = m ? (m.move_type ?? m.type ?? null) : null;
      if (mt?.name) typeNames.add(mt.name);
    });
  });

  const moveIconUrls = new Set<string>();
  data.monsters.forEach(e => {
    e.moves.forEach(m => {
      const url = m ? moveIconUrl(m) : null;
      if (url) moveIconUrls.add(url);
    });
  });

  const [sprites, typeIconArr, moveIconArr, magicIcon, logoIcon] = await Promise.all([
    Promise.all(data.monsters.map(e => loadImg(monsterImageFallbackChain(e.monster, 360)))),
    Promise.all(Array.from(typeNames).map(name => {
      const url = typeIconUrl(name, 60);
      return url
        ? loadImg([url]).then(img => ({ name, img }))
        : Promise.resolve({ name, img: null as HTMLImageElement | null });
    })),
    Promise.all(Array.from(moveIconUrls).map(url =>
      loadImg([url]).then(img => ({ url, img }))
    )),
    loadImg([magicItemImageUrl(data.magic_item) ?? '']),
    loadImg(['/logo.png']),
  ]);

  const typeIcons: Record<string, HTMLImageElement | null> = {};
  typeIconArr.forEach(({ name, img }) => { typeIcons[name] = img; });
  const moveIcons: Record<string, HTMLImageElement | null> = {};
  moveIconArr.forEach(({ url, img }) => { moveIcons[url] = img; });

  return { sprites, typeIcons, moveIcons, magicIcon, logoIcon };
}

// ─── Renderer ─────────────────────────────────────────────────────────────────

interface CardLabels {
  teamName: string;       // sidebar label e.g. "TEAM NAME:" / "队伍名称："
  teamFallback: string;   // fallback when team has no name
  personality: string;    // "Personality: " / "性格："
  talents: string;        // "Talents: " / "个体值："
  legacy: string;         // "Legacy: " / "血脉："
  sharedBy: string;       // "Shared by " / "分享者："
  scanToImport: string;   // "Scan to import" / "扫码导入队伍"
  brandName: string;      // "RK Team Builder" / "洛手配队器"
}

function renderCard(
  ctx: CanvasRenderingContext2D,
  data: ShareDecodeResponse,
  assets: Assets,
  lang: 'en' | 'zh',
  showQrSection: boolean,
  qrCanvas: HTMLCanvasElement | null,
  labels: CardLabels,
  note?: string,
) {
  const { sprites, typeIcons, moveIcons, magicIcon, logoIcon } = assets;

  // Language-dependent layout: ZH keeps original spacing; EN uses tighter row gaps
  // to fit the extra legacy type row.
  const ROW_GAP_Y      = lang === 'zh' ? 28 : 5;
  const MOVE_BOT_PAD   = lang === 'zh' ? 6  : 2;
  const ROW_H          = (H - ROWS_TOP - 8 - (GRID_ROWS - 1) * ROW_GAP_Y) / GRID_ROWS;
  const MOVE_BAND_Y_OFF = ROW_H - MOVE_BOT_PAD - MOVE_SLOT_H;

  // Font constants
  const F_NAME    = '700 18px system-ui,-apple-system,sans-serif';
  const F_BADGE   = '600 15px system-ui,-apple-system,sans-serif';
  const F_CHIP    = '500 15px system-ui,-apple-system,sans-serif';
  const F_LABEL   = '600 15px system-ui,-apple-system,sans-serif';
  const F_MOVE    = '500 13px system-ui,-apple-system,sans-serif';
  const F_TEAM_NM = '700 26px system-ui,-apple-system,sans-serif';
  const F_SB_LBL  = '600 13px system-ui,-apple-system,sans-serif';
  const F_SB_BODY = '400 16px system-ui,-apple-system,sans-serif';
  const F_SEP     = '400 12px system-ui,-apple-system,sans-serif';

  const talentLabels = lang === 'zh' ? TALENT_LABELS_ZH : TALENT_LABELS_EN;

  // ── Full card background ──────────────────────────────────────────────────
  ctx.fillStyle = C.cardBg;
  ctx.fillRect(0, 0, W, H);

  // ── 3 × 2 Monster grid ────────────────────────────────────────────────────
  data.monsters.forEach((entry, i) => {
    const col    = i % GRID_COLS;
    const row    = Math.floor(i / GRID_COLS);
    const cellX  = LFT_X + col * (COL_W + COL_GAP);
    const cellY  = ROWS_TOP + row * (ROW_H + ROW_GAP_Y);

    // ── Left accent stripe (main type color) ─────────────────────────────────
    ctx.fillStyle = sc(entry.monster.main_type?.name);
    ctx.fillRect(cellX, cellY, STRIPE_W, ROW_H);

    // ── Portrait (top-anchored in the left column) ────────────────────────────
    const portX = cellX + STRIPE_W + PORT_PAD_L;
    const portY = cellY + PORT_PAD_T;
    if (sprites[i]) {
      ctx.drawImage(sprites[i]!, portX, portY, PORT_SZ, PORT_SZ);
    }

    // ── Info area (right of portrait) ─────────────────────────────────────────
    const infoX = cellX + INFO_X_OFF;

    // Name (+ optional form tag to the right)
    const monName  = pickName(entry.monster, lang);
    const formName = pickFormName(entry.monster, lang);
    const F_FORM   = '400 14px system-ui,-apple-system,sans-serif';
    ctx.textBaseline = 'top';
    if (formName) {
      const F_FORM_GAP = 8;  // gap between name and form tag
      ctx.font = F_FORM;
      const fW = ctx.measureText(formName).width;
      const nameMaxW = Math.max(30, INFO_W - fW - F_FORM_GAP);
      ctx.font = F_NAME;
      const truncName = trunc(ctx, monName, nameMaxW);
      ctx.fillStyle = C.text;
      ctx.fillText(truncName, infoX, cellY + LINE_NAME);
      const nameW = ctx.measureText(truncName).width;
      ctx.font = F_FORM;
      ctx.fillStyle = C.textSub;
      ctx.fillText(formName, infoX + nameW + F_FORM_GAP, cellY + LINE_NAME + 3);
    } else {
      ctx.font = F_NAME;
      ctx.fillStyle = C.text;
      ctx.fillText(trunc(ctx, monName, INFO_W), infoX, cellY + LINE_NAME);
    }

    // Type badges
    const typeY    = cellY + LINE_TYPE;
    const mainName = entry.monster.main_type ? pickName(entry.monster.main_type, lang) : null;
    const subName  = entry.monster.sub_type  ? pickName(entry.monster.sub_type, lang)  : null;
    const mainIcon = entry.monster.main_type ? (typeIcons[entry.monster.main_type.name] ?? null) : null;
    const subIcon  = entry.monster.sub_type  ? (typeIcons[entry.monster.sub_type.name] ?? null) : null;
    const legIcon  = entry.legacy_type       ? (typeIcons[entry.legacy_type.name] ?? null)      : null;

    const TYPE_ICON_SZ = 26;
    let bx = infoX;
    if (mainName) {
      bx = drawPill(ctx, bx, typeY, PILL_H, mainName, F_BADGE,
        hexAlpha(sc(entry.monster.main_type?.name), 0.30), tc(entry.monster.main_type?.name).text, 7, mainIcon, TYPE_ICON_SZ);
    }
    if (subName) {
      bx += 5;
      bx = drawPill(ctx, bx, typeY, PILL_H, subName, F_BADGE,
        hexAlpha(sc(entry.monster.sub_type?.name), 0.30), tc(entry.monster.sub_type?.name).text, 7, subIcon, TYPE_ICON_SZ);
    }
    // EN needs a dedicated row for legacy because "Legacy: " + English type names overflow INFO_W.
    // ZH stays on the same row (Chinese type names are short; it fits fine).
    const legacyNewRow = lang === 'en' && !!entry.legacy_type;

    // Legacy inline (ZH only): dot separator + label + icon on the type row
    if (legIcon && !legacyNewRow) {
      bx += 8;
      ctx.font = F_SEP;
      ctx.fillStyle = C.textDim;
      ctx.textBaseline = 'middle';
      ctx.fillText('·', bx, typeY + PILL_H / 2 + 1);
      bx += ctx.measureText('·').width + 5;

      const legLabel = labels.legacy;
      ctx.font = F_LABEL;
      ctx.fillStyle = C.legacyLabel;
      ctx.fillText(legLabel, bx, typeY + PILL_H / 2 + 1);
      bx += ctx.measureText(legLabel).width;

      const LEG_ICON_SZ = 29;
      ctx.drawImage(legIcon, bx, typeY + (PILL_H - LEG_ICON_SZ) / 2, LEG_ICON_SZ, LEG_ICON_SZ);
    }

    // Legacy new row (EN only): full-size row below type pills
    // Type row ends at 65. Legacy row: 67→95 (PILL_H=28, 2px gap).
    // Pers: 98→122. Talent: 125→149. Divider: 151. Move band: 156. ✓
    if (legacyNewRow) {
      const legRowY = cellY + 67;
      ctx.font = F_LABEL;
      ctx.fillStyle = C.legacyLabel;
      ctx.textBaseline = 'middle';
      ctx.fillText(labels.legacy, infoX, legRowY + PILL_H / 2 + 1);
      const legLabelW = ctx.measureText(labels.legacy).width;
      if (legIcon) {
        ctx.drawImage(legIcon, infoX + legLabelW, legRowY + (PILL_H - TYPE_ICON_SZ) / 2, TYPE_ICON_SZ, TYPE_ICON_SZ);
      }
    }

    // Dynamic row positions — EN with legacy row shifts pers/talent down.
    const persLineY   = legacyNewRow ? 98  : LINE_PERS;
    const talentLineY = legacyNewRow ? 125 : LINE_TALENT;

    // ── Row: personality "性格：速度↑魔攻↓" ──────────────────────────────────
    const persLabel  = labels.personality;
    const persEffect = personalityEffects(entry.personality, lang);
    let px = infoX;

    ctx.font = F_LABEL;
    ctx.fillStyle = C.persLabel;
    ctx.textBaseline = 'middle';
    ctx.fillText(persLabel, px, cellY + persLineY + CHIP_H / 2 + 1);
    px += ctx.measureText(persLabel).width;

    ctx.font = F_CHIP;
    ctx.fillStyle = C.persFg;
    ctx.fillText(persEffect, px, cellY + persLineY + CHIP_H / 2 + 1);

    // ── Row: talents "个体值：速度 魔攻 …" (own line — no overflow risk) ───────
    const talentLabel = labels.talents;
    px = infoX;

    ctx.font = F_LABEL;
    ctx.fillStyle = C.talentLabel;
    ctx.fillText(talentLabel, px, cellY + talentLineY + CHIP_H / 2 + 1);
    px += ctx.measureText(talentLabel).width + 2;

    const boosts = [
      entry.talent.hp_boost, entry.talent.phy_atk_boost, entry.talent.mag_atk_boost,
      entry.talent.phy_def_boost, entry.talent.mag_def_boost, entry.talent.spd_boost,
    ];
    const investedIdx = boosts.map((v, j) => v >= 7 ? j : -1).filter(j => j >= 0);

    if (investedIdx.length === 0) {
      ctx.font = F_CHIP;
      ctx.fillStyle = C.textMuted;
      ctx.fillText('—', px, cellY + talentLineY + CHIP_H / 2 + 1);
    } else {
      investedIdx.forEach(bi => {
        px = drawChip(ctx, px, cellY + talentLineY, CHIP_H, talentLabels[bi] ?? '', F_CHIP,
          C.talentBg, C.talentFg);
        px += 3;
      });
    }

    // ── Move-band divider ─────────────────────────────────────────────────────
    const divY = cellY + MOVE_BAND_Y_OFF - 5;
    ctx.fillStyle = C.divider;
    ctx.fillRect(cellX + STRIPE_W + 6, divY, COL_W - STRIPE_W - 12, 1);

    // ── Move slots (bottom band, spans full cell width past stripe) ───────────
    const moveStartX = cellX + STRIPE_W + MOVE_SIDE_PAD;
    const moveY      = cellY + MOVE_BAND_Y_OFF;

    entry.moves.forEach((move, mi) => {
      const mx       = moveStartX + mi * (MOVE_SLOT_W + MOVE_SLOT_GAP);
      const valid    = entry.move_valid[mi] ?? true;
      const moveType = move ? (move.move_type ?? move.type ?? null) : null;
      const iconUrl  = move ? moveIconUrl(move) : null;
      const iconImg  = iconUrl ? (moveIcons[iconUrl] ?? null) : null;

      // Slot background
      ctx.fillStyle = valid ? hexAlpha(sc(moveType?.name), 0.30) : C.invalidBg;
      rrect(ctx, mx, moveY, MOVE_SLOT_W, MOVE_SLOT_H, 5);

      // Move icon (centered horizontally, top-padded by 2px)
      if (iconImg) {
        const iconX = mx + (MOVE_SLOT_W - MOVE_ICON_SZ) / 2;
        ctx.drawImage(iconImg, iconX, moveY + 2, MOVE_ICON_SZ, MOVE_ICON_SZ);
      }

      // Name bar overlay (rounded bottom)
      ctx.fillStyle = valid ? 'rgba(0,0,0,0.62)' : 'rgba(0,0,0,0.75)';
      rrectBottom(ctx, mx, moveY + MOVE_ICON_SZ + 1, MOVE_SLOT_W, MOVE_BAR_H - 1, 5);

      // Move name
      ctx.font = F_MOVE;
      ctx.fillStyle = valid ? '#e2e8f0' : C.invalidFg;
      ctx.textBaseline = 'middle';
      ctx.textAlign = 'center';
      const label = move ? trunc(ctx, pickName(move, lang), MOVE_SLOT_W - 8) : '—';
      ctx.fillText(label, mx + MOVE_SLOT_W / 2, moveY + MOVE_ICON_SZ + MOVE_BAR_H / 2 + 2);

      if (!valid) {
        const stw = ctx.measureText(label).width;
        ctx.strokeStyle = C.invalidFg;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(mx + MOVE_SLOT_W / 2 - stw / 2, moveY + MOVE_ICON_SZ + MOVE_BAR_H / 2 + 2);
        ctx.lineTo(mx + MOVE_SLOT_W / 2 + stw / 2, moveY + MOVE_ICON_SZ + MOVE_BAR_H / 2 + 2);
        ctx.stroke();
      }
      ctx.textAlign = 'left';
    });
  });

  // ── Right sidebar ─────────────────────────────────────────────────────────
  ctx.fillStyle = C.sidebarBg;
  ctx.fillRect(SB_X, 0, SB_W, H);

  // Left border line (subtle)
  ctx.fillStyle = C.brandLine;
  ctx.fillRect(SB_X, 0, 1, H);

  const CX = SB_X + SB_PAD;
  const CW = SB_W - SB_PAD * 2;
  let curY = 20;

  // ── Brand block ──────────────────────────────────────────────────────────
  const LOGO_SZ = 40;
  if (logoIcon) ctx.drawImage(logoIcon, CX, curY, LOGO_SZ, LOGO_SZ);
  const brandTextX = CX + (logoIcon ? LOGO_SZ + 12 : 0);
  const brandName  = labels.brandName;
  ctx.font = '700 22px system-ui,-apple-system,sans-serif';
  ctx.fillStyle = C.text;
  ctx.textBaseline = 'middle';
  ctx.fillText(brandName, brandTextX, curY + LOGO_SZ / 2);
  // Website URL — sits below the brand name, right of the logo icon
  ctx.font = '400 13px system-ui,-apple-system,sans-serif';
  ctx.fillStyle = C.textSub;
  ctx.textBaseline = 'top';
  ctx.fillText('rkteambuilder.com', brandTextX, curY + LOGO_SZ / 2 + 14);
  curY += LOGO_SZ + 20;

  // Divider
  ctx.fillStyle = C.divider;
  ctx.fillRect(CX, curY, CW, 1);
  curY += 1 + 14;

  // ── Team name section ────────────────────────────────────────────────────
  ctx.font = F_SB_LBL;
  ctx.fillStyle = C.textSub;
  ctx.textBaseline = 'top';
  ctx.fillText(labels.teamName, CX, curY);
  curY += 14 + 5;

  ctx.font = F_TEAM_NM;
  ctx.fillStyle = C.text;
  const teamName = data.team_name || labels.teamFallback;
  const tnLines  = wrapLines(ctx, teamName, CW);
  tnLines.slice(0, 2).forEach((line, li) => {
    ctx.fillText(line, CX, curY + li * 30);
  });
  curY += Math.min(tnLines.length, 2) * 30 + 4;

  // Magic item row
  const MI_SZ = 36;
  let miX = CX;
  if (magicIcon) { ctx.drawImage(magicIcon, miX, curY, MI_SZ, MI_SZ); miX += MI_SZ + 8; }
  ctx.font = '500 17px system-ui,-apple-system,sans-serif';
  ctx.fillStyle = C.text;
  ctx.textBaseline = 'middle';
  ctx.fillText(trunc(ctx, pickName(data.magic_item, lang), CW - (magicIcon ? MI_SZ + 8 : 0)), miX, curY + MI_SZ / 2 + 1);
  curY += MI_SZ + 12;

  // Divider
  ctx.fillStyle = C.divider;
  ctx.fillRect(CX, curY, CW, 1);
  curY += 1 + 12;

  // ── Attribution ──────────────────────────────────────────────────────────
  if (data.shared_by) {
    ctx.font = F_SB_BODY;
    ctx.textBaseline = 'top';
    const prefix = labels.sharedBy;
    const pw = ctx.measureText(prefix).width;
    ctx.fillStyle = C.textSub;
    ctx.fillText(prefix, CX, curY);
    ctx.fillStyle = C.text;
    ctx.fillText(trunc(ctx, `@${data.shared_by}`, CW - pw), CX + pw, curY);
    curY += 18 + 10;
  }

  // ── Note section ─────────────────────────────────────────────────────────
  // Ensure breathing room above notes whether or not attribution was shown.
  if (!data.shared_by) curY += 8;

  // Pre-compute QR top so we can clip note lines before they overflow into it.
  const QR  = 180;
  const QBG = QR + 8;  // 4px padding each side
  const qrBgY = showQrSection
    ? H - 12 - 18 - 6 - QBG  // label(18) + gap(6) + QR box(QBG) + bottom pad(12)
    : H - 16;

  ctx.font = '400 16px system-ui,-apple-system,sans-serif';
  ctx.fillStyle = C.textSub;
  const noteText  = (note?.trim()) || NOTE_FALLBACK[lang];
  const noteLines = wrapLines(ctx, noteText, CW);
  const maxNoteLines = Math.max(1, Math.floor((qrBgY - curY - 8) / 22));
  noteLines.slice(0, maxNoteLines).forEach((line, li) => {
    ctx.fillText(line, CX, curY + li * 22);
  });

  // ── QR code section — bottom-anchored ────────────────────────────────────
  if (showQrSection && qrCanvas) {
    const qrBgX = SB_X + (SB_W - QBG) / 2;

    const ctaTopY = qrBgY + QBG + 6;  // label sits just below QR box

    ctx.fillStyle = C.white;
    rrect(ctx, qrBgX, qrBgY, QBG, QBG, 6);
    ctx.drawImage(qrCanvas, qrBgX + 4, qrBgY + 4, QR, QR);

    ctx.font = '500 14px system-ui,-apple-system,sans-serif';
    ctx.fillStyle = C.textSub;
    ctx.textBaseline = 'top';
    ctx.textAlign = 'center';
    ctx.fillText(labels.scanToImport, SB_X + SB_W / 2, ctaTopY);
    ctx.textAlign = 'left';
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

export interface TeamCardProps {
  data: ShareDecodeResponse;
  shareUrl?: string;
  showQr?: boolean;
  lang: 'en' | 'zh';
  note?: string;
  onReady?: () => void;
  canvasRef?: React.RefObject<HTMLCanvasElement | null>;
}

export default function TeamCard({ data, shareUrl, showQr = true, lang, note, onReady, canvasRef }: TeamCardProps) {
  const internalRef  = useRef<HTMLCanvasElement>(null);
  const qrWrapperRef = useRef<HTMLDivElement>(null);
  const onReadyRef   = useRef(onReady);
  useEffect(() => { onReadyRef.current = onReady; });

  const { t } = useI18n();
  const labels: CardLabels = {
    teamName:     t('share.cardTeamName')     ?? (lang === 'zh' ? '队伍名称：' : 'TEAM NAME:'),
    teamFallback: t('share.cardTeamFallback') ?? (lang === 'zh' ? '我的队伍'  : 'My Team'),
    personality:  t('share.cardPersonality')  ?? (lang === 'zh' ? '性格：'    : 'Personality: '),
    talents:      t('share.cardTalents')      ?? (lang === 'zh' ? '个体值：'  : 'Talents: '),
    legacy:       t('share.cardLegacy')       ?? (lang === 'zh' ? '血脉：'    : 'Legacy: '),
    sharedBy:     t('share.cardSharedBy')     ?? (lang === 'zh' ? '分享者：'  : 'Shared by '),
    scanToImport: t('share.cardScanToImport') ?? (lang === 'zh' ? '扫码导入队伍' : 'Scan to import'),
    brandName:    t('share.cardBrandName')    ?? (lang === 'zh' ? '洛手配队器' : 'RK Team Builder'),
  };

  const showQrSection = showQr && !!shareUrl;

  const draw = useCallback(async (mounted: { current: boolean }) => {
    const canvas = canvasRef?.current ?? internalRef.current;
    if (!canvas) return;

    // Scale canvas buffer by devicePixelRatio for crisp HiDPI rendering.
    // Cap at 2× to avoid oversized buffers on 3× devices.
    const dpr = Math.min(window.devicePixelRatio || 1, 2);

    // Only resize the buffer when dimensions actually change — assigning
    // canvas.width/height clears the canvas immediately, which would cause a
    // blank-frame flash while assets are loading asynchronously.
    if (canvas.width !== W * dpr || canvas.height !== H * dpr) {
      canvas.width  = W * dpr;
      canvas.height = H * dpr;
    }

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    // setTransform resets the matrix (safe to call on every draw, unlike scale
    // which compounds on repeated calls without a prior reset).
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    await document.fonts.ready;
    const assets = await loadAssets(data);
    if (!mounted.current) return;

    const qrCanvas = showQrSection
      ? (qrWrapperRef.current?.querySelector('canvas') ?? null)
      : null;

    renderCard(ctx, data, assets, lang, showQrSection, qrCanvas, labels, note);
    if (mounted.current) onReadyRef.current?.();
  }, [data, shareUrl, lang, showQrSection, labels, note, canvasRef]);

  useEffect(() => {
    const mounted = { current: true };
    draw(mounted);
    return () => { mounted.current = false; };
  }, [draw]);

  // Redraw when returning from another app — iOS may clear the canvas backing
  // store while the tab is frozen/backgrounded. Uses the same mounted-flag
  // pattern as the main draw effect to cancel stale in-progress redraws.
  useEffect(() => {
    let lastMounted: { current: boolean } | null = null;
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      if (lastMounted) lastMounted.current = false;
      lastMounted = { current: true };
      draw(lastMounted);
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      document.removeEventListener('visibilitychange', onVisible);
      if (lastMounted) lastMounted.current = false;
    };
  }, [draw]);

  return (
    <div style={{ position: 'relative', width: '960px', height: '720px' }}>
      <canvas
        ref={canvasRef ?? internalRef}
        style={{ display: 'block', width: '960px', height: '720px' }}
      />
      {showQrSection && (
        <div
          ref={qrWrapperRef}
          style={{ position: 'absolute', left: '-9999px', top: 0 }}
          aria-hidden="true"
        >
          {/* Render at 2× (360px) so it maps 1:1 into the 2× HiDPI canvas buffer */}
          <QRCodeCanvas value={shareUrl!} size={360} bgColor="#ffffff" fgColor="#0b1120" />
        </div>
      )}
    </div>
  );
}
