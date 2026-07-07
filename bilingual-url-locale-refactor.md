# URL-Based Bilingual Locale Refactor — Implementation Plan

> ✅ **IMPLEMENTED 2026-07-07 (Phase 1 frontend+backend).** All code changes below
> shipped: `/:lang` routing, URL-derived locale with `switchLang`, hreflang/canonical
> per page, hash-aware inline script, locale email links, and the 2,062-URL
> hreflang sitemap. Verified: typecheck + lint (0 errors) + prod build + TapTap
> build + 178 backend tests + Playwright SEO harness (74/74) + behavioral smoke
> (lang-switch preserves path/query, bad-locale→/en, dev fallback). **Phase 2 (the
> CloudFront `rktb-locale-routing` function that 301s legacy URLs and 302s the root)
> is the remaining step** — function code is committed at
> `ops/cloudfront/rktb-locale-routing.js`; deploy per Section N3.
> Original review notes retained below for reference.
>
> ⏸️ **(historical) PROPOSED — NOT IMPLEMENTED. REVISED 2026-07-07 to be implementation-ready**
> after a full re-validation against the current codebase and the LIVE CloudFront
> config (read-only AWS checks). The strategy is unchanged; these amendments were
> folded in (look for **REVISED 2026-07-07** markers):
> 1. **Trailing-slash normalization** — the original H7 emitted canonical `/en`
>    while sitemap/hreflang/redirects used `/en/`; now normalized (`/en/` for the
>    homepage, no trailing slash deeper) and the CF function 301s `/en` → `/en/`.
> 2. **Provider restructure replaced** — moving `I18nProvider` inside the router
>    would crash `AuthProvider` (it calls `useI18n()` since 2026-06). New approach:
>    provider stays put; a `<LocaleFromUrl>` child of the router syncs URL → provider;
>    `setLang` (5 consumers, not 1) is replaced by a navigation-based `switchLang`.
> 3. **TapTap + dev fallbacks** — pathname-only locale detection would show English
>    to TapTap's hash-router users; inline script and wildcard route now fall back
>    to hash → localStorage → navigator.language.
> 4. **Query-string preservation is load-bearing** (share links are `/import?t=…`);
>    both redirect branches now serialize QS; live sandbox test is mandatory (P2).
> 5. `/announcements` route added throughout; `verify-robots.mjs` does NOT exist in
>    the repo (L3 rewritten); audit greps extended for `location.pathname` compares.
> 6. Resolved former unknowns: P1 (preferred_language exists; email functions already
>    take `language` — H11 is now a 3-line change), P3, P5, P12, P13 (CloudFront limbo
>    verified live 2026-07-07: `rktb-spa-routing` associated on viewer-request,
>    `/api/*` behavior has zero function associations).
> Still open before implementation: P2 (CF querystring sandbox test) and P11
> (Bing/Baidu webmaster state — ask the site owner).

**Site:** rkteambuilder.com
**Goal:** Make the Chinese version of every public page crawlable and indexable as a unique URL, so Google/Baidu/Bing can rank it separately from the English version.

---

## A. Executive Summary

