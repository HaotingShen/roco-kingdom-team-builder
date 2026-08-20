/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Axios base URL — set in .env.local or inline for TapTap build */
  readonly VITE_API_BASE_URL?: string;
  /** Prefix for all static image/asset URLs — set to https://rkteambuilder.com in TapTap build */
  readonly VITE_ASSET_BASE_URL?: string;
  /** When truthy, ad banners are hidden (TapTap platform rules prohibit ads) */
  readonly VITE_HIDE_ADS?: string;
  /** When "true", use createHashRouter instead of createBrowserRouter (TapTap CDN has no SPA fallback) */
  readonly VITE_HASH_ROUTER?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
