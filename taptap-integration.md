# TapTap Integration

This document covers the TapTap game tool submission for RK Team Builder (洛手配队器).

## Overview

TapTap hosts the app as a static ZIP served from their CDN (`3rd-tool-h5-al.tapimg.com`), rendered inside a Chrome 89 webview. This has several constraints vs. the normal production build:

| Constraint | Solution |
|---|---|
| No server-side SPA fallback (CDN serves flat files) | `createHashRouter` — routes use `#/build`, `#/dex`, etc. |
| Served from arbitrary CDN sub-path (relative assets) | `base: "./"` in vite.config.ts for TapTap mode |
| Cross-origin API/image requests | `VITE_API_BASE_URL` and `VITE_ASSET_BASE_URL` set to `https://rkteambuilder.com` |
| `window.confirm()` / `alert()` silently blocked in webview | Replaced with React `ConfirmDialog` + `toast.error()` |
| `window.location.origin` returns TapTap CDN domain | Share URLs use `VITE_ASSET_BASE_URL \|\| window.location.origin` |
| Ad banners prohibited by TapTap platform rules | `VITE_HIDE_ADS=true` |
| Login/account features prohibited by TapTap platform rules | `VITE_HIDE_AUTH=true` — anonymous-only, 1 analysis/day, no team saving |
| External clickable links prohibited (stay inside webview) | Plain text domain mentions only, no `<a href>` buttons |
| Cross-site cookies (auth) | `COOKIE_SAMESITE=none` + CSRF token system |

## Environment Variables (TapTap build only)

Defined in `frontend/.env.taptap` and inlined in the `build:taptap` npm script (inline vars take precedence over `.env.local`):

```
VITE_API_BASE_URL=https://rkteambuilder.com/api
VITE_ASSET_BASE_URL=https://rkteambuilder.com
VITE_HIDE_ADS=true
VITE_HIDE_AUTH=true
VITE_HASH_ROUTER=true
```

None of these are set in the normal production build — all fallback correctly to production defaults (empty string or undefined = falsy).

### VITE_HIDE_AUTH behaviour

When `VITE_HIDE_AUTH=true`, the TapTap build:
- Hides UserMenu, admin link (Topbar)
- Hides donate button and DonationModal (also gated by `VITE_HIDE_ADS`)
- Hides My Teams link (Sidebar) and Teams tab (BottomNav mobile)
- Hides Save Team / Save Analysis buttons (BuilderPage, AnalysisResults)
- Hides unsaved-work warning banner (BuilderPage)
- Replaces SaveTeamModal content with plain-text redirect message
- Replaces 429 quota error with plain-text "visit rkteambuilder.com" message
- Shows plain-text placeholder on TeamsListPage instead of "create a team"

## Build & Submit

```bash
# 1. WSL — build
cd "/mnt/d/Alan/Github Projects/roco-kingdom-team-builder/frontend"
rm -rf rk-team-builder          # remove previous build folder if it exists
npm run build:taptap
mv dist-taptap rk-team-builder

# 2. PowerShell — zip (contents, NOT the folder)
Compress-Archive -Path "D:\Alan\Github Projects\roco-kingdom-team-builder\frontend\rk-team-builder\*" -DestinationPath "D:\Alan\Github Projects\roco-kingdom-team-builder\frontend\taptap-submission.zip" -Force
```

Then upload `frontend/taptap-submission.zip` to TapTap tool management.

**Important zip rule:** TapTap requires `index.html` at the root of the zip. Always use `\*` (contents) not the folder itself in `Compress-Archive`.

## Files Changed for TapTap Support

| File | Change |
|---|---|
| `frontend/src/router.tsx` | Conditional `createHashRouter` when `VITE_HASH_ROUTER=true` |
| `frontend/src/vite-env.d.ts` | TypeScript declarations for all `VITE_*` env vars |
| `frontend/.env.taptap` | TapTap build config |
| `frontend/package.json` | Added `build:taptap` script with inlined env vars |
| `frontend/vite.config.ts` | Function form; `base: "./"` + custom rollup input for `mode=taptap` |
| `frontend/index.taptap.html` | Separate HTML entry: relative paths, no canonical/OG tags, loading screen |
| `frontend/src/lib/images.ts` | `assetBase` prefix using `VITE_ASSET_BASE_URL` (empty string in production = no change) |
| `docker-compose.prod.yml` | `COOKIE_SAMESITE=none` + TapTap CDN in `ALLOWED_ORIGINS` |
| `frontend/src/components/ConfirmDialog.tsx` | New React modal replacing `window.confirm()` |
| `frontend/src/components/Topbar.tsx` | `VITE_HIDE_ADS/AUTH` gating; ConfirmDialog replacing `window.confirm()` |
| `frontend/src/components/Sidebar.tsx` | `VITE_HIDE_AUTH` gates My Teams link |
| `frontend/src/components/BottomNav.tsx` | `VITE_HIDE_AUTH` gates Teams tab on mobile |
| `frontend/src/components/SaveTeamModal.tsx` | `VITE_HIDE_AUTH` replaces modal body with plain-text redirect |
| `frontend/src/components/AnalysisResults.tsx` | `VITE_HIDE_AUTH` hides save analysis section |
| `frontend/src/features/builder/BuilderPage.tsx` | `VITE_HIDE_AUTH` hides save button, unsaved-work banner; custom 429 error message |
| `frontend/src/features/teams/TeamsListPage.tsx` | `VITE_HIDE_AUTH` placeholder; ConfirmDialog replacing `window.confirm()` |
| `frontend/src/features/teams/SavedTeamPage.tsx` | ConfirmDialog replacing `window.confirm()` |
| `frontend/src/features/share/sharePayload.ts` | `VITE_ASSET_BASE_URL \|\| window.location.origin` for share URL base |
| `frontend/src/features/share/ImportPage.tsx` | Same fix for QR code URL |
| `frontend/src/i18n.tsx` | Added keys for ConfirmDialog, TapTap redirect messages |

## Known Issues

### Canvas export broken in TapTap webview

**Affected features:** Download PNG, Copy Image, Share (mobile)  
**Unaffected:** Copy Link

**Root cause:** `TeamCard` draws monster images from `rkteambuilder.com` onto a canvas. In Chrome 89 webview, cross-origin images (loaded without `crossOrigin="anonymous"`) taint the canvas, causing `canvas.toBlob()` to throw a SecurityError.

**Proper fix (not yet implemented):** Requires both:
1. S3 CORS policy on `rktb-frontend` bucket
2. CloudFront behavior updated to forward `Origin` header
3. `el.crossOrigin = "anonymous"` in `TeamCard.tsx` `loadImg()`

**Current state:** Buttons remain visible. Users get `toast.error("导出失败，请重试。")`. Copy Link works correctly and generates a valid `rkteambuilder.com/import?t=...` URL.

## Submission History

| Date | Version | Notes |
|---|---|---|
| 2026-04-21 | v1 | Failed — zip had folder at root, not `index.html` |
| 2026-04-21 | v2 | Failed — `createBrowserRouter` → 404 on CDN (no SPA fallback) |
| 2026-04-21 | v3 | Loaded successfully. CSRF warnings on login (self-healing, not a bug) |
| 2026-04-22 | v4 | `window.confirm/alert` replaced with React ConfirmDialog + toast. Awaiting review. |
| 2026-04-22 | v5 | Rejected — 「含有【打赏】」and 「含有账号登录功能」. Added `VITE_HIDE_AUTH=true`: hides login UI, donate button, save buttons, teams tab. Anonymous-only UX with plain-text rkteambuilder.com mentions. |