### The problem in one line
Language lives in `localStorage` ([frontend/src/i18n.tsx:1642](frontend/src/i18n.tsx#L1642)) and every public URL serves both languages from the same path. Googlebot starts every crawl with empty localStorage, so it only ever sees the English version. The hreflang tags in `index.html` claim both languages live at `https://rkteambuilder.com/` (same URL) — Google treats this as a single English page and silently drops the `hreflang="zh"` declaration.

### The fix in one line
Move locale into the URL path (`/en/dex/monsters/123` and `/zh/dex/monsters/123`), derive the active language from `useParams()` instead of localStorage, regenerate the sitemap with both variants plus reciprocal hreflang annotations, and add CloudFront-level 301 redirects from every legacy URL to its `/en/` equivalent so existing inbound links and indexed pages don't break.

### Why path-prefix (not subdomain or query string)
Verified against this codebase:
- **Subdomains** (`en.rkteambuilder.com` / `zh.rkteambuilder.com`) would require a second CloudFront alternate domain, second ACM cert SAN (the wildcard cert in [deployment-complete.md:172-174](deployment-complete.md#L172) does cover it, but still requires distribution config changes), and would split cookies — the production cookies are deliberately `path="/"` with `domain=None` (exact origin), so login on `en.` would not authenticate `zh.`. Significant infrastructure risk for no SEO benefit over path prefix.
- **Query string** (`?lang=zh`): Google's documentation explicitly states query parameters are **not** treated as separate locales. Worst option.
- **Path prefix** (`/en/dex` / `/zh/dex`): industry standard, requires only frontend changes + one CloudFront Function update + sitemap regeneration. Cookies, auth, analytics, API all unaffected.

### Expected impact
- **Crawlable URLs grow from 1,030 to ~2,062** (each indexable page gets an `/en/` and `/zh/` variant; counts re-verified 2026-07-07, incl. `/announcements`).
- **Baidu indexability:** unlocks ~1,031 Chinese-language URLs. Critical for the Chinese-origin game's primary audience — but see M9/M10: as a client-rendered SPA, the Baidu win from this plan alone is mostly the Chinese `<title>` (H9); prerendering is the follow-up that fully unlocks Baidu, and without an ICP, Baidu webmaster submission stays limited.
- **Existing SEO equity:** preserved via 301 redirects from legacy paths → `/en/` paths.
- **Engineering effort:** roughly 1-2 days of focused work across frontend routing, ~50 link sites, sitemap regen, CloudFront Function update, and verification.
- **User-visible behavior:** every URL gets longer by 3 characters. Language switcher becomes a navigation instead of a state update.

---

## B. Verified Current Behavior

A fresh visit to `https://rkteambuilder.com/dex/monsters/1`:

1. **CloudFront** distribution `E1S4H9ALERPPY0` ([spa-routing-seo-fix.md:31](spa-routing-seo-fix.md#L31)) receives the request.
2. Path doesn't match `/api/*` behavior, so the default behavior (S3) handles it.
3. **CloudFront Function `rktb-spa-routing`** ([spa-routing-seo-fix.md:295-317](spa-routing-seo-fix.md#L295)) rewrites the URI to `/index.html` because the path has no dot and isn't `/`.
4. **S3** returns `index.html` with HTTP 200 (the rewrite means S3 sees `/index.html`, not the SPA path).
5. **Browser** parses HTML. Before React boots, the inline script at [frontend/index.html:112-133](frontend/index.html#L112) runs:
   ```js
   const lang = localStorage.getItem('lang') || 'en';
   document.title = lang === 'zh' ? '洛手配队器 ...' : 'RK Team Builder ...';
   ```
   For Googlebot (empty localStorage) this is always `'en'`.
6. **React mounts.** `I18nProvider` ([frontend/src/i18n.tsx:1640-1655](frontend/src/i18n.tsx#L1640)) initializes:
   ```ts
   const browserLang: Lang = navigator.language.startsWith("zh") ? "zh" : "en";
   const [lang, setLang] = useState<Lang>((localStorage.getItem("lang") as Lang) || browserLang);
   ```
   Crawler `navigator.language` is typically `en-US` → lang = `'en'`.
7. **MonsterDetailPage** runs `useSeoMeta` ([frontend/src/features/dex/MonsterDetailPage.tsx:116-128](frontend/src/features/dex/MonsterDetailPage.tsx#L116)):
   - Title gets the English version: `"Dimo | RK Team Builder"`
   - Canonical → `https://rkteambuilder.com/dex/monsters/1` (no locale segment)
   - Description, OG title, OG description, Twitter title/description — all English
   - Robots → `index, follow`
8. **The same URL** can render in Chinese only if the user had previously toggled language. Then localStorage = `'zh'`, and the same `/dex/monsters/1` URL shows Chinese content. **The URL never changes when the user switches language** ([frontend/src/components/Topbar.tsx:185-193](frontend/src/components/Topbar.tsx#L185)).

### Key facts verified
| Fact | Source |
|---|---|
| Single-route definition: 19 paths under one `/` parent (18 at time of writing; `/announcements` added since — re-verified 2026-07-07) | [router.tsx](frontend/src/router.tsx) |
| Language stored only in `localStorage['lang']` | [i18n.tsx:1642,1649](frontend/src/i18n.tsx#L1642) |
| Default language is browser's `navigator.language` | [i18n.tsx:1641](frontend/src/i18n.tsx#L1641) |
| Language switcher = button in `Topbar.tsx`, no navigation | [Topbar.tsx:186-187](frontend/src/components/Topbar.tsx#L186) |
| 53 files consume `useI18n()` | reported by Explore agent |
| `useSeoMeta.BASE_URL` hardcoded to root domain | [useSeoMeta.ts:4](frontend/src/hooks/useSeoMeta.ts#L4) |
| `index.html` hreflang en + zh + x-default all point to `/` | [index.html:17-19](frontend/index.html#L17) |
| Sitemap contains 1,030 URLs, none with locale (re-counted 2026-07-07) | [sitemap.xml](frontend/public/sitemap.xml) |
| 6 pages call `useSeoMeta` with language-aware titles | reported by Explore agent |
| 11 pages render `<NoIndex>` (no language awareness in noindex) | [spa-routing-seo-fix.md:222-233](spa-routing-seo-fix.md#L222) |
| 18 unique internal-path strings hardcoded across ~30 components | reported by Explore agent |
| 3 backend email URL builders, all use `f"{FRONTEND_URL}/auth/..."` — and all three functions ALREADY accept `language: str = "en"` (used for email body content; verified 2026-07-07) | [email_service.py:99,111,179,191,260,272](backend/email_service.py#L99) |
| Cookies use `path="/"`, `domain=None`, `samesite=none`, `secure=true` | [docker-compose.prod.yml](docker-compose.prod.yml) + [deployment-complete.md:1029-1052](deployment-complete.md#L1029) |
| Backend has NO Accept-Language header handling | reported by Explore agent (no matches) |
| Umami analytics uses `defer` script, language-agnostic | [umami-setup.md:26](umami-setup.md#L26) |
| CI/CD: GitHub Actions → S3 sync + CloudFront `/*` invalidation | [.github/workflows/deploy.yml:120-139](.github/workflows/deploy.yml#L120) |

---

## C. Files Inspected

### Directly read
- `frontend/index.html`
- `frontend/src/router.tsx`
- `frontend/src/i18n.tsx` (lines 1630-1662)
- `frontend/src/hooks/useSeoMeta.ts`
- `frontend/src/components/Topbar.tsx` (lines 180-204)
- `frontend/src/components/NoIndex.tsx`
- `frontend/src/features/dex/MonsterDetailPage.tsx` (SEO block)
- `frontend/public/sitemap.xml`
- `frontend/public/robots.txt`
- `frontend/vite.config.ts`
- `backend/scripts/maintenance/generate_sitemap.py`
- `.github/workflows/deploy.yml`
- `docker-compose.prod.yml`
- `umami-setup.md`
- `deployment-complete.md` (partial — first ~1200 of 2943 lines, covering CloudFront/S3/CF Function topology)
- `spa-routing-seo-fix.md` (full)

### Inspected via Explore agents (cross-verified by spot-reads)
- All ~30 components that contain `<Link>`, `<NavLink>`, `useNavigate`
- All 6 pages calling `useSeoMeta`
- All 11 pages rendering `<NoIndex>`
- All backend email URL construction sites
- `backend/email_service.py`, `backend/config.py`
- `backend/main.py` cookie-setting code
- `frontend/src/lib/api.ts`, `frontend/src/main.tsx`, `frontend/src/App.tsx`

### Not inspected (UNVERIFIED — see Section P)
- The live CloudFront distribution `E1S4H9ALERPPY0` configuration (assumed to match the spa-routing-seo-fix.md description)
- The actual Search Console state (which of the 1,030 sitemap URLs are currently indexed)
- Baidu / Bing webmaster tool state
- DNS configuration at Cloudflare (assumed to match deployment-complete.md)
- Whether `rds-az-migration-runbook.md` has any locale-relevant content (file referenced by user but unrelated topic per its title)
- The full backend cookie-setting code in `backend/auth.py` (I have the version reported by Explore agent — direct read recommended before implementation)
- `user-auth-system.md` lines 1-end (only grepped, not fully read)
- Several specific call sites flagged as ambiguous in the link inventory (e.g. `MonsterDetailPage.tsx:327`)

---

## D. Current Route / Language / SEO Architecture

### Route map (verified)
```
/                                     → BuilderPage (index)              indexable
/build                                → BuilderPage (duplicate)          indexable, canonical → /
/build/analyze/:slot                  → MonsterAnalysisPage              noindex,nofollow
/dex                                  → DexPage                          indexable
/dex/monsters/:id                     → MonsterDetailPage                indexable
/dex/moves/:id                        → MoveDetailPage                   indexable
/teams                                → TeamsListPage                    noindex,follow
/teams/:id                            → SavedTeamPage                    noindex,follow
/auth/login                           → LoginPage                        noindex,nofollow
/auth/register                        → RegisterPage                     noindex,nofollow
/auth/forgot-password                 → ForgotPasswordPage               noindex,nofollow
/auth/reset-password                  → ResetPasswordPage                noindex,nofollow
/auth/verify                          → VerifyEmailPage                  noindex,nofollow
/auth/confirm-email                   → ConfirmEmailChangePage           noindex,nofollow
/settings                             → SettingsPage                     noindex,nofollow
/admin                                → AdminPage                        noindex,nofollow
/feedback                             → FeedbackPage                     noindex,follow
/import                               → ImportPage                       noindex,follow
/announcements                        → AnnouncementsPage                indexable (added 2026-04; uses useSeoMeta with canonicalPath "/announcements", no noindex)
```

### Language flow
```
1. Initial HTML loads (S3 → CloudFront).
2. Inline <script> in index.html reads localStorage['lang'] → sets <title> + loading text.
3. React mounts. I18nProvider reads same key + falls back to navigator.language.
4. useI18n() hook is consumed by 53 files.
5. Each page that calls useSeoMeta overrides title/description per language via `lang === "zh" ? ... : ...` ternary.
6. Topbar's language button calls setLang(), which writes localStorage and updates React state.
7. URL never changes. Page does not reload.
8. document.documentElement.lang is updated to "en" or "zh" (a11y signal).
```

### SEO machinery
```
index.html sets static defaults (currently both hreflang en/zh point to `/`)
                              ↓
React mounts; useSeoMeta hook on each page overrides:
    document.title
    <meta name="description">
    <meta property="og:title|og:description|og:url">
    <meta name="twitter:title|twitter:description">
    <link rel="canonical">
    <meta name="robots">
                              ↓
Sitemap (frontend/public/sitemap.xml): 1,030 language-neutral URLs.
Robots.txt: allows all, points to sitemap.
                              ↓
Generated by: backend/scripts/maintenance/generate_sitemap.py
              Reads Monster.id + Move.id from DB.
              Outputs static file written to frontend/public/sitemap.xml.
              Run manually before frontend build.
```

### Hosting topology (from deployment-complete.md + spa-routing-seo-fix.md)
```
Cloudflare DNS → CloudFront (E1S4H9ALERPPY0)
                    ├── /api/*  → EC2/Nginx → FastAPI
                    └── /*      → CloudFront Function `rktb-spa-routing`
                                    ├── /api/* (defense) → passthrough
                                    ├── anything with dot → passthrough (static assets)
                                    └── else → rewrite to /index.html
                                  → S3 bucket rktb-frontend (website hosting mode)
```

---

## E. Problems Found (With Evidence)

### E1. Chinese content is structurally invisible to all search engines
- **Symptom:** Googlebot, Bingbot, and Baiduspider can only ever index the English version of any URL because language depends on localStorage.
- **Evidence:**
  - [i18n.tsx:1642](frontend/src/i18n.tsx#L1642): `localStorage.getItem("lang") as Lang || browserLang` — bots have empty localStorage, fall back to `navigator.language`, which all bots set to `en-US` by default.
  - [index.html:112-133](frontend/index.html#L112): even the inline pre-React title-setting script uses the same localStorage key.
  - All 6 useSeoMeta call sites compute titles/descriptions via `lang === "zh" ? "..." : "..."` ternaries — meaning the meta tags Google sees are *always* English for any bot crawl.
- **Severity:** Critical. The entire Chinese-language SEO market is unreachable.

### E2. Same URL serves multiple languages — duplicate-content trap
- **Symptom:** `/dex/monsters/1` can show English OR Chinese depending on visitor history. To Google, that's one URL with non-deterministic content.
- **Evidence:**
  - [Topbar.tsx:186-187](frontend/src/components/Topbar.tsx#L186): `onClick={() => setLang(lang === "en" ? "zh" : "en")}` — no `navigate()` call, URL unchanged.
  - `useSeoMeta` writes `canonicalPath ?? pathname` ([useSeoMeta.ts:22](frontend/src/hooks/useSeoMeta.ts#L22)) — same canonical URL regardless of which language is being shown.
- **Severity:** Critical. Hurts ranking for both languages.

### E3. Hreflang tags violate Google's "must be unique URLs" rule
- **Symptom:** Both `hreflang="en"` and `hreflang="zh"` in `index.html` point to the same URL — Google's documentation explicitly says this is invalid and the tags will be dropped.
- **Evidence:** [index.html:17-19](frontend/index.html#L17):
  ```html
  <link rel="alternate" hreflang="x-default" href="https://rkteambuilder.com/" />
  <link rel="alternate" hreflang="en" href="https://rkteambuilder.com/" />
  <link rel="alternate" hreflang="zh" href="https://rkteambuilder.com/" />
  ```
- **Severity:** High. No reciprocal language pairing exists.

### E4. Canonical URLs don't carry language information
- **Symptom:** Even if Chinese content were rendered, the canonical tag would still point to a language-neutral URL.
- **Evidence:** [useSeoMeta.ts:22,34](frontend/src/hooks/useSeoMeta.ts#L22): canonical is just `BASE_URL + pathname`. No language info.
- **Severity:** High. Compounds E2.

### E5. Sitemap lists no language variants
- **Symptom:** All 1,030 sitemap URLs are language-neutral. Google has no static signal that Chinese versions exist.
- **Evidence:** [sitemap.xml](frontend/public/sitemap.xml) + [generate_sitemap.py:55-62](backend/scripts/maintenance/generate_sitemap.py#L55) — no hreflang annotations, no `/en/` or `/zh/` variants.
- **Severity:** High. Even with hreflang in the HTML, the sitemap signal is missing.

### E6. Backend email links default to English-only URLs
- **Symptom:** Verification/reset/email-change links open in whatever language the user's browser detects on first visit — not necessarily what the user signed up in.
- **Evidence:** [email_service.py:111,191,272](backend/email_service.py#L111) — all three URLs are `{FRONTEND_URL}/auth/...`, no language path component.
- **Severity:** Medium. Not an SEO issue, but a UX issue that becomes worse after the refactor unless we fix it now.

### E7. Hardcoded paths everywhere in components
- **Symptom:** ~50 sites use literal path strings (`<Link to="/build">`, `navigate("/auth/login")`, etc.). After the refactor, every one must compose `/${lang}/...`.
- **Evidence:** Reported by Explore agent — unique hardcoded path strings include `/`, `/build`, `/dex`, `/teams`, `/feedback`, `/import`, `/admin`, `/settings`, `/auth/login`, `/auth/register`, `/auth/forgot-password`, `/auth/reset-password`, `/auth/verify`. Plus template literals for dynamic IDs (`/dex/monsters/${id}`, `/teams/${id}`).
- **Severity:** Medium (effort). All catchable by removing the literal strings and routing through a helper.

### E8. The CloudFront SPA-rewriting function has no locale awareness
- **Symptom:** It rewrites `/anything-without-dot` → `/index.html`. That logic is correct for SPA fallback but does nothing for legacy → locale 301 redirects.
- **Evidence:** [spa-routing-seo-fix.md:295-317](spa-routing-seo-fix.md#L295).
- **Severity:** High. We need to extend this function (or replace it) to emit 301s for legacy paths.

---

## F. Recommended Target Architecture

### F1. URL structure (chosen: path prefix)
```
https://rkteambuilder.com/en/                       English homepage (BuilderPage)
https://rkteambuilder.com/zh/                       Chinese homepage (BuilderPage)
https://rkteambuilder.com/en/dex                    English Dex
https://rkteambuilder.com/zh/dex                    Chinese Dex
https://rkteambuilder.com/en/dex/monsters/123       English monster detail
https://rkteambuilder.com/zh/dex/monsters/123       Chinese monster detail
... (every existing route gets an /en/ and /zh/ variant)
```

**Drop the `/build` route** in the new structure. Today `/build` is a duplicate of `/`. After the refactor, the canonical English homepage is `/en/`. There's no benefit to keeping `/en/build` as a separate route — it would force us to set `canonicalPath: "/en"` on it, creating the same duplicate-content pattern. Simpler: route `/${lang}/` to BuilderPage and leave `/build` to a single 301 redirect (`/build → /en/`, `/en/build → /en/`, `/zh/build → /zh/`).

### F2. Why path prefix beats the alternatives
| Approach | Cookies | Cert/DNS | Infra change | SEO | Verdict |
|---|---|---|---|---|---|
| Path prefix `/en/`, `/zh/` | unaffected (`path="/"`) | none | only CloudFront Function + sitemap | ✅ standard | **Chosen** |
| Subdomain `en.`, `zh.` | breaks login (cookies on `rkteambuilder.com` exact host) | new ACM SAN + Cloudflare A records | CloudFront alternate domain mapping | ✅ standard | Rejected: cookie + infra risk |
| Query string `?lang=zh` | unaffected | none | trivial | ❌ Google doesn't treat as locale | Rejected: doesn't solve the actual problem |
| Status quo (localStorage) | n/a | n/a | n/a | ❌ critical bug | Rejected |

### F3. Language detection at root
- `/` is no longer a route the SPA renders. It's a CloudFront-Function-level 302 redirect to `/en/` or `/zh/` based on `Accept-Language` header (with `Vary: Accept-Language`).
- Logic: if the first language tag in `Accept-Language` starts with `zh`, redirect to `/zh/`; otherwise `/en/`. (Default `/en/` because English is the global default, and Google's en-US Googlebot will land naturally on `/en/`.)
- Why 302 not 301: Accept-Language varies per user, so the redirect target varies — a 301 would get cached by the browser and ignore future Accept-Language differences. 302 is the correct choice for content-negotiated redirects.

### F4. Legacy URL handling
- Every legacy unprefixed path (`/dex`, `/dex/monsters/1`, `/build`, `/teams`, `/auth/login`, etc.) gets a **301 permanent redirect to `/en/<same path>`**.
- Why 301 not 302: the legacy path is being permanently replaced. 301 transfers PageRank/equity. Browser caches the redirect — a benefit here since the mapping never changes.
- Why default to `/en/` (not Accept-Language-based)? Two reasons:
  1. 301s are cached. If we redirected based on Accept-Language, a Chinese user clicking an old `/dex` bookmark would get cached `/zh/dex` forever, even after switching language preference.
  2. Google's English Googlebot crawls these — sending it to `/en/` is the cleanest equity transfer.

### F5. In-app language switching — REVISED 2026-07-07
- `setLang` is NOT simply removed — it has **five** consumers today, not one:
  `Topbar` (~line 214, the visible toggle), `AuthProvider:91` (applies
  `user.preferred_language` on session restore), `LoginPage:48` and
  `RegisterPage:69` (cross-device language sync after login/registration), and
  `SettingsPage:90`. All five represent real product behavior that must survive.
- The context replaces `setLang` with a navigation-based **`switchLang(next)`**:
  it no-ops when `next === lang`, writes `localStorage['lang']` (preference
  signal), and navigates to the locale-swapped equivalent of the current URL
  (path + search + hash preserved). Implemented via the `<LocaleFromUrl>`
  registration described in F6/H3 — the provider itself sits outside the router
  and cannot call `useNavigate` directly.
- Login/restore semantics preserved: `switchLang(user.preferred_language)`
  navigates you to your preferred locale's URL (no-op if you're already on it) —
  same observable behavior as today's `setLang`, now URL-visible.
- (Optional v2 refinement unchanged: a `lang` cookie the CloudFront Function
  could consult at the root redirect — still deferred, see P10.)

### F6. Active language derivation — REVISED 2026-07-07
- **Original approach (moving `I18nProvider` inside the router) is DEAD**: since
  2026-06, `AuthProvider` — which sits OUTSIDE the router in `main.tsx` — calls
  `useI18n()` ([AuthProvider.tsx:58](frontend/src/features/auth/AuthProvider.tsx#L58)).
  Moving the provider below the router would make that hook throw at boot. The
  real `main.tsx` tree is `ErrorBoundary > I18nProvider > QueryClientProvider >
  AuthProvider > AppReadyProvider > (Toaster + RouterProvider)`.
- **New approach — provider stays put; the URL is still the single source of truth:**
  1. `I18nProvider` keeps internal `lang` state, initialized by a
     `detectInitialLang()` chain (URL path → URL hash → localStorage →
     `navigator.language`) that is correct for browser-router, hash-router
     (TapTap), and the pre-router first render.
  2. A tiny **`<LocaleFromUrl />`** component rendered INSIDE the router (child
     of the `/:lang` element) reads `useParams().lang` + `useNavigate()` and,
     in an effect, (a) syncs the URL lang into the provider and (b) registers a
     `swap(next)` callback the provider's `switchLang` delegates to.
  3. `main.tsx` needs **no changes**. `AuthProvider` keeps working. Every
     `useI18n()` consumer keeps working.
- Validation of `:lang` stays in the route element (H2): anything other than
  `en`/`zh` redirects to `/en${restOfPath}`.
- A side-effect still writes `lang` to localStorage (preference memory for the
  wildcard/dev/TapTap fallback and any future root-redirect cookie).

### F7. SEO artifacts per page (all useSeoMeta call sites)
For every page that's indexable:
- **Canonical:** self (`https://rkteambuilder.com/<lang>/<rest>`)
- **Hreflang (3 tags):**
  - `hreflang="en"` → `/en/<rest>`
  - `hreflang="zh"` → `/zh/<rest>`
  - `hreflang="x-default"` → `/en/<rest>` (English is default)
- **OG URL:** matches canonical
- **OG locale + alternate:** `en_US` + `zh_CN` swapped per page

For noindex pages: canonical + hreflang still emitted (so users sharing a `/zh/teams` link to a friend still get the proper Chinese page), but `robots: noindex` keeps them out of search.

### F8. Sitemap structure
Use Google's xhtml:link hreflang annotation format. One `<url>` entry per (locale, page) pair, each entry listing all alternates including itself:
```xml
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
  <url>
    <loc>https://rkteambuilder.com/en/dex/monsters/1</loc>
    <xhtml:link rel="alternate" hreflang="en"        href="https://rkteambuilder.com/en/dex/monsters/1"/>
    <xhtml:link rel="alternate" hreflang="zh"        href="https://rkteambuilder.com/zh/dex/monsters/1"/>
    <xhtml:link rel="alternate" hreflang="x-default" href="https://rkteambuilder.com/en/dex/monsters/1"/>
    <lastmod>2026-05-24</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://rkteambuilder.com/zh/dex/monsters/1</loc>
    <xhtml:link rel="alternate" hreflang="en"        href="https://rkteambuilder.com/en/dex/monsters/1"/>
    <xhtml:link rel="alternate" hreflang="zh"        href="https://rkteambuilder.com/zh/dex/monsters/1"/>
    <xhtml:link rel="alternate" hreflang="x-default" href="https://rkteambuilder.com/en/dex/monsters/1"/>
    <lastmod>2026-05-24</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>
```

Total URL count: ~2,062 (2 × current 1,030, plus the two `/announcements` entries — REVISED 2026-07-07). Well under the 50,000-URL per-sitemap limit; no sitemap index needed.

---

## G. Full URL Migration Table

| Current URL | New English URL | New Chinese URL | Legacy redirect | Notes |
|---|---|---|---|---|
| `/` | `/en/` | `/zh/` | 302 to `/en/` or `/zh/` based on Accept-Language | Root locale negotiation |
| `/build` | `/en/` (route dropped) | `/zh/` (route dropped) | 301 `/build` → `/en/`; route `/en/build` → 301 to `/en/`; `/zh/build` → 301 to `/zh/` | Consolidate duplicate of homepage |
| `/build/analyze/:slot` | `/en/build/analyze/:slot` | `/zh/build/analyze/:slot` | 301 to `/en/build/analyze/:slot` | noindex,nofollow — kept |
| `/dex` | `/en/dex` | `/zh/dex` | 301 to `/en/dex` | Indexable both langs |
| `/dex/monsters/:id` | `/en/dex/monsters/:id` | `/zh/dex/monsters/:id` | 301 to `/en/dex/monsters/:id` | Highest SEO value |
| `/dex/moves/:id` | `/en/dex/moves/:id` | `/zh/dex/moves/:id` | 301 to `/en/dex/moves/:id` | High SEO value |
| `/teams` | `/en/teams` | `/zh/teams` | 301 to `/en/teams` | noindex,follow |
| `/teams/:id` | `/en/teams/:id` | `/zh/teams/:id` | 301 to `/en/teams/:id` | noindex,follow |
| `/auth/login` | `/en/auth/login` | `/zh/auth/login` | 301 to `/en/auth/login` | noindex,nofollow |
| `/auth/register` | `/en/auth/register` | `/zh/auth/register` | 301 to `/en/auth/register` | noindex,nofollow |
| `/auth/forgot-password` | `/en/auth/forgot-password` | `/zh/auth/forgot-password` | 301 | noindex,nofollow |
| `/auth/reset-password` | `/en/auth/reset-password` | `/zh/auth/reset-password` | 301; email links must include locale | noindex,nofollow |
| `/auth/verify` | `/en/auth/verify` | `/zh/auth/verify` | 301; email links must include locale | noindex,nofollow |
| `/auth/confirm-email` | `/en/auth/confirm-email` | `/zh/auth/confirm-email` | 301; email links must include locale | noindex,nofollow |
| `/settings` | `/en/settings` | `/zh/settings` | 301 | noindex,nofollow |
| `/admin` | `/en/admin` | `/zh/admin` | 301 | noindex,nofollow |
| `/feedback` | `/en/feedback` | `/zh/feedback` | 301 | noindex,follow |
| `/import` | `/en/import` | `/zh/import` | 301 | noindex,follow — **share links are `/import?t=<payload>` ([sharePayload.ts:53](frontend/src/features/share/sharePayload.ts#L53)); the 301 MUST carry the query string or every previously shared team link breaks** (see K1). New share links should embed the current locale. |
| `/announcements` | `/en/announcements` | `/zh/announcements` | 301 | **REVISED 2026-07-07 (route added 2026-04):** indexable via useSeoMeta; add both variants to the sitemap generator (weekly, 0.5) |
| `/en`, `/zh` (bare, no slash) | `/en/` | `/zh/` | 301 to trailing-slash form | **REVISED 2026-07-07:** normalization so exactly ONE homepage URL form exists — matches canonical, sitemap, and hreflang (all use `/en/`, `/zh/`) |

**Preservation rules** (CloudFront Function must implement):
- Query string preserved across redirect (`?from=...&back=...`)
- Hash (`#section`) is browser-handled — not part of the HTTP request, no special handling needed
- Path params (`:id`, `:slot`) preserved verbatim

### Static / non-route paths (NOT to be redirected)
| Path | Handling |
|---|---|
| `/api/*` | Untouched, goes to EC2 |
| `/sitemap.xml`, `/robots.txt` | Untouched, served from S3 |
| `/favicon/*`, `/logo.png`, `/monster-images/*`, `/move-icons/*`, `/type-icons/*`, `/decorative-icons/*`, `/ad-images/*`, `/magic-items/*`, `/move-sub-icons/*`, `/payments/*`, `/google8ffd930116c9c497.html`, `/vite.svg` | Untouched (anything with a dot) |
| `/assets/*` (Vite bundle output) | Untouched (anything with a dot) |
| `/manifest.json` / `/favicon/site.webmanifest` | Untouched |

---

## H. File-by-File Change Plan

### H1. `frontend/src/router.tsx` — wrap all routes in `/:lang`

Current shape:
```tsx
{
  path: "/",
  element: <App />,
  children: [{ index: true, ... }, { path: "build", ... }, ...]
}
```

New shape:
```tsx
{
  path: "/:lang",
  element: <App />,                  // App stays; sees lang param via useParams
  children: [
    { index: true, element: <BuilderPage /> },
    { path: "build", element: <BuilderPage /> },         // kept as redirect target (see H8)
    { path: "build/analyze/:slot", element: <MonsterAnalysisPage /> },
    { path: "dex", element: <DexPage /> },
    { path: "dex/monsters/:id", element: <MonsterDetailPage /> },
    { path: "dex/moves/:id", element: <MoveDetailPage /> },
    { path: "teams", element: <TeamsListPage /> },
    { path: "teams/:id", element: <SavedTeamPage /> },
    { path: "auth/login", element: <LoginPage /> },
    // ...remaining unchanged...
  ]
},
// Wildcard catch — REVISED 2026-07-07: must be PREFERENCE-BASED, not hardcoded /en.
// In production the CloudFront Function 302s "/" before the SPA sees it, so this
// wildcard only fires in `vite dev` (root + unknown paths) and in the TapTap
// hash-router build, which boots at "#/" — a hardcoded /en would dump TapTap's
// ~all-Chinese audience into English UI.
{
  path: "*",
  element: <RedirectToPreferredLocale />
}

// components/RedirectToPreferredLocale.tsx (NEW):
function RedirectToPreferredLocale() {
  const stored = localStorage.getItem("lang");
  const lang = stored === "zh" || stored === "en"
    ? stored
    : navigator.language.startsWith("zh") ? "zh" : "en";
  return <Navigate to={`/${lang}/`} replace />;
}
```

**Keep the `createHashRouter` conditional** at the top of router.tsx untouched
(`VITE_HASH_ROUTER === "true"` → TapTap build). The `/:lang` route tree works
identically under both routers; only the fallback semantics above differ.

**Validation of `:lang` param** is done by `App.tsx` (see H2).

### H2. `frontend/src/App.tsx` — validate locale param

Add at the top of `App` (before any other hook):
```tsx
import { useParams, Navigate, useLocation } from "react-router-dom";

export default function App() {
  const { lang } = useParams<{ lang: string }>();
  const { pathname, search, hash } = useLocation();

  if (lang !== "en" && lang !== "zh") {
    // Strip the bad lang and fall back to /en + rest
    // e.g. /xx/dex → /en/dex
    const restOfPath = pathname.replace(/^\/[^/]+/, "") || "/";
    return <Navigate to={`/en${restOfPath}${search}${hash}`} replace />;
  }
  // ... existing scroll-to-top + outlet
}
```

Why here, not at the router level: React Router's element resolves before params validation; doing the check in the route element is the cleanest pattern.

### H3. `frontend/src/i18n.tsx` — URL becomes the source of truth (REVISED 2026-07-07)

> **The original version of this section moved `I18nProvider` inside the router
> and deleted `setLang`. Do NOT do that** — `AuthProvider` sits outside the
> router and calls `useI18n()`/`setLang(freshUser.preferred_language)` on
> session restore ([AuthProvider.tsx:58,91](frontend/src/features/auth/AuthProvider.tsx#L58));
> the old approach crashes the app at boot. `main.tsx` now needs **no changes**.

Keep `I18nProvider` exactly where it is in the tree. Rework its internals:

```tsx
// i18n.tsx
function detectInitialLang(): Lang {
  // Correct for browser-router (/zh/...), hash-router (#/zh/... — TapTap build),
  // and the pre-router first render. LocaleFromUrl corrects it from useParams
  // as soon as the router mounts.
  const probe = window.location.pathname + " " + window.location.hash;
  if (/[/#]\/?zh(\/|$)/.test(probe)) return "zh";
  if (/[/#]\/?en(\/|$)/.test(probe)) return "en";
  const stored = localStorage.getItem("lang");
  if (stored === "zh" || stored === "en") return stored;
  return navigator.language.startsWith("zh") ? "zh" : "en";
}

type Ctx = {
  lang: Lang;
  t: (key: string, vars?: Record<string, any>) => string;
  /** Navigate to the same page in `next`'s locale. No-ops if already there.
   *  Replaces setLang for ALL five former consumers (F5). */
  switchLang: (next: Lang) => void;
};

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(detectInitialLang);
  // Populated by <LocaleFromUrl> once the router mounts; the provider itself
  // is outside the router and cannot call useNavigate.
  const swapRef = useRef<((next: Lang) => void) | null>(null);

  useEffect(() => {
    document.documentElement.lang = lang;
    localStorage.setItem("lang", lang);  // preference memory for fallbacks
  }, [lang]);

  const value = useMemo<Ctx>(() => ({
    lang,
    t: (key, vars) => resolve(ui[lang], key, vars) || resolve(ui.en, key, vars),
    switchLang: (next) => {
      if (next === lang) return;
      if (swapRef.current) swapRef.current(next);   // normal path: navigate
      else setLangState(next);                       // pre-router fallback
    },
  }), [lang]);

  return (
    <I18nCtx.Provider value={value}>
      <I18nInternalCtx.Provider value={{ setLangState, swapRef }}>
        {children}
      </I18nInternalCtx.Provider>
    </I18nCtx.Provider>
  );
}

/**
 * <LocaleFromUrl /> — render INSIDE the /:lang route element (e.g. first child
 * of App). Syncs the URL's lang into the provider and registers the
 * navigation-based swap used by switchLang.
 */
export function LocaleFromUrl() {
  const { lang: urlLang } = useParams<{ lang?: string }>();
  const navigate = useNavigate();
  const { pathname, search, hash } = useLocation();
  const { setLangState, swapRef } = useContext(I18nInternalCtx)!;

  useEffect(() => {
    if (urlLang === "en" || urlLang === "zh") setLangState(urlLang);
  }, [urlLang, setLangState]);

  useEffect(() => {
    swapRef.current = (next) => {
      const swapped = pathname.replace(/^\/(en|zh)(?=\/|$)/, `/${next}`);
      navigate(swapped + search + hash);
    };
    return () => { swapRef.current = null; };
  }, [pathname, search, hash, navigate, swapRef]);

  return null;
}
```

Changes:
- `useI18n()` return type becomes `{ lang, t, switchLang }` — `setLang` is gone,
  but every former consumer has a drop-in replacement (see H4/H4b).
- **Re-mount concern (unchanged):** switching `/en/dex` → `/zh/dex` keeps the
  same `/:lang` route element — React Router re-renders with new params, no
  remount. AuthProvider, query cache, builder stores all preserved.

### H4. `frontend/src/components/Topbar.tsx` — make switcher navigate (REVISED 2026-07-07)

With H3's `switchLang` in the context this is now a one-line change. The button
handler (now at ~line 214, drifted from 187):
```tsx
// Before:
onClick={() => setLang(lang === "en" ? "zh" : "en")}
// After:
onClick={() => switchLang(lang === "en" ? "zh" : "en")}
```

### H4b. The other four `setLang` consumers (NEW 2026-07-07)

These postdate the original plan and MUST be migrated (a bare `setLang` removal
breaks cross-device language sync):

| Site | Today | After |
|---|---|---|
| [AuthProvider.tsx:91](frontend/src/features/auth/AuthProvider.tsx#L91) — session restore applies stored preference | `setLang(freshUser.preferred_language as Lang)` | `switchLang(freshUser.preferred_language as Lang)` — no-ops if already on that locale; otherwise navigates to the preferred-locale URL |
| [LoginPage.tsx:48](frontend/src/features/auth/LoginPage.tsx#L48) — apply preference after login | `setLang(data.user.preferred_language …)` | `switchLang(...)` — note LoginPage also calls `navigate("/build")` right after; sequence so the final URL is `localized("/")` in the PREFERRED locale (compute target once, single navigate) |
| [RegisterPage.tsx:69](frontend/src/features/auth/RegisterPage.tsx#L69) — same after registration | `setLang(...)` | same as LoginPage |
| [SettingsPage.tsx:90](frontend/src/features/auth/SettingsPage.tsx#L90) — user changes UI language in settings | `setLang(newLang)` | `switchLang(newLang)` (stays on `/⟨next⟩/settings`) |

Product semantics preserved: logging in with `preferred_language=zh` while
browsing an `/en/...` URL moves you to the `/zh/...` equivalent — the same
observable behavior as today, now expressed in the URL.

### H5. Create `frontend/src/lib/locale.ts` — centralized URL helpers

```ts
import { useI18n } from "@/i18n";

/**
 * Returns a function that prefixes a path with the active locale.
 * Examples (lang="zh"):
 *   localized("/")              → "/zh/"
 *   localized("/dex")           → "/zh/dex"
 *   localized("/dex/monsters/1") → "/zh/dex/monsters/1"
 *   localized("https://...")    → passthrough
 *   localized("/en/dex")        → "/en/dex" (already prefixed; idempotent)
 */
export function useLocalizedPath() {
  const { lang } = useI18n();
  return (path: string) => {
    if (/^https?:|^mailto:|^tel:/.test(path)) return path;
    if (/^\/(en|zh)(?:\/|$)/.test(path)) return path;
    if (path === "/" || path === "") return `/${lang}`;
    return `/${lang}${path.startsWith("/") ? "" : "/"}${path}`;
  };
}

/** Non-hook variant for places that already have lang. */
export function localizedPath(lang: "en" | "zh", path: string) {
  if (/^https?:|^mailto:|^tel:/.test(path)) return path;
  if (/^\/(en|zh)(?:\/|$)/.test(path)) return path;
  if (path === "/" || path === "") return `/${lang}`;
  return `/${lang}${path.startsWith("/") ? "" : "/"}${path}`;
}
```

### H6. Update every internal-link site

Per the Explore agent inventory (~50 sites across ~30 files). Pattern:

**Before:**
```tsx
<Link to="/dex">Dex</Link>
navigate("/auth/login");
<Link to={`/dex/monsters/${m.id}?back=${back}`}>
```

**After:**
```tsx
const localized = useLocalizedPath();
<Link to={localized("/dex")}>Dex</Link>
navigate(localized("/auth/login"));
<Link to={localized(`/dex/monsters/${m.id}`) + `?back=${back}`}>
```

(For paths with query strings, apply localized to the *path part only*, then append the query — keeps the helper simple.)

**Files needing changes** (counts from Explore agent):
- `components/Sidebar.tsx` — 4 links: `/build`, `/dex`, `/teams`, `/feedback`
- `components/BottomNav.tsx` — 4 data-driven links (update the data array)
- `components/Topbar.tsx` — 2 links: `/build`, `/admin`
- `components/Footer.tsx` — 1 link: `/feedback`
- `components/UserMenu.tsx` — 5 navigate targets
- `components/SaveTeamModal.tsx` — 2 navigate targets
- `components/AnalysisResults.tsx` — 1 link template literal
- `components/MatchupPanel.tsx` — 1 link via variable
- `features/auth/LoginPage.tsx` — 2 links + 2 navigates
- `features/auth/RegisterPage.tsx` — 1 link + 2 navigates
- `features/auth/ResetPasswordPage.tsx` — 2 links + 1 navigate
- `features/auth/VerifyEmailPage.tsx` — 3 links + 1 navigate
- `features/auth/ConfirmEmailChangePage.tsx` — 2 links
- `features/auth/SettingsPage.tsx` — 3 navigates
- `features/builder/BuilderPage.tsx` — 2 navigates
- `features/builder/MonsterInspector.tsx` — 1 navigate
- `features/builder/CustomDefenderInspector.tsx` — 1 link template literal
- `features/builder/MonsterAnalysisPage.tsx` — present in inventory
- `features/dex/DexPage.tsx` — 2 link template literals
- `features/dex/MonsterDetailPage.tsx` — multiple link/navigate template literals (back URLs)
- `features/dex/MoveDetailPage.tsx` — 2 link template literals
- `features/dex/EvolutionTree.tsx` — 1 link template literal
- `features/teams/TeamsListPage.tsx` — 2 link template literals
- `features/teams/SavedTeamPage.tsx` — 1 link
- `features/share/ImportPage.tsx` — 1 link + redirects
- `features/share/FeaturedTeamView.tsx` — 1 link template literal
- `features/admin/AdminPage.tsx` — `<Navigate to="/" />` (38)
- `features/admin/FeaturedTeamsTab.tsx` — 1 navigate
- `features/feedback/FeedbackPage.tsx` (likely; flagged in inventory)
- Plus the `back` URL parameters passed across pages need to be re-derived from `location.pathname` (which already has the prefix) — most are dynamic and will Just Work as long as they were built from the current pathname, not hardcoded.

**Audit technique:**
After updating, run this grep to confirm no hardcoded internal paths remain in JSX:
```bash
rg --type tsx --type ts 'to="\/(?!en\/|zh\/)' frontend/src/
rg --type tsx --type ts "navigate\(['\"]\\/(?!en\\/|zh\\/)" frontend/src/
```
(Both should return zero hits after the refactor, except in the locale helper file itself.)

**REVISED 2026-07-07 — the two greps above have a blind spot.** Also audit
pathname *comparisons*, which neither pattern catches:
```bash
rg "location\.pathname" frontend/src/
```
Known site requiring manual rework:
[BuilderPage.tsx:528-529](frontend/src/features/builder/BuilderPage.tsx#L528)
compares `window.location.pathname !== "/build"` to decide whether to navigate
back to the builder after an analysis completes. With `/build` dropped (F1),
rework it against the localized home path (or `useLocation` + the locale
helper). 2026-07-07 inventory check: ~55 hardcoded link/navigate sites across
25 files (31 `to="/"`, 12 `` to={`/ ``, 11 `navigate(`, 1 `<Navigate>` in
AdminPage:38) — the plan's ~50/~30 estimate remains accurate.

### H7. `frontend/src/hooks/useSeoMeta.ts` — emit hreflang + locale-aware canonical

Rewrite to:
```ts
import { useEffect } from "react";
import { useLocation, useParams } from "react-router-dom";

const BASE_URL = "https://rkteambuilder.com";

interface SeoMeta {
  title: string;
  description: string;
  /** Override the canonical PATH (without locale prefix). E.g. "/" for /build → canonical /en/. */
  canonicalPath?: string;
  noindex?: boolean;
  nofollow?: boolean;
}

function setAttr(selector: string, attr: string, value: string) {
  const el = document.querySelector(selector);
  if (el) el.setAttribute(attr, value);
}

/**
 * Ensure a single <link rel="alternate" hreflang="X"> tag exists with the given href.
 * Removes any existing tag with the same hreflang before adding the new one.
 */
function setHreflang(hreflang: string, href: string) {
  document.querySelectorAll(`link[rel="alternate"][hreflang="${hreflang}"]`).forEach(el => el.remove());
  const link = document.createElement("link");
  link.setAttribute("rel", "alternate");
  link.setAttribute("hreflang", hreflang);
  link.setAttribute("href", href);
  document.head.appendChild(link);
}

export function useSeoMeta({ title, description, canonicalPath, noindex, nofollow }: SeoMeta) {
  const { pathname } = useLocation();
  const { lang: urlLang } = useParams<{ lang?: string }>();
  const lang: "en" | "zh" = (urlLang === "zh" || urlLang === "en") ? urlLang : "en";

  // Strip the leading /lang segment to get the path-without-locale.
  // canonicalPath (if provided) overrides this — but should also be locale-neutral.
  const pathNoLang = pathname.replace(/^\/(en|zh)(?=\/|$)/, "") || "/";
  const cp = canonicalPath ?? pathNoLang;
  // REVISED 2026-07-07 — TRAILING-SLASH NORMALIZATION: the homepage canonical is
  // "/en/" WITH the slash (the original `cp === "/" ? "" : cp` emitted "/en",
  // contradicting the sitemap/hreflang/redirects which all use "/en/" — Google
  // treats those as different URLs). Homepage: trailing slash. Deeper paths: none.
  // The CloudFront Function 301s bare "/en" → "/en/" to close the loop (K1 §3).
  const selfPath = `/${lang}${cp === "/" ? "/" : cp}`;
  const enPath = `/en${cp === "/" ? "/" : cp}`;
  const zhPath = `/zh${cp === "/" ? "/" : cp}`;

  useEffect(() => {
    document.title = title;
    const selfUrl = `${BASE_URL}${selfPath}`;

    setAttr('meta[name="description"]', "content", description);
    setAttr('meta[property="og:title"]', "content", title);
    setAttr('meta[property="og:description"]', "content", description);
    setAttr('meta[property="og:url"]', "content", selfUrl);
    setAttr('meta[property="og:locale"]', "content", lang === "zh" ? "zh_CN" : "en_US");
    setAttr('meta[property="og:locale:alternate"]', "content", lang === "zh" ? "en_US" : "zh_CN");
    setAttr('meta[name="twitter:title"]', "content", title);
    setAttr('meta[name="twitter:description"]', "content", description);
    setAttr('link[rel="canonical"]', "href", selfUrl);

    setHreflang("en", `${BASE_URL}${enPath}`);
    setHreflang("zh", `${BASE_URL}${zhPath}`);
    setHreflang("x-default", `${BASE_URL}${enPath}`);

    const indexPart = noindex ? "noindex" : "index";
    const followPart = nofollow ? "nofollow" : "follow";
    setAttr('meta[name="robots"]', "content", `${indexPart}, ${followPart}`);
  }, [title, description, selfPath, enPath, zhPath, lang, noindex, nofollow]);
}
```

**Backwards-compat note for callers:** existing `canonicalPath: "/"` (in BuilderPage), `canonicalPath: "/dex"` (DexPage), `canonicalPath: "/teams"` (TeamsListPage), and `canonicalPath: ` /dex/monsters/${id}`` (MonsterDetailPage) — all of these are **locale-neutral** and continue to work as-is. The hook prepends the locale internally.

### H8. `frontend/src/features/builder/BuilderPage.tsx` — adjust canonical for `/<lang>/build`

Today: `canonicalPath: "/"` consolidates `/build` → `/`.

After: `canonicalPath: "/"` will yield self-canonical of `/en/` (for `/en/`) or `/en/` (for `/en/build`). The hook now treats `canonicalPath` as the locale-neutral path. So this just works.

However, **strongly recommend dropping the `/<lang>/build` route** from the router and adding a CloudFront 301 from `/<lang>/build` → `/<lang>/`. Reasons:
- `/build` is a legacy code path. The "homepage" is `/` (now `/<lang>/`).
- Two URLs with the same content is friction in the long term. Cleaner to consolidate.
- Removing the route deletes one router entry and one indexable surface.

If kept, BuilderPage's `canonicalPath: "/"` continues to send Google the right signal.

### H9. `frontend/index.html` — update static defaults + inline script

**Hreflang block (lines 17-19):** keep as defaults pointing to homepage — the per-page `useSeoMeta` overrides them with proper locale-specific URLs:
```html
<link rel="alternate" hreflang="x-default" href="https://rkteambuilder.com/en/" />
<link rel="alternate" hreflang="en"        href="https://rkteambuilder.com/en/" />
<link rel="alternate" hreflang="zh"        href="https://rkteambuilder.com/zh/" />
```

**Canonical (line 13):** update to `https://rkteambuilder.com/en/` (default canonical; per-page hook overrides).

**Inline script (lines ~110-133):** detect language from the URL — but **REVISED
2026-07-07: pathname alone is NOT enough.** The TapTap build uses a hash router
(`#/zh/...` — the locale never appears in `pathname`), and the legacy pre-redirect
state has no locale at all. A pathname-only check would show English loading
text/title to TapTap's ~all-Chinese audience — a regression vs. today's
localStorage detection. Use the same fallback chain as `detectInitialLang()` (H3):

```html
<script>
  (function() {
    // Locale detection: URL path (/zh/...) → URL hash (#/zh/..., TapTap's
    // hash-router build) → saved preference → browser language.
    var probe = window.location.pathname + ' ' + window.location.hash;
    var lang;
    if (/[\/#]\/?zh(\/|$)/.test(probe)) lang = 'zh';
    else if (/[\/#]\/?en(\/|$)/.test(probe)) lang = 'en';
    else {
      var stored = null;
      try { stored = localStorage.getItem('lang'); } catch (e) {}
      lang = (stored === 'zh' || stored === 'en') ? stored
           : (navigator.language && navigator.language.indexOf('zh') === 0 ? 'zh' : 'en');
    }

    var translations = {
      en: { title: 'Loading RK Team Builder', subtitle: 'Initializing application...' },
      zh: { title: '正在加载洛手配队器', subtitle: '初始化应用...' }
    };
    var text = translations[lang];
    document.getElementById('loading-text').textContent = text.title;
    document.getElementById('loading-subtext').textContent = text.subtitle;
    document.title = lang === 'zh'
      ? '洛手配队器 | 洛克王国：世界 PvP 配队工具'
      : 'RK Team Builder | Roco Kingdom: World PvP Team Builder';
  })();
</script>
```

This means: if a Googlebot crawls `https://rkteambuilder.com/zh/dex`, the *very first* HTML it parses has the Chinese title, before any React execution — the single most important signal for weak-JS crawlers (Baidu). And TapTap keeps its Chinese loading screen.

### H10. `backend/scripts/maintenance/generate_sitemap.py` — emit locale variants with hreflang

Replace the body of `main()`:
```python
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

def main():
    engine = create_engine(DATABASE_URL)
    today = date.today().isoformat()
    with Session(engine) as session:
        monster_ids = [mid for (mid,) in session.query(Monster.id).order_by(Monster.id).all()]
        move_ids = [mid for (mid,) in session.query(Move.id).order_by(Move.id).all()]

    LANGS = ["en", "zh"]
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>\n',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
    ]

    def alts(path: str) -> list[tuple[str, str]]:
        return [
            ("en", f"{BASE_URL}/en{path}"),
            ("zh", f"{BASE_URL}/zh{path}"),
            ("x-default", f"{BASE_URL}/en{path}"),
        ]

    for lang in LANGS:
        parts.append(url_entry(f"{BASE_URL}/{lang}/", today, "weekly", "1.0", alts("/")))
        parts.append(url_entry(f"{BASE_URL}/{lang}/dex", today, "weekly", "0.9", alts("/dex")))
        # REVISED 2026-07-07: /announcements (added 2026-04) is indexable and
        # was previously absent from the sitemap entirely — include it.
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
    total = len(LANGS) * (2 + len(monster_ids) + len(move_ids))
    print(f"Wrote {total} URLs to {OUTPUT_PATH}")
```

Note the leading slash inside alts — paths like `/dex` produce `BASE_URL + /en + /dex` = `…/en/dex`. The `/` case becomes `…/en/` which is correct **and now matches H7's canonical exactly** (trailing-slash normalization). Implementation notes (2026-07-07): keep/add `from xml.sax.saxutils import escape` (the snippet calls `escape()`); new total = 2 × (3 static + monsters + moves) ≈ **2,062** given today's 1,030-URL sitemap.

### H11. `backend/email_service.py` — include locale in email links (REVISED 2026-07-07)

**This is now a three-line change.** Verified against the current code: all three
email functions ALREADY accept `language: str = "en"` and every call site already
passes the user's language — it localizes the email *body* today
([email_service.py:99,179,260](backend/email_service.py#L99)). `User.preferred_language`
exists (`String(5)`, `"en"`/`"zh"`, set at registration, updatable via
`/auth/update-language-preference`) — former P1 is RESOLVED. Just embed the
already-available `language` into the three URLs:

```python
# line ~111
verify_url = f"{FRONTEND_URL}/{language}/auth/verify?token={token}"
# line ~191
reset_url = f"{FRONTEND_URL}/{language}/auth/reset-password?token={token}"
# line ~272
verify_url = f"{FRONTEND_URL}/{language}/auth/confirm-email?token={token}"
```

No signature changes, no call-site threading, no model work. (Belt-and-braces:
guard `language if language in ("en", "zh") else "en"` when interpolating into
the URL, since the value originates from a user-settable column.)

### H12. `backend/scripts/maintenance/regenerate_static_for_locale_refactor.py` — one-shot regeneration

Not strictly required, but useful: a tiny wrapper script that regenerates the sitemap *and* prints the count, to be run once after the refactor lands. Already covered by H10 above; no new script needed.

### H13. `robots.txt` — no change

Already correct ([frontend/public/robots.txt](frontend/public/robots.txt)):
```
User-agent: *
Allow: /
Sitemap: https://rkteambuilder.com/sitemap.xml
```
The path-prefix change doesn't affect robots.txt.

### H14. `.github/workflows/deploy.yml` — no change

Build → S3 sync → `/*` invalidation. The invalidation already covers everything. No workflow changes needed.

### H15. `docker-compose.prod.yml` — no change

Cookies are `path="/"`; locale prefixes don't affect cookie scope. `FRONTEND_URL` is still `https://rkteambuilder.com` — the path component is added by email_service.py per H11.

### H16. CloudFront Function `rktb-spa-routing` — extend for redirects (Section K covers this in detail)

---

## I. Feature-by-Feature Impact Analysis

| Feature | URLs used | Generates links? | Reads `lang`? | Risk after refactor | Required tests |
|---|---|---|---|---|---|
| **Dex listing** (DexPage) | `/<lang>/dex` | Yes — monster cards link to detail pages with `back=` query | Yes | All monster/move card links must use `useLocalizedPath`. `back=` URL inside query must already be locale-prefixed (it's derived from `location.pathname`, so OK). | Browse dex EN + ZH, click a monster card, click back. |
| **Monster detail** (MonsterDetailPage) | `/<lang>/dex/monsters/:id` | Yes — back link, previous/next monster nav, move links | Yes | All template-literal hrefs need `localized(...)`. Particularly: the `back` query param round-trip. | Open detail page from dex, click next, click move, click back. |
| **Move detail** (MoveDetailPage) | `/<lang>/dex/moves/:id` | Yes — back link, "monsters that learn" links | Yes | Same as above. | Open move, click monster from learners, click back. |
| **Team builder** (BuilderPage) | `/<lang>/` | Yes — magic item picker, monster slot navigation | Yes | The redirect-after-action navigates: `navigate(localized("/build/analyze/" + slot))`. Verify session continuity across switch. | Build a team in EN, switch to ZH (URL change), continue building. |
| **Per-monster analysis** (MonsterAnalysisPage) | `/<lang>/build/analyze/:slot` | Yes — back to builder, view monster in dex | Yes | `:slot` param preserved across `:lang` change. State store keyed on slot. Verify analysis state survives language switch (since I18nProvider doesn't remount). | Run analysis in EN, switch to ZH mid-page. |
| **Battle simulator / type matchup / damage calc** | rendered inside MonsterAnalysisPage | n/a | Yes | Pure UI components, no internal navigation. Language switch is a re-render only. | Visual regression check. |
| **Saved teams list** (TeamsListPage) | `/<lang>/teams` | Yes — team cards link to `/<lang>/teams/:id` | Yes | Template literal `to={`/teams/${team.id}`}` needs `localized(...)`. Auth-gated. | Login, save team, navigate to list, click team. |
| **Saved team detail** (SavedTeamPage) | `/<lang>/teams/:id` | Yes — back to teams, monster links in team | Yes | All hardcoded `to` strings need `localized(...)`. | Open saved team, click each monster. |
| **Login / Register / Forgot / Reset / Verify / Confirm-email** | `/<lang>/auth/...` | Yes — cross-links between auth pages | Yes | All `<Link to="...">` need update. After successful login, `navigate("/build")` becomes `navigate(localized("/"))`. Cross-form links (login → forgot, register → login) need update. | Each form, success and failure paths. |
| **Settings** | `/<lang>/settings` | Yes — logout redirect | Yes | `navigate("/auth/login")` after delete-account, etc. — update sites. | Change password, change email, delete account. |
| **Admin dashboard** | `/<lang>/admin` | Has `<Navigate to="/" />` for non-admins | Yes | Update to `<Navigate to="/<lang>/" />` — but need to know lang at component mount. Cleanest: a `<NavigateLocalized to="/" />` wrapper. | Try to access as non-admin, confirm redirect. |
| **Feedback** | `/<lang>/feedback` | None significant | Yes | Trivial. | Submit feedback in each language. |
| **Import (share)** | `/<lang>/import` | Yes — to /<lang>/auth/register if not authed | Yes | Import payload URLs (if any are produced as full URLs anywhere) must contain locale. Check if `ImportPage` generates a shareable link. UNVERIFIED. | Generate share link, open in incognito, verify it opens in the correct language. |
| **Featured teams** (FeaturedTeamView, VsFeaturedTeamsTab) | matchup pages | Yes — monster links | Yes | Template literals. | Open featured team, click monster. |
| **AI team analysis** | API call, no URL impact | Generates description text only | Yes (sent to backend as `language` param) | No URL change. | Run analysis in each language, confirm prompt/output language. |
| **Email verification flow** | Backend → user's inbox → `/<lang>/auth/verify?token=...` | Backend constructs URL | Yes (from user.preferred_language) | H11 implementation. Test with both EN-registered and ZH-registered users. | Register in EN, click email link → land on `/en/auth/verify`. Same in ZH. |
| **Password reset flow** | Backend → email → `/<lang>/auth/reset-password?token=...` | Backend constructs URL | Yes | H11. | Request reset for ZH user, click email, land on `/zh/...`. |
| **Email change confirmation** | Backend → email → `/<lang>/auth/confirm-email?token=...` | Backend constructs URL | Yes | H11. | Same pattern. |
| **Language switcher in Topbar** | swaps current path locale | No links | Yes | H4. Behavior change: full navigation instead of state update. Lose ~1ms but URL changes (which is the whole point). | On every type of page (dex, detail, builder, auth, modal-open) switch language. |
| **Auth cookies** | n/a | n/a | n/a | Cookies `path="/"` → unaffected by locale prefix. Session persists across `/en/` ↔ `/zh/` navigation. Verified per [docker-compose.prod.yml](docker-compose.prod.yml) + Explore agent. | Login in EN, switch to ZH, confirm still logged in. |
| **API client** (`frontend/src/lib/api.ts`) | `/api/*` | n/a | n/a | API paths never get locale prefix (verified — only frontend SPA paths do). | API calls work in both locales. |
| **Sitemap** | `/sitemap.xml` | Yes (regenerated) | n/a | URL count doubles. Submit fresh to Search Console. | Validate XML, check Google's sitemap report after upload. |
| **Analytics (Umami)** | tracks `window.location.pathname` | n/a | n/a | URL changes will *split* analytics: `/en/dex` and `/zh/dex` become separate rows. Expected. Consider whether to add a custom event with `lang` to make per-page-per-lang reporting easy. | Visit each page in each language; confirm Umami sees them as distinct paths. |

---

## J. SEO Artifacts Plan

### J1. Canonical
- Every page emits a self-canonical: `https://rkteambuilder.com/<lang>/<rest>`.
- Implemented by H7 (`useSeoMeta` rewrite).
- For pages that share a canonical (e.g., `/<lang>/build` → `/<lang>/`), pass `canonicalPath: "/"` (locale-neutral) and the hook resolves it.

### J2. Hreflang
- Every indexable page emits exactly 3 alternate links:
  - `hreflang="en"` → its English equivalent
  - `hreflang="zh"` → its Chinese equivalent
  - `hreflang="x-default"` → its English equivalent
- Reciprocal by construction (each page lists both itself and its sibling).
- Implemented by H7 (`useSeoMeta` rewrite, `setHreflang` helper).
- Static defaults in `index.html` (H9) serve as a baseline for pages without `useSeoMeta`.

### J3. Sitemap
- Switch to xhtml:link annotation format (H10).
- Each pair of URLs (en + zh) appears as two `<url>` entries, each listing all three alternates.
- ~2,062 URLs total; ~1MB file size (well under 50MB limit).
- Regenerate after any monster/move add or removal: `python3 -m backend.scripts.maintenance.generate_sitemap`.

### J4. Robots
- `robots.txt` unchanged.
- Per-page `<meta name="robots">` retains current semantics (set by `useSeoMeta` or `<NoIndex>`).
- No new disallow rules — both `/en/` and `/zh/` are crawlable.

### J5. OG / Twitter / structured data
- OG URL: matches canonical (locale-aware).
- OG locale: `en_US` for `/en/...`, `zh_CN` for `/zh/...`.
- OG locale:alternate: the other one.
- Twitter card type: unchanged (`summary`); separate small win — could later upgrade to `summary_large_image`. Out of scope of this plan.
- Structured data (JSON-LD): not currently present. Out of scope of this plan but pairs well with the locale URLs once added (each locale page would declare its own `inLanguage`).

### J6. Search Console
- Submit the new sitemap.xml after deploy.
- Use Search Console's International Targeting > Hreflang tab to verify the tags are picked up (takes ~1-2 days after sitemap regeneration).
- Expect crawl + index of Chinese pages over 2-8 weeks.

---

## K. Redirect and Hosting Plan

### K1. New CloudFront Function: `rktb-locale-routing`

Replace (or update) `rktb-spa-routing`. Recommend creating a new function and atomically swapping the association — preserves the rollback path.

**REVISED 2026-07-07** — final version. Changes vs. the original sketch:
query-string serialization is now used in BOTH redirect branches (it is
**load-bearing**: previously shared team links are `/import?t=<payload>` and the
payload lives entirely in the query string — see [sharePayload.ts:53](frontend/src/features/share/sharePayload.ts#L53));
and bare `/en`/`/zh` now 301 to the trailing-slash form so exactly one homepage
URL exists (matching canonical/sitemap/hreflang — see H7).

```javascript
function handler(event) {
    var request = event.request;
    var uri = request.uri;
    var headers = request.headers;

    // Serialize the (possibly multi-value) query string for redirect Locations.
    // CloudFront does NOT auto-append the query string when a function returns
    // a response object (it DOES preserve it on request rewrites). Values in
    // event.request.querystring arrive still percent-encoded, so plain
    // concatenation is safe.
    function buildQS(qs) {
        var out = [];
        for (var k in qs) {
            var v = qs[k];
            if (v.multiValue) {
                for (var i = 0; i < v.multiValue.length; i++) {
                    out.push(k + '=' + v.multiValue[i].value);
                }
            } else if (v.value !== undefined) {
                out.push(k + '=' + v.value);
            }
        }
        return out.length ? '?' + out.join('&') : '';
    }
    var qs = buildQS(request.querystring);

    // 1. API requests untouched (defense — they go to a different behavior anyway)
    if (uri.startsWith('/api/')) return request;

    // 2. Static files (anything with a dot in the URI) untouched
    if (uri.includes('.')) return request;

    // 3. Bare locale roots → 301 to the trailing-slash canonical form.
    //    /en → /en/, /zh → /zh/ (canonical, sitemap, and hreflang all use /en/).
    if (uri === '/en' || uri === '/zh') {
        return {
            statusCode: 301,
            statusDescription: 'Moved Permanently',
            headers: {
                'location': { value: uri + '/' + qs },
                'cache-control': { value: 'public, max-age=3600' }
            }
        };
    }

    // 4. Locale-prefixed → SPA rewrite to /index.html
    if (uri.startsWith('/en/') || uri.startsWith('/zh/')) {
        request.uri = '/index.html';
        return request;
    }

    // 5. Root: 302 redirect to /en/ or /zh/ based on Accept-Language
    //    (302 not 301: the target varies per user; keep query string, e.g. /?ref=…)
    if (uri === '/') {
        var lang = 'en';
        var al = headers['accept-language'];
        if (al && al.value && al.value.toLowerCase().indexOf('zh') === 0) {
            lang = 'zh';
        }
        return {
            statusCode: 302,
            statusDescription: 'Found',
            headers: {
                'location': { value: '/' + lang + '/' + qs },
                'vary': { value: 'Accept-Language' },
                'cache-control': { value: 'no-store' }
            }
        };
    }

    // 6. Legacy unprefixed routes → 301 to /en/<same>, query string preserved.
    //    Covers /dex, /dex/monsters/1, /build, /teams, /auth/*, /admin,
    //    /settings, /feedback, /import?t=… (share links!), /announcements.
    return {
        statusCode: 301,
        statusDescription: 'Moved Permanently',
        headers: {
            'location': { value: '/en' + uri + qs },
            'cache-control': { value: 'public, max-age=3600' }
        }
    };
}
```

**Querystring verification (P2 — still MANDATORY before production):** the
`buildQS` shape matches the [CloudFront Functions event structure docs](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cloudfront-functions-event-structure.html)
(JS 2.0: `querystring` object, `value`/`multiValue`, values percent-encoded), but
this MUST be validated in the CloudFront Functions console **test tab** (or a
sandbox function) before the association swap, using a real share-style URL:
`/import?t=<long-base64-payload>` and a multi-param URL
`/dex/monsters/1?from=builder&back=%2Fbuild`. Confirm the Location header
preserves the payload byte-for-byte.

### K2. CloudFront Function deployment steps

Adopt the exact pattern from [spa-routing-seo-fix.md Sections 8-11](spa-routing-seo-fix.md#L376):
1. Read-only preflight (confirm AWS account, distribution ID, current ETag, current function associations).
2. Write function code to `/tmp/rktb-locale-routing.js`.
3. `aws cloudfront create-function ...`.
4. `aws cloudfront publish-function ...`.
5. Fetch current distribution config + ETag in one atomic step.
6. Patch: replace the existing `rktb-spa-routing` association in `DefaultCacheBehavior.FunctionAssociations` with `rktb-locale-routing` (keep `Quantity: 1`).
7. Diff against backup — exactly one field changed.
8. `aws cloudfront update-distribution --if-match <ETag>`.
9. `aws cloudfront wait distribution-deployed`.
10. `aws cloudfront create-invalidation --paths "/*"`.

### K3. S3 hosting — no change required
- S3 website hosting (with `index.html` as error document) still handles all SPA paths — the CloudFront Function rewrites everything to `/index.html` before S3 sees it.
- Bucket policy referer check ([deployment-complete.md:732](deployment-complete.md#L732)) unaffected.

### K4. Nginx (on EC2) — no change
- Nginx serves only `/api/*` requests. Locale routing happens entirely in CloudFront, never reaches EC2.

### K5. Prerendering — explicitly out of scope
- Locale URLs make the site *crawlable* — that's necessary but not sufficient.
- The deeper issue (SPA hands Googlebot empty HTML) is unsolved by this plan. Mitigation:
  - The inline script in H9 sets the correct title/loading text before React boots, so even bots that don't execute JS see the right title.
  - For Bing/Baidu/Yandex (weaker JS support than Google), this is still a significant gap.
- **Recommendation:** treat prerendering as a *separate* follow-up plan after this refactor is stable. Tools to evaluate then: `vite-plugin-prerender`, Cloudflare Worker bot-UA detection + Puppeteer, or migration to Next.js / Astro. Not in scope here.

---

## L. Testing Plan

### L1. Local pre-deploy tests

```bash
# Frontend type-check + lint
cd frontend
npm ci
npm run typecheck       # MUST pass
npm run lint            # MUST pass
npm run build           # MUST succeed
```

If `npm test` exists, run it. (UNVERIFIED — check package.json.)

```bash
# Backend tests
cd backend
source ~/.venvs/rktb310/bin/activate
pytest -v               # MUST pass; specifically test_auth.py because of email URL changes
```

### L2. Local manual browser tests against `npm run dev`

For each route in the migration table (Section G), verify in a real browser:

```bash
cd frontend && npm run dev   # http://localhost:5173
```

Then in Chrome (clear localStorage first):
- Visit `http://localhost:5173/` — should 302 → `/en/` or `/zh/` based on browser language. **UNVERIFIED** the dev server's behavior; the CloudFront 302 only runs in prod. For dev, the root route should be handled by a React-level `<Navigate>` based on `navigator.language` — add this fallback to the router.
- Visit `http://localhost:5173/en/dex` — English Dex renders. Click monster.
- URL after click: `/en/dex/monsters/<id>?back=...`. View source → confirm hreflang en/zh/x-default present and pointing correctly.
- Click language switcher. URL changes to `/zh/dex/monsters/<id>?back=...`. Same content in Chinese.
- Browser back button works.

### L3. SEO meta verification (REVISED 2026-07-07 — script must be written from scratch)

**`verify-robots.mjs` does NOT exist in the repo** (checked 2026-07-07 — it was a
one-off from the spa-routing work that was never committed), and Playwright is
not a dependency (`npm test` = vitest). Write a new `frontend/scripts/verify-seo.mjs`
and add `playwright` as a devDependency (meta tags are set by client-side JS, so
a real browser is required — plain fetch won't see them). Checks per page:
canonical, hreflang ×3, robots, og:url, `<html lang>`. Example table:

```js
const tests = [
  // [path, expectedCanonical, expectedHreflangEn, expectedHreflangZh, expectedHreflangXDefault, expectedRobots]
  ["/en/",                  "https://rkteambuilder.com/en/",                  "https://rkteambuilder.com/en/",                  "https://rkteambuilder.com/zh/",                  "https://rkteambuilder.com/en/",                  "index, follow"],
  ["/zh/",                  "https://rkteambuilder.com/zh/",                  "https://rkteambuilder.com/en/",                  "https://rkteambuilder.com/zh/",                  "https://rkteambuilder.com/en/",                  "index, follow"],
  ["/en/dex",               "https://rkteambuilder.com/en/dex",               "https://rkteambuilder.com/en/dex",               "https://rkteambuilder.com/zh/dex",               "https://rkteambuilder.com/en/dex",               "index, follow"],
  ["/zh/dex",               "https://rkteambuilder.com/zh/dex",               "https://rkteambuilder.com/en/dex",               "https://rkteambuilder.com/zh/dex",               "https://rkteambuilder.com/en/dex",               "index, follow"],
  ["/en/dex/monsters/1",    "https://rkteambuilder.com/en/dex/monsters/1",    "https://rkteambuilder.com/en/dex/monsters/1",    "https://rkteambuilder.com/zh/dex/monsters/1",    "https://rkteambuilder.com/en/dex/monsters/1",    "index, follow"],
  ["/zh/dex/monsters/1",    "https://rkteambuilder.com/zh/dex/monsters/1",    "https://rkteambuilder.com/en/dex/monsters/1",    "https://rkteambuilder.com/zh/dex/monsters/1",    "https://rkteambuilder.com/en/dex/monsters/1",    "index, follow"],
  ["/en/dex/moves/1",       /* analogous */ ],
  ["/zh/dex/moves/1",       /* analogous */ ],
  ["/en/teams",             "https://rkteambuilder.com/en/teams",             /* ... */, /* ... */, /* ... */,  "noindex, follow"],
  ["/zh/teams",             "https://rkteambuilder.com/zh/teams",             /* ... */, /* ... */, /* ... */,  "noindex, follow"],
  ["/en/auth/login",        "https://rkteambuilder.com/en/auth/login",        /* ... */, /* ... */, /* ... */,  "noindex, nofollow"],
  ["/zh/auth/login",        "https://rkteambuilder.com/zh/auth/login",        /* ... */, /* ... */, /* ... */,  "noindex, nofollow"],
  // ... continue for every entry in the migration table
];
```

Run against `http://localhost:5173` after Phase 1 (frontend deploy), then again against `https://rkteambuilder.com` after Phase 2 (CloudFront Function deploy).

### L4. Production smoke tests (after each deploy phase)

```bash
# All locale routes return 200
for path in /en/ /zh/ /en/dex /zh/dex /en/dex/monsters/1 /zh/dex/monsters/1 \
            /en/dex/moves/1 /zh/dex/moves/1 /en/teams /zh/teams \
            /en/auth/login /zh/auth/login /en/admin /zh/admin /en/feedback /zh/feedback; do
  status=$(curl -so /dev/null -w "%{http_code}" "https://rkteambuilder.com$path")
  echo "$path → $status"
done
# All must be 200

# Legacy routes return 301 to /en/<same>
for path in / /dex /dex/monsters/1 /dex/moves/1 /build /teams \
            /auth/login /auth/register /feedback /import; do
  resp=$(curl -so /dev/null -D - -w "%{http_code}" "https://rkteambuilder.com$path")
  echo "$path:"
  echo "$resp" | head -3
done
# /  → 302 to /en/ or /zh/ (depending on curl's Accept-Language, usually unset → /en/)
# everything else → 301 to /en/<same path>

# Root redirect with explicit Accept-Language: zh
curl -sI -H "Accept-Language: zh-CN" "https://rkteambuilder.com/" | grep -i location
# Expected: location: /zh/

# Root redirect with explicit Accept-Language: en
curl -sI -H "Accept-Language: en-US" "https://rkteambuilder.com/" | grep -i location
# Expected: location: /en/

# Querystring preserved across legacy redirect
curl -sI "https://rkteambuilder.com/dex/monsters/1?back=foo&from=bar" | grep -i location
# Expected: location: /en/dex/monsters/1?back=foo&from=bar

# REVISED 2026-07-07 — CRITICAL: share-link payload survives the redirect
# (previously shared team links are /import?t=<payload>; the payload must be
# preserved byte-for-byte or every old share link breaks)
curl -sI "https://rkteambuilder.com/import?t=SOME_LONG_BASE64_PAYLOAD" | grep -i location
# Expected: location: /en/import?t=SOME_LONG_BASE64_PAYLOAD

# REVISED 2026-07-07 — bare locale roots normalize to trailing slash
curl -sI "https://rkteambuilder.com/en" | grep -i "HTTP/2\|location"
# Expected: 301, location: /en/
curl -sI "https://rkteambuilder.com/zh" | grep -i "HTTP/2\|location"
# Expected: 301, location: /zh/

# REVISED 2026-07-07 — announcements (new since original plan)
curl -so /dev/null -w "%{http_code}\n" "https://rkteambuilder.com/en/announcements"   # 200
curl -sI "https://rkteambuilder.com/announcements" | grep -i location                  # /en/announcements

# Static assets unaffected
curl -sI https://rkteambuilder.com/logo.png | grep "HTTP/2 200"
curl -sI https://rkteambuilder.com/sitemap.xml | grep "HTTP/2 200"
curl -sI https://rkteambuilder.com/robots.txt | grep "HTTP/2 200"

# API unaffected — JSON body, not HTML
api_body=$(curl -s "https://rkteambuilder.com/api/nonexistent-xyz")
echo "$api_body" | grep -c "<!doctype"   # MUST be 0

# Sitemap is the new format
curl -s https://rkteambuilder.com/sitemap.xml | head -20
# MUST contain xhtml:link rel="alternate" and /en/ + /zh/ URLs
curl -s https://rkteambuilder.com/sitemap.xml | grep -c "<loc>"
# MUST be ~2062 (2 × current 1,030 + 2 announcements entries — REVISED 2026-07-07)

# robots.txt unchanged
curl -s https://rkteambuilder.com/robots.txt
```

### L5. Auth flow tests (manual)

1. Register new account in `/en/auth/register`. Receive verification email. **Check email link path** — must start with `https://rkteambuilder.com/en/auth/verify?...`.
2. Click link → land on `/en/auth/verify` → email verified.
3. Logout. Switch to `/zh/auth/register`. Register a *different* account. Email link must start with `https://rkteambuilder.com/zh/auth/verify?...`.
4. Forgot password flow for each user — link locale matches the user's `preferred_language`.
5. After login: redirected to `/<lang>/` (or `/<lang>/build`). User stays logged in. Switch languages — still logged in (cookie has `path="/"`).
6. Delete account flow — confirm redirect to `/<lang>/`.

### L6. Existing-share-link tests

A user with a bookmarked `/dex/monsters/123` from before the refactor opens the link:
- HTTP 301 → `/en/dex/monsters/123` → renders. Confirmed via curl in L4.

A user shares a `/zh/dex/monsters/123` link to a friend whose browser is in English:
- 200 OK direct, renders in Chinese (because URL says so). Confirmed via L2 manual test.

### L7. Search Console verification (post-deploy)

After deploy + ~3 days for crawl:
1. **URL Inspection → `https://rkteambuilder.com/zh/dex/monsters/1`** — confirm Google can fetch and render the Chinese version.
2. **URL Inspection → `https://rkteambuilder.com/dex/monsters/1` (legacy)** — confirm Google sees the 301 redirect target.
3. **Sitemaps tab** — resubmit `https://rkteambuilder.com/sitemap.xml`. Confirm "discovered" URL count doubles within a few days.
4. **International Targeting > Hreflang errors** — confirm no errors reported. Common pitfall: "No return tags" — the reciprocal hreflang on the other locale fixes this.

### L8. Performance / regression

- Run the new `verify-seo.mjs` (written per revised L3) against production.
- Check page load time of `/en/dex` and `/zh/dex` — should be identical to pre-refactor (no perf impact).
- Confirm Umami still records traffic.

---

## M. Risk Register

| # | Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|---|
| M1 | A hardcoded `<Link to="/dex">` is missed in the refactor → broken navigation | High | Medium | grep audit in H6 catches all; typecheck won't catch but Playwright + manual click-through will. |
| M2 | CloudFront Function 301 loop: `/dex` → `/en/dex` → `/en/dex` ... | Critical | Low | Function explicitly checks `uri.startsWith('/en/') || uri.startsWith('/zh/')` BEFORE the legacy-redirect branch. Test via curl in L4. |
| M3 | API request mistakenly matched by locale routing | Critical | Low | Function explicit `/api/*` short-circuit at line 1. Also `/api/*` is a separate cache behavior with its own function association (Quantity: 0). |
| M4 | Old browser-cached 301s strand users when monster IDs change | Low | Low | Monster IDs are stable (auto-increment, never reused). Even if a monster were deleted, the 301 would redirect to `/en/dex/monsters/<id>` → React 404. Acceptable. |
| M5 | Email link locale mismatch (e.g., user registers in ZH but link is `/en/...`) | Medium | Medium | H11. UNVERIFIED — need to confirm `User.preferred_language` is populated at registration. |
| M6 | Cookies break across locale change | High | Very Low | Verified: `path="/"`, `domain=None` (exact origin) → cookies match all paths under `rkteambuilder.com`. L5 confirms in production. |
| M7 | Search Console drops indexed pages during 301 transition | Medium | Medium | 301s pass equity. Worst case is a ~2-week dip in impressions while Google re-crawls. Counter-mitigation: submit fresh sitemap immediately. |
| M8 | Sitemap doubles to ~2062 URLs but file size still fine; risk of timeout in sitemap generation | Low | Very Low | Generator is O(monsters + moves) on the DB query, then linear write. Tested in current form for 1030 URLs in <1s. |
| M9 | Chinese SEO doesn't actually improve because crawler still doesn't execute JS (SPA limitation) | High | High (truthfully) | This plan unblocks crawlability but doesn't solve JS rendering. Prerendering is a separate follow-up. The inline script in H9 mitigates by setting the correct title before React runs — the most important meta signal. |
| M10 | Baidu rendering — Baidu's renderer is even weaker than Google's | High | High | Same as M9. Prerendering needed for Baidu specifically. But: even unprerendered, Baidu seeing `<title>` in Chinese (via H9) is a major improvement over the current state. |
| M11 | Analytics history "resets" because all URLs change | Low | High (expected) | Umami will see `/en/dex` and `/zh/dex` as new paths. Existing rows for `/dex` will continue to show historical data; new rows start fresh. Document this in the rollout summary. |
| M12 | Initial pageviews counted twice (legacy `/dex` 301 to `/en/dex`) | Low | Low | Umami uses `defer` script that fires after redirect → only `/en/dex` is counted. |
| M13 | Custom defender / inspector deep-links broken due to query param `back=` containing old format | Medium | Medium | `back=` values are constructed at click time from `location.pathname` — after the refactor that pathname is already locale-prefixed. So no migration of stale `back=` values is needed. UNVERIFIED for any `back=` URLs that may be stored long-term (e.g., in localStorage of an existing session). |
| M14 | I18nProvider re-renders cause flash of English content when language switches | Low | Low | The provider re-evaluates with new lang from URL; same component tree, no remount. React's batching means a single re-render. Test in L2. |
| M15 | Dev server (Vite) doesn't replicate CloudFront 302/301 behavior → dev experience hits "page not found" at `/` | Medium | Medium | Mitigation: add a SPA-level `<Navigate>` fallback in the router for the unprefixed root, so `/` → `/en` or `/zh` even in dev. This duplicates the CloudFront logic but is necessary for local dev. |
| M16 | TapTap build (hash router) regressions | High | Medium | **RESOLVED IN PLAN 2026-07-07** — two concrete breakages identified and designed around: (a) pathname-only locale detection in the inline script would show English loading text/title to TapTap's ~all-Chinese users → H9 now falls back to hash → localStorage → navigator.language; (b) hash router boots at `#/`, matching no `/:lang` route → the wildcard now redirects by stored preference / navigator.language instead of hardcoded `/en` (H1). Residual: run `npm run build:taptap` and click through `#/zh/...` routes before release. TapTap usage ended 2026-05-12 per analytics, but the tool is still published — it must not silently break. |
| M17 | NoIndex component races against hreflang from useSeoMeta on noindex pages | Low | Low | NoIndex sets only `robots` meta, leaves hreflang alone. Pages using NoIndex don't set hreflang (currently). Decision needed: do noindex pages need hreflang? Recommendation: yes (so shared links open in correct language). Need to either (a) augment NoIndex to also set hreflang, or (b) keep noindex pages without hreflang since they aren't crawled. Pick (a) for consistency. |
| M18 | The 301 redirect cache (`Cache-Control: public, max-age=3600`) means changes to redirect logic take up to 1h to propagate to repeat visitors | Medium | Low | Accept; emergency rollback uses CloudFront `/*` invalidation which clears edge cache but not browser cache. For most users, an Nx hard refresh resolves. |
| M19 | Search Console takes weeks to recrawl all ~2062 URLs | Low | High | Expected, not a bug. Submit sitemap, use Search Console "URL inspection" for sample pages to encourage re-crawl. |
| M20 | Auth pages had `noindex,nofollow` — hreflang on them sends Google a link to follow → contradiction | Low | Low | `nofollow` means Google won't follow links *from* the page; hreflang is a metadata link, not a content link. Doesn't conflict per Google docs. |

---

## N. Rollout Plan

### N1. Pre-flight checklist
- [ ] All N changes squashed into one feature branch
- [ ] `npm run typecheck` passes
- [ ] `npm run lint` passes
- [ ] `npm run build` succeeds locally
- [ ] **`npm run build:taptap` succeeds; click through `#/zh/...` routes in the dist-taptap build** (REVISED 2026-07-07 — see M16)
- [ ] `pytest -v` in `backend/` passes (with the email_service.py changes — H11)
- [ ] **New `frontend/scripts/verify-seo.mjs` (written per revised L3 — `verify-robots.mjs` does not exist) passes against `localhost:5173`**
- [ ] **CloudFront Function console-test of `buildQS` with `/import?t=<long-payload>` and multi-param URLs (P2 — MANDATORY)**
- [ ] Manual click-through every page in EN and ZH at `localhost:5173`
- [ ] **The five `switchLang` call sites behave (H4/H4b): Topbar toggle, login-with-different-preferred-language, register, settings language change, session restore**
- [ ] Generate the new sitemap.xml locally: `python3 -m backend.scripts.maintenance.generate_sitemap`
- [ ] Commit the regenerated sitemap.xml
- [ ] Backup current CloudFront distribution config:
  ```bash
  aws cloudfront get-distribution-config --id E1S4H9ALERPPY0 --region us-east-1 \
    > /tmp/cf-backup-pre-locale-$(date +%Y%m%d-%H%M%S).json
  ```
- [ ] Note the existing function ARN (`rktb-spa-routing`) so rollback can restore it

### N2. Phase 1 — Frontend code deploy (auto via CI/CD)

1. Push the feature branch's PR, get review, merge to `main`.
2. GitHub Actions auto-runs: tests → build frontend (with new sitemap.xml in `public/`) → `aws s3 sync` → CloudFront `/*` invalidation.
3. **At this point**: the SPA can render `/<lang>/*` routes IF accessed directly. But because the CloudFront Function still rewrites everything to `/index.html` without redirect logic, legacy `/dex` and `/` URLs still work the OLD way (English-only).
4. **Risk**: between Phase 1 and Phase 2, the SPA defines `/<lang>/...` routes but the CloudFront Function doesn't 301 legacy paths. Most users still hit `/dex` (no prefix) and get the React app, which now expects `/:lang` prefix → falls into the preference-based wildcard (`<RedirectToPreferredLocale />`, H1 — REVISED 2026-07-07). So they see a brief flash and then land on `/{preferred}/` (note: the wildcard goes to the locale HOME, not `/{lang}/dex` — deep legacy paths only round-trip correctly after Phase 2's 301s; keep the Phase 1→2 window short). Acceptable transitional state but worth knowing.

### N3. Phase 2 — CloudFront Function deploy (manual)

Adopt the exact sequence from [spa-routing-seo-fix.md Section 11](spa-routing-seo-fix.md#L577):

1. **Read-only preflight:**
   ```bash
   aws sts get-caller-identity   # confirm account 273130558025
   aws cloudfront get-distribution-config --id E1S4H9ALERPPY0 --region us-east-1 \
     --query "{ETag:ETag, DefaultFunc:DistributionConfig.DefaultCacheBehavior.FunctionAssociations}"
   ```
2. **Write new function code** to `/tmp/rktb-locale-routing.js` (per K1).
3. **Create function:**
   ```bash
   aws cloudfront create-function --name rktb-locale-routing \
     --function-config '{"Comment":"Locale routing: 302 root, 301 legacy → /en, SPA rewrite for /en|/zh","Runtime":"cloudfront-js-2.0"}' \
     --function-code fileb:///tmp/rktb-locale-routing.js \
     --region us-east-1
   ```
4. **Publish to LIVE:**
   ```bash
   FUNCTION_ETAG=$(aws cloudfront describe-function --name rktb-locale-routing \
     --region us-east-1 --query ETag --output text)
   aws cloudfront publish-function --name rktb-locale-routing \
     --if-match $FUNCTION_ETAG --region us-east-1
   ```
5. **Fetch+patch distribution config atomically** (per spa-routing-seo-fix.md Step 5):
   - Patch: `DefaultCacheBehavior.FunctionAssociations.Items[0].FunctionARN` from `arn:.../rktb-spa-routing` → `arn:.../rktb-locale-routing`.
   - Diff against backup; must show exactly one changed field.
6. **Apply:** `aws cloudfront update-distribution --id E1S4H9ALERPPY0 --distribution-config file:///tmp/cf-patched.json --if-match <ETag>`.
7. **Wait:** `aws cloudfront wait distribution-deployed --id E1S4H9ALERPPY0`. ~3-15 min.
8. **Invalidate:** `aws cloudfront create-invalidation --distribution-id E1S4H9ALERPPY0 --paths "/*"`.
9. **Wait additional 2 minutes** for edge propagation.

### N4. Phase 2 verification

Run all Section L tests:
- L4 smoke tests via curl
- L3 Playwright (`BASE = "https://rkteambuilder.com"`)
- L5 auth flow manual tests
- L6 share-link tests

### N5. Phase 3 — Search Console & external

1. Search Console → Sitemaps → Resubmit `https://rkteambuilder.com/sitemap.xml`.
2. Submit individual high-value URLs via URL Inspection > Request Indexing for both `/en/` and `/zh/` of:
   - Homepage
   - Dex (`/en/dex`, `/zh/dex`)
   - Top ~10 monsters (per your popularity report)
3. Bing Webmaster Tools (separate verification needed): submit sitemap.
4. Baidu Webmaster Tools (if ICP available): submit sitemap. Otherwise skip.
5. Update any external backlinks / social profiles you control to point to `/en/...` or `/zh/...`.

### N6. Monitoring (first 7 days)

Daily check:
- Search Console > Pages > Indexed count by URL (look for `/zh/...` URLs starting to appear)
- Search Console > Coverage > exclusions ("Page with redirect" should show ~1029 legacy URLs being processed)
- Umami > Top Pages — confirm `/zh/...` paths showing traffic
- CloudFront logs (if enabled) — check for 4xx or 5xx spikes
- App errors — confirm no surge in client-side errors from missed Link refactors

### N7. Decision gate at 14 days

Review:
- Total Chinese URL indexing count > 100 → SUCCESS, plan a follow-up for prerendering
- Stale at 0 → likely a hreflang or sitemap issue. Re-verify Section J.
- Many "Crawled, not indexed" → JS rendering is the blocker. Prerendering moves up in priority.

---

## O. Rollback Plan

Designed for two scenarios:
- **A. Frontend code broken** (Phase 1 deploy bad)
- **B. CloudFront Function broken** (Phase 2 deploy bad)

### Rollback A: Frontend code

Either:
1. `git revert` the merge commit on `main`, push. CI/CD auto-deploys old code.
2. OR `aws s3 sync` an older `frontend/dist/` to S3 + `/*` invalidation. (Requires the old dist still being available — recommend keeping a tarball before deploy.)

This restores SPA behavior. CloudFront Function still emits 301s for legacy → `/en/`, but the SPA now no longer expects `/<lang>/` prefix. **Effect:** all users hit `/en/dex` and the SPA tries to render `/en/dex` per the old router → 404 inside SPA.

→ Need to also rollback the CloudFront Function (Rollback B).

### Rollback B: CloudFront Function

```bash
# Step 1: Re-fetch config + ETag atomically; restore the old function ARN
python3 - << 'EOF'
import json, subprocess
result = subprocess.run(
    ["aws", "cloudfront", "get-distribution-config",
     "--id", "E1S4H9ALERPPY0", "--region", "us-east-1"],
    capture_output=True, text=True, check=True)
data = json.loads(result.stdout)
etag = data["ETag"]
config = data["DistributionConfig"]
config["DefaultCacheBehavior"]["FunctionAssociations"] = {
    "Quantity": 1,
    "Items": [{
        "FunctionARN": "arn:aws:cloudfront::273130558025:function/rktb-spa-routing",
        "EventType": "viewer-request"
    }]
}
open("/tmp/cf-rollback.json", "w").write(json.dumps(config, indent=2))
open("/tmp/cf-rollback-etag.txt", "w").write(etag)
print(f"ETag: {etag}")
EOF

# Step 2: Apply
DIST_ETAG=$(cat /tmp/cf-rollback-etag.txt)
aws cloudfront update-distribution \
  --id E1S4H9ALERPPY0 \
  --distribution-config file:///tmp/cf-rollback.json \
  --if-match "$DIST_ETAG" \
  --region us-east-1

# Step 3: Wait + invalidate
aws cloudfront wait distribution-deployed --id E1S4H9ALERPPY0 --region us-east-1
aws cloudfront create-invalidation --distribution-id E1S4H9ALERPPY0 --paths "/*" --region us-east-1

# Step 4: Verify
curl -sI https://rkteambuilder.com/dex | head -3  # should now 404 or 200 from old behavior

# Step 5: AFTER rollback fully deployed, delete the new function (optional)
FUNCTION_ETAG=$(aws cloudfront describe-function --name rktb-locale-routing \
  --region us-east-1 --query ETag --output text)
aws cloudfront delete-function --name rktb-locale-routing \
  --if-match $FUNCTION_ETAG --region us-east-1
```

### Rollback C: Sitemap

If the new sitemap.xml is malformed and breaks Search Console:
```bash
git checkout main -- frontend/public/sitemap.xml   # restore previous version
# rebuild + deploy frontend
```

### Decision criteria for rollback
Roll back if any of the following happens within 30 minutes of Phase 2 deploy:
- Smoke tests in L4 fail (any 5xx, infinite redirect, API breakage)
- Playwright tests in L3 < 95% pass rate
- Error rate visible in Umami/CloudFront logs > 2× baseline
- Auth flows in L5 broken

Otherwise, monitor for 24 hours before considering the deploy stable.

---

## P. Open Questions / UNVERIFIED Items

> **REVISED 2026-07-07:** P1, P3, P5, P12, P13 are RESOLVED (verified against the
> current codebase and the live AWS config). P2 remains the one mandatory
> pre-deploy technical verification; P11 needs input from the site owner.

### P1. ✅ RESOLVED (2026-07-07) — `User.preferred_language` field
- Exists: `User.preferred_language`, `String(5)`, default `"en"`, values `en`/`zh`.
- Populated at registration; updatable via `/auth/update-language-preference`
  (Topbar/Settings sync it); used today for transactional email BODY content.
- Bonus: all three `email_service.py` functions already accept `language` —
  see revised H11 (three-line change).

### P2. ⚠️ STILL OPEN (MANDATORY) — CloudFront Function querystring serialization
- The `buildQS` helper in K1 matches the CF JS 2.0 event-structure docs, but it
  MUST be validated in the CloudFront console function **test tab** before the
  association swap. Now load-bearing: share links carry their entire payload in
  `?t=…` (see G/import row).
- **Test URLs:** `/import?t=<long-base64>` and `/dex/monsters/1?from=builder&back=%2Fbuild`.

### P3. ✅ RESOLVED (2026-07-07) — TapTap build implications
- Two concrete breakages found and designed around; see M16 and the revised
  H1 (preference-based wildcard) + H9 (hash-aware inline script).
- `.env.taptap` confirmed: `VITE_HASH_ROUTER=true`, `VITE_HIDE_AUTH=true`,
  absolute API/asset bases — none affected by locale prefixes.
- Residual action: click through the `dist-taptap` build's `#/zh/...` routes
  before release.

### P4. DECISION CONFIRMED — drop `/<lang>/build`
- Drop the SPA route; CloudFront 301 handles legacy `/build` → `/en/`.
- **2026-07-07 addition:** dropping it REQUIRES reworking the
  `window.location.pathname !== "/build"` comparisons in
  [BuilderPage.tsx:528-529](frontend/src/features/builder/BuilderPage.tsx#L528)
  (see H6 audit note) — they silently break otherwise.

### P5. ✅ RESOLVED (2026-07-07) — Existing CloudFront Function code
- Verified live via read-only AWS calls: `rktb-spa-routing` (cloudfront-js-2.0)
  IS associated with the default behavior on viewer-request (Quantity: 1); the
  `/api/*` behavior has ZERO function associations; the LIVE function code is
  exactly the simple api/dot/index.html rewrite described in
  spa-routing-seo-fix.md. K1/K2's replace-and-swap plan applies cleanly.

### P6. UNVERIFIED — Cookie domain in cross-origin scenarios
- `docker-compose.prod.yml` sets `COOKIE_SAMESITE=none` because of TapTap CDN webview.
- Locale changes don't affect domain — should be safe.
- **Action before deploy:** smoke-test login in TapTap webview both before and after.

### P7. PARTIALLY RESOLVED (2026-07-07) — `useMonsterNavigation` hook behavior
- File confirmed to exist at `frontend/src/features/dex/useMonsterNavigation.ts`.
- Navigates via `navigate(\`/dex/monsters/${(form as any).id}?...\`)` — needs `localized(...)` wrap.
- **Action during implementation:** read it fully while applying H6 (it's on the H6 grep's radar).

### P8. UNVERIFIED — Specific call sites
The Explore agent flagged a few specific lines as ambiguous in the link inventory. Should re-verify before editing:
- `MonsterDetailPage.tsx:327` (incomplete in grep output)
- `MonsterInspector.tsx` navigate target (not shown)
- `SavedTeamPage.tsx:1` navigate (visible but target not extracted)

### P9. ✅ RESOLVED (2026-07-07) — Treatment of unprefixed root in dev server
- Production CloudFront 302s `/` based on Accept-Language; dev has no equivalent.
- Resolved by H1's `<RedirectToPreferredLocale />` wildcard (localStorage →
  `navigator.language` → en), which serves BOTH `vite dev` AND the TapTap
  hash-router build (which boots at `#/`). No Vite middleware needed — the tiny
  dev/prod behavioral difference at `/` is acceptable.

### P10. Open question — Should `lang` cookie be set for CloudFront's root redirect to honor user preference?
- Today: `/` → Accept-Language → `/en/` or `/zh/`.
- Better UX: `/` checks an `rktb-lang` cookie (set by the SPA when user switches language) → if present, redirect to that lang. Falls back to Accept-Language. Falls back to `en`.
- **Trade-off:** adds a cookie (privacy notice consideration); needs CF Function to read cookies (supported in CF JS 2.0).
- **Recommendation:** skip in v1, add in v2 if user feedback indicates need.

### P11. UNVERIFIED — Bing/Baidu existing index state
- Don't have access to either webmaster tool.
- **Action:** ask the user to confirm whether sitemaps were ever submitted to Bing/Baidu.

### P12. ✅ RESOLVED (2026-07-07) — Share-URL generation
- [sharePayload.ts:52-53](frontend/src/features/share/sharePayload.ts#L52):
  `` `${base}/import?t=${encodeSharePayload(...)}` `` where `base` is
  `VITE_ASSET_BASE_URL || window.location.origin` — **no locale, whole payload
  in the query string.** Two consequences folded into the plan:
  1. OLD share links rely on the legacy 301 preserving `?t=…` (K1 §6 + L4 test).
  2. NEW share links should embed the current locale:
     `` `${base}/${lang}/import?t=…` `` — pass `lang` into `buildShareUrl` from
     the caller (TeamShareModal has `useI18n`). Add to H6's file list.

### P13. ✅ RESOLVED (2026-07-07) — spa-routing Phase 2 is in production
- Confirmed live via `aws cloudfront get-distribution-config` /
  `describe-function` / `get-function` (see P5). No trust required.

### P14. Open question — Migration timing
- Recommend deploying during low-traffic hours.
- Recommend NOT deploying same week as any other big change (e.g., right before/after a TapTap submission).

---

## Appendix: Quick reference for the implementer

**Critical files to change (REVISED 2026-07-07):**
1. `frontend/src/router.tsx` (`/:lang` wrapper + preference-based wildcard; keep the `createHashRouter` conditional)
2. `frontend/src/main.tsx` — **NO changes** (the original "reorder providers" step is dead; see H3)
3. `frontend/src/App.tsx` (validate lang param; render `<LocaleFromUrl />`)
4. `frontend/src/i18n.tsx` (URL-synced provider + `switchLang`; `LocaleFromUrl`; `detectInitialLang`)
5. `frontend/src/components/Topbar.tsx` (switcher → `switchLang`, ~line 214)
6. `frontend/src/features/auth/AuthProvider.tsx`, `LoginPage.tsx`, `RegisterPage.tsx`, `SettingsPage.tsx` (the other four `setLang` consumers — H4b)
7. `frontend/src/lib/locale.ts` (NEW — `useLocalizedPath`/`localizedPath` helpers)
8. `frontend/src/hooks/useSeoMeta.ts` (emit hreflang; trailing-slash normalization per revised H7)
9. `frontend/src/components/NoIndex.tsx` (also emit hreflang — recommended)
10. `frontend/index.html` (hash-aware inline script + hreflang defaults)
11. `frontend/src/features/share/sharePayload.ts` (+ caller in TeamShareModal — locale in new share links, P12)
12. `frontend/src/features/builder/BuilderPage.tsx:528-529` (`window.location.pathname !== "/build"` rework — H6/P4)
13. `backend/scripts/maintenance/generate_sitemap.py` (xhtml:link format + `/announcements`)
14. `backend/email_service.py` (locale in 3 URLs — three-line change, H11)
15. `frontend/scripts/verify-seo.mjs` (NEW — L3 harness; `verify-robots.mjs` does not exist)
16. CloudFront Function: replace `rktb-spa-routing` with `rktb-locale-routing` (final code in K1)
17. ~55 sites across ~25 components for `<Link>` / `navigate()` updates (H6 greps + the pathname-comparison grep)

**Files verified 2026-07-07 (no longer "verify before changing"):**
- `backend/models.py` — `preferred_language` exists (String(5), en/zh) ✅
- `frontend/src/features/share/sharePayload.ts` — read; change folded in (P12) ✅
- Live CloudFront config/function — verified via AWS CLI (P5/P13) ✅
- `frontend/src/features/dex/useMonsterNavigation.ts` — exists; read during H6 (P7)
- `.env.taptap` / TapTap contracts — verified; fixes folded in (P3/M16) ✅

**Estimated effort:** 1.5-2.5 days of focused work + 1 day of testing + 30 min CloudFront deploy (original estimate +~0.5 day for the 2026-07-07 amendments: switchLang consumers, verify-seo.mjs from scratch, TapTap checks).

**Estimated downtime:** Zero, if the rollout plan in Section N is followed.

**Estimated SEO recovery time:** 4-8 weeks for Chinese pages to start appearing in Google. Bing/Baidu may take longer (or shorter, depending on submission).
