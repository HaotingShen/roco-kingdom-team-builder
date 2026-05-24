# SPA Routing / SEO Fix — Production-Safety Plan

**Status:** Phase 1 complete (2026-05-17). Phase 2 complete (2026-05-17).

---

## Section 1 — Current Diagnosis

**Root cause:** S3 website hosting serves `index.html` (correct body, correct content-type) for all extensionless SPA routes but always with **HTTP 404** status. CloudFront passes this 404 through unchanged. Browsers render the React app regardless and users see correct pages. Google strictly respects the HTTP status code and refuses to index any page returning 404.

Confirmed via `curl -sI`:

| Route | Status | Body | Server |
|---|---|---|---|
| `/` | 200 | index.html | S3 (DefaultRootObject) |
| `/dex` | 404 | index.html | S3 (error document) |
| `/dex/monsters/1` | 404 | S3 error | S3 |
| `/dex/moves/1` | 404 | S3 error | S3 |
| `/build`, `/teams`, `/feedback` | 404 | S3 error | S3 |
| `/assets/index-B7EM5158.js` | 200 | JS bundle | S3 |
| `/robots.txt`, `/sitemap.xml`, `/favicon/favicon.ico` | 200 | correct files | S3 |
| `/api/types` | 405 | application/json | nginx (EC2) |
| `/api/nonexistent-xyz` | 404 | `{"detail":"Not Found"}` | nginx (EC2) |

API 404s are completely separate from S3. They return JSON from nginx. Any fix scoped to the S3/default CloudFront behavior does not touch them.

---

## Section 2 — Current Architecture

CloudFront distribution: `E1S4H9ALERPPY0`  
ETag at time of review: `E234HDVPYTUVNS` (re-fetch immediately before any write)

**Two origins:**

| Origin ID | Domain | Type | Secret sent |
|---|---|---|---|
| S3 | `rktb-frontend.s3-website-ap-southeast-1.amazonaws.com` | S3 website hosting | Referer header |
| API | `origin-api.rkteambuilder.com` | EC2/nginx | X-Origin-Verify header |

**Two behaviors:**

| Path Pattern | Origin | Cache Policy | Methods | Functions |
|---|---|---|---|---|
| `/api/*` | EC2/nginx | Managed-CachingDisabled (TTL=0) | All 7 | None |
| `/*` (default) | S3 website | Managed-CachingOptimized (DefaultTTL=86400) | GET/HEAD | None (to be added) |

S3 website hosting config:
```json
{ "IndexDocument": "index.html", "ErrorDocument": "index.html" }
```

CI/CD: On every push to main, GitHub Actions runs `aws s3 sync` + `aws cloudfront create-invalidation --paths "/*"`. This already clears all CloudFront cache on every deploy, so the 24h DefaultTTL is effectively mitigated for users.

Cache headers: Neither `index.html` nor assets currently have `Cache-Control` headers set in S3. Both default to 24h CloudFront TTL. The `/*` invalidation on deploy compensates. (Flagged as a future improvement: hashed assets should have `Cache-Control: public, max-age=31536000, immutable`.)

---

## Section 3 — Route Indexability Classification

### Indexable — `index, follow`

| Route | Reason |
|---|---|
| `/` | Homepage. Currently the only indexed page. Canonical source of truth. |
| `/dex` | Public content — the jingling dex. High SEO value. In sitemap. |
| `/dex/monsters/:id` | Public content — unique title/description per jingling. Highest SEO value. |
| `/dex/moves/:id` | Public content — unique title/description per move. High SEO value. |

### Indexable with canonical redirect — `index, follow` + `canonical: /`

| Route | Reason |
|---|---|
| `/build` | Duplicate of `/` (same component). Receives `index, follow` but with `canonical: /` so Google consolidates ranking signals to `/` rather than splitting them. |

### Non-indexable utility — `noindex, follow`

These pages are public and accessible, but should not appear in search results. `follow` is appropriate because they may contain links to indexable content. Telling Google to follow links but not index the page itself is correct.

| Route | Reason |
|---|---|
| `/teams` | User-specific saved teams list. Content varies per user. Not a search destination. |
| `/teams/:id` | User-specific team detail. Same reason. |
| `/feedback` | Functional form. Not a search destination. |
| `/import` | Share import tool. Not a search destination. |

### Non-indexable private — `noindex, nofollow`

These pages are auth-gated, admin-only, or session-dependent. `nofollow` prevents Google from following any links from these pages.

| Route | Reason |
|---|---|
| `/build/analyze/:slot` | Requires an active team/slot context. Meaningless without session state. |
| `/auth/login` | Auth page. Private. |
| `/auth/register` | Auth page. Private. |
| `/auth/forgot-password` | Auth page. Private. |
| `/auth/reset-password` | Auth page. Private. |
| `/auth/verify` | Auth page. Private. |
| `/auth/confirm-email` | Auth page. Private. |
| `/settings` | Account settings. Private. |
| `/admin` | Admin dashboard. Private. |

---

## Section 4 — Frontend Code Changes

### 4a. `index.html` — add default robots meta tag

Add inside `<head>`, before the closing `</head>`:

```html
<meta name="robots" content="index, follow" />
```

This sets a sensible default. Every page that calls `useSeoMeta` with `noindex: true` will override it via JavaScript. Pages that don't call `useSeoMeta` at all will inherit this default — which is acceptable since the indexable pages (`/dex`, detail pages) all call `useSeoMeta`.

### 4b. `src/hooks/useSeoMeta.ts` — add noindex parameter

```ts
import { useEffect } from "react";
import { useLocation } from "react-router-dom";

const BASE_URL = "https://rkteambuilder.com";

interface SeoMeta {
  title: string;
  description: string;
  canonicalPath?: string;
  noindex?: boolean;
  nofollow?: boolean;
}

function setAttr(selector: string, attr: string, value: string) {
  const el = document.querySelector(selector);
  if (el) el.setAttribute(attr, value);
}

export function useSeoMeta({ title, description, canonicalPath, noindex, nofollow }: SeoMeta) {
  const { pathname } = useLocation();
  const canonical = canonicalPath ?? pathname;

  useEffect(() => {
    document.title = title;
    const url = `${BASE_URL}${canonical}`;

    setAttr('meta[name="description"]', "content", description);
    setAttr('meta[property="og:title"]', "content", title);
    setAttr('meta[property="og:description"]', "content", description);
    setAttr('meta[property="og:url"]', "content", url);
    setAttr('meta[name="twitter:title"]', "content", title);
    setAttr('meta[name="twitter:description"]', "content", description);
    setAttr('link[rel="canonical"]', "href", url);

    const indexPart = noindex ? "noindex" : "index";
    const followPart = nofollow ? "nofollow" : "follow";
    setAttr('meta[name="robots"]', "content", `${indexPart}, ${followPart}`);
  }, [title, description, canonical, noindex, nofollow]);
}
```

### 4c. `src/components/NoIndex.tsx` — new component for pages without useSeoMeta

```tsx
import { useEffect } from "react";

interface NoIndexProps {
  nofollow?: boolean;
}

function setAttr(selector: string, attr: string, value: string) {
  document.querySelector(selector)?.setAttribute(attr, value);
}

export default function NoIndex({ nofollow = false }: NoIndexProps) {
  useEffect(() => {
    const followPart = nofollow ? "nofollow" : "follow";
    setAttr('meta[name="robots"]', "content", `noindex, ${followPart}`);
  }, [nofollow]);
  return null;
}
```

### 4d. Changes to existing pages with useSeoMeta

> **Same-commit requirement:** `<meta name="robots">` does not currently exist in `index.html`. The `setAttr` helper silently does nothing if the element is missing. All `useSeoMeta` and `NoIndex` robots changes depend on the tag added in Section 4a. **All changes in Section 4 must land in a single commit.** Do not push the hook/component changes without the `index.html` change, or robots overrides will silently fail in production until the next deploy.

**BuilderPage.tsx** — `canonicalPath: "/"` is **already present at line 302**. No change needed for canonicalization. The `noindex` parameter defaults to `undefined` (falsy), so `index, follow` is already the result without any code change. Verify the existing call looks like:

```ts
// Already correct — no changes needed
useSeoMeta({
  title: ...,
  description: ...,
  canonicalPath: "/",   // already exists
  // noindex not set → defaults to false → "index, follow"
});
```

`/` will receive `index, follow` with canonical `/`.  
`/build` will receive `index, follow` with canonical `/` — Google sees `/build` as a duplicate of `/` and consolidates ranking signals rather than splitting them. This is cleaner than `noindex` for a duplicate route.

**TeamsListPage.tsx** — add `noindex: true`. Preserve the existing `canonicalPath: "/teams"` at line 58:
```ts
useSeoMeta({
  title: ...,
  description: ...,
  canonicalPath: "/teams",  // already exists — keep it
  noindex: true,            // add this
});
// result: "noindex, follow"
```

**SavedTeamPage.tsx:**
```ts
useSeoMeta({ title: ..., description: ..., noindex: true });
// "noindex, follow"
```

### 4e. Add `<NoIndex />` to pages without useSeoMeta

| File | nofollow value | Robots result |
|---|---|---|
| `MonsterAnalysisPage.tsx` | `true` | `noindex, nofollow` |
| `LoginPage.tsx` | `true` | `noindex, nofollow` |
| `RegisterPage.tsx` | `true` | `noindex, nofollow` |
| `ForgotPasswordPage.tsx` | `true` | `noindex, nofollow` |
| `ResetPasswordPage.tsx` | `true` | `noindex, nofollow` |
| `VerifyEmailPage.tsx` | `true` | `noindex, nofollow` |
| `ConfirmEmailChangePage.tsx` | `true` | `noindex, nofollow` |
| `SettingsPage.tsx` | `true` | `noindex, nofollow` |
| `AdminPage.tsx` | `true` | `noindex, nofollow` |
| `FeedbackPage.tsx` | `false` | `noindex, follow` |
| `ImportPage.tsx` | `false` | `noindex, follow` |

Usage pattern:

```tsx
import NoIndex from "@/components/NoIndex";

export default function LoginPage() {
  return (
    <>
      <NoIndex nofollow />
      {/* rest of component */}
    </>
  );
}
```

---

## Section 5 — Sitemap Changes

File: `frontend/public/sitemap.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://rkteambuilder.com/</loc>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://rkteambuilder.com/dex</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>
</urlset>
```

Removed: `/teams` (user-specific content, should not be in sitemap).  
Not added yet: `/dex/monsters/:id` and `/dex/moves/:id` — these are the highest-value SEO pages but require a build-time data fetch to enumerate all valid IDs. Deferred as a separate future enhancement.

---

## Section 6 — CloudFront Function

- **Name:** `rktb-spa-routing`
- **Runtime:** `cloudfront-js-2.0`
- **Event type:** `viewer-request`
- **Behavior:** Default behavior (`/*` → S3) only

```javascript
function handler(event) {
    var request = event.request;
    var uri = request.uri;

    // Defense-in-depth: if somehow an /api/ path reaches this behavior,
    // pass it through unchanged. (In normal operation /api/* is handled
    // by the separate API cache behavior and never reaches this function.)
    if (uri.startsWith('/api/')) {
        return request;
    }

    // Pass through / — handled by CloudFront DefaultRootObject (index.html).
    // Pass through anything with a dot — real static files (.js, .css, .png,
    // .ico, .txt, .xml, .webp, .woff2, etc.) must reach S3 as-is.
    // Rewrite everything else to /index.html — these are SPA routes.
    if (uri !== '/' && !uri.includes('.')) {
        request.uri = '/index.html';
    }

    return request;
}
```

**How every path is handled:**

| Incoming URI | Has dot? | Starts with /api/? | Action | S3 response |
|---|---|---|---|---|
| `/` | — | No | Untouched (DefaultRootObject) | 200, index.html |
| `/dex` | No | No | → `/index.html` | 200, index.html |
| `/dex/monsters/1` | No | No | → `/index.html` | 200, index.html |
| `/dex/moves/1` | No | No | → `/index.html` | 200, index.html |
| `/build` | No | No | → `/index.html` | 200, index.html |
| `/teams` | No | No | → `/index.html` | 200, index.html |
| `/auth/login` | No | No | → `/index.html` | 200, index.html |
| `/admin` | No | No | → `/index.html` | 200, index.html |
| `/assets/index-B7EM5158.js` | Yes | No | Untouched | 200, JS bundle |
| `/assets/deleted-old.js` | Yes | No | Untouched | 404 preserved |
| `/robots.txt` | Yes | No | Untouched | 200 |
| `/sitemap.xml` | Yes | No | Untouched | 200 |
| `/favicon/favicon.ico` | Yes | No | Untouched | 200 |
| `/api/monsters` | No | Yes | Untouched (defense) | EC2/nginx |

---

## Section 7 — Deployment Order

Phase 1 must complete and be verified before Phase 2 begins.

### Phase 1 — Frontend code changes (safe, auto-deploys via CI/CD)

1. Add `<meta name="robots" content="index, follow" />` to `index.html`
2. Extend `useSeoMeta` with `noindex` and `nofollow` parameters
3. Create `src/components/NoIndex.tsx`
4. Verify `BuilderPage.tsx` already has `canonicalPath: "/"` — **no change needed**
5. Update `TeamsListPage.tsx` — add `noindex: true` (keep existing `canonicalPath: "/teams"`)
6. Update `SavedTeamPage.tsx` — add `noindex: true`
7. Add `<NoIndex nofollow />` to: `MonsterAnalysisPage`, `LoginPage`, `RegisterPage`, `ForgotPasswordPage`, `ResetPasswordPage`, `VerifyEmailPage`, `ConfirmEmailChangePage`, `SettingsPage`, `AdminPage`
8. Add `<NoIndex />` to: `FeedbackPage`, `ImportPage`
9. Update `sitemap.xml` — remove `/teams`

Commit and push → CI/CD auto-deploys to S3, runs `/*` CloudFront invalidation. No manual AWS steps needed.

Verify Phase 1 using the browser-rendered verification steps in Section 9 before proceeding.

### Phase 2 — CloudFront Function (manual AWS steps, requires explicit approval)

1. Read-only preflight (Section 8)
2. Create and publish the function
3. Backup current distribution config
4. Generate and review the config patch
5. Apply `update-distribution` with patched config
6. Invalidate CloudFront cache
7. Run smoke tests (Section 10)
8. Run browser-rendered verification (Section 9)
9. Google Search Console follow-up (Section 12)

---

## Section 8 — Read-Only Preflight Commands

All commands in this section are safe read-only checks. Do not run write commands until these pass.

```bash
# 1. Confirm correct AWS account
aws sts get-caller-identity
# Expected: "Account": "273130558025"

# 2. Confirm distribution and capture fresh ETag
aws cloudfront get-distribution-config --id E1S4H9ALERPPY0 --region us-east-1 \
  --query "{ETag:ETag, DefaultOrigin:DistributionConfig.DefaultCacheBehavior.TargetOriginId,
ApiPath:DistributionConfig.CacheBehaviors.Items[0].PathPattern,
DefaultFunctions:DistributionConfig.DefaultCacheBehavior.FunctionAssociations.Quantity,
ApiFunctions:DistributionConfig.CacheBehaviors.Items[0].FunctionAssociations.Quantity}"
# Expected:
#   ETag: current value (may differ from E234HDVPYTUVNS if any change happened since review)
#   DefaultOrigin: rktb-frontend.s3-website-ap-southeast-1.amazonaws.com-...
#   ApiPath: /api/*
#   DefaultFunctions: 0
#   ApiFunctions: 0

# 3. Verify Phase 1 static robots tag is present in the HTML body
# curl cannot see JS-injected per-route overrides — it always sees the static default from index.html.
# The static default added in Section 4a is "index, follow", so that is what curl will return for ALL routes.
curl -s https://rkteambuilder.com/ | grep 'name="robots"'
# Expected after Phase 1: <meta name="robots" content="index, follow" />
# Per-route overrides (e.g. noindex on /teams) are JS-injected — verify those via Playwright (Section 9).

# 4. Confirm /dex still returns index.html body
curl -s https://rkteambuilder.com/dex | grep -c "<!doctype"
# Expected: 1

# 5. Confirm API is healthy
curl -sI https://rkteambuilder.com/api/types | head -3
# Expected: HTTP/2 200 or 405, server: nginx

# 6. Confirm static assets serve correctly
# Note: hashed JS/CSS filenames change on every deploy — use stable public files instead
curl -sI https://rkteambuilder.com/logo.png | grep "HTTP/2 200"
curl -sI https://rkteambuilder.com/sitemap.xml | grep "HTTP/2 200"
curl -sI https://rkteambuilder.com/robots.txt | grep "HTTP/2 200"

# 7. Confirm sitemap no longer contains /teams (after Phase 1 deploys)
# grep -v would silently hide the teams line and appear to pass — use positive grep instead
! curl -s https://rkteambuilder.com/sitemap.xml | grep -q "teams" \
  && echo "PASS: /teams absent from sitemap" \
  || echo "FAIL: /teams still present in sitemap"
```

---

## Section 9 — Browser-Rendered Verification (noindex)

`curl` cannot see JavaScript-injected `<meta>` tags. These must be verified in a rendered browser context.

### Option A — Playwright script (recommended)

> **Phase 1 vs Phase 2:** Before Phase 2 (CloudFront Function), SPA routes like `/teams` still return HTTP 404 from S3. While Playwright's `page.goto()` doesn't throw on 404, S3 may serve its XML error page instead of `index.html` for some paths, meaning the React app never boots and the robots meta won't be set. To avoid false failures, **run Phase 1 verification against the local dev server** (`localhost:5173`) where all routes return 200. Run Phase 2 verification against production (`rkteambuilder.com`).

Install once if not already present:
```bash
cd /tmp
npm init -y
npm install playwright
npx playwright install chromium
```

Save as `/tmp/verify-robots.mjs`. Change `BASE` to `http://localhost:5173` for Phase 1, `https://rkteambuilder.com` for Phase 2:

> **Monster/move ID assumption:** The script uses IDs `1` for `/dex/monsters/1` and `/dex/moves/1`. Verify that these IDs exist in the database before running (they almost certainly do since IDs are auto-incremented from 1, but confirm if in doubt). If ID 1 doesn't exist, the detail page renders an error state and robots may not be set — substitute a known-good ID.

```js
import { chromium } from "playwright";

// Phase 1 (before CloudFront Function): use "http://localhost:5173"
// Phase 2 (after CloudFront Function):  use "https://rkteambuilder.com"
const BASE = "http://localhost:5173";

const routes = [
  // [path, expectedRobots, description]
  ["/",               "index, follow",     "Homepage — must stay indexed"],
  ["/build",          "index, follow",     "Builder duplicate — canonical to /"],
  ["/dex",            "index, follow",     "Dex — must stay indexed"],
  ["/dex/monsters/1", "index, follow",     "Monster detail — must stay indexed"],
  ["/dex/moves/1",    "index, follow",     "Move detail — must stay indexed"],
  ["/teams",          "noindex, follow",   "Teams list — must be noindex"],
  ["/teams/1",        "noindex, follow",   "Saved team — must be noindex"],
  ["/feedback",       "noindex, follow",   "Feedback — must be noindex"],
  ["/import",         "noindex, follow",   "Import — must be noindex"],
  ["/auth/login",     "noindex, nofollow", "Login — must be noindex nofollow"],
  ["/auth/register",  "noindex, nofollow", "Register — must be noindex nofollow"],
  ["/settings",       "noindex, nofollow", "Settings — must be noindex nofollow"],
  ["/admin",          "noindex, nofollow", "Admin — must be noindex nofollow"],
];

// Canonical checks: [path, expectedCanonical]
// Note: useSeoMeta always uses BASE_URL = "https://rkteambuilder.com" regardless of
// which server you're testing against, so canonical URLs always point to production.
const canonicalChecks = [
  ["/",               "https://rkteambuilder.com/"],
  ["/build",          "https://rkteambuilder.com/"],
  ["/dex",            "https://rkteambuilder.com/dex"],
  ["/dex/monsters/1", "https://rkteambuilder.com/dex/monsters/1"],
  ["/dex/moves/1",    "https://rkteambuilder.com/dex/moves/1"],
];

const browser = await chromium.launch();
const page = await browser.newPage();
let passed = 0;
let failed = 0;

for (const [path, expected, desc] of routes) {
  await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 15000 });
  const robots = await page.$eval(
    'meta[name="robots"]',
    el => el.getAttribute("content")
  ).catch(() => "(not found)");

  const ok = robots === expected;
  if (ok) passed++; else failed++;
  console.log(`${ok ? "✓ PASS" : "✗ FAIL"}  ${path}  [robots]`);
  if (!ok) console.log(`       expected: "${expected}"\n       got:      "${robots}"\n       (${desc})`);
}

for (const [path, expectedCanonical] of canonicalChecks) {
  await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 15000 });
  const canonical = await page.$eval(
    'link[rel="canonical"]',
    el => el.getAttribute("href")
  ).catch(() => "(not found)");

  const ok = canonical === expectedCanonical;
  if (ok) passed++; else failed++;
  console.log(`${ok ? "✓ PASS" : "✗ FAIL"}  ${path}  [canonical → ${canonical}]`);
  if (!ok) console.log(`       expected: "${expectedCanonical}"`);
}

await browser.close();
console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
```

Run after Phase 1 deploys. For Phase 1, point `BASE` at `http://localhost:5173` and run `npm run dev` first:
```bash
# In one terminal: cd frontend && npm run dev
# In another terminal:
node /tmp/verify-robots.mjs
```

After Phase 2, change `BASE` to `https://rkteambuilder.com` and re-run. Wait at least 2 minutes after `aws cloudfront wait distribution-deployed` completes before running — edge propagation can lag behind the distribution update by 1–2 minutes.

All lines must show `✓ PASS` before proceeding to Phase 2.

### Option B — Browser DevTools (manual fallback)

For each route, open Chrome DevTools → Elements tab → search for `robots` in the `<head>`. Verify the `content` attribute matches the expected value from the table in Section 3.

---

## Section 10 — Smoke Tests (after Phase 2)

```bash
# ── SPA routes must return HTTP 200 ──────────────────────────────────
for path in /dex /dex/monsters/1 /dex/moves/1 /build /teams /teams/1 \
            /feedback /import /auth/login /auth/register /settings /admin; do
  status=$(curl -so /dev/null -w "%{http_code}" "https://rkteambuilder.com$path")
  echo "$path → $status"
done
# All must print: 200

# ── Homepage must still return 200 ───────────────────────────────────
curl -sI https://rkteambuilder.com/ | grep "HTTP/2 200"

# ── Static assets must still return 200 ─────────────────────────────
# Use stable public files — hashed JS/CSS filenames change on every deploy
curl -sI https://rkteambuilder.com/logo.png | grep "HTTP/2 200"
curl -sI https://rkteambuilder.com/robots.txt | grep "HTTP/2 200"
curl -sI https://rkteambuilder.com/sitemap.xml | grep "HTTP/2 200"
curl -sI https://rkteambuilder.com/favicon/favicon.ico | grep "HTTP/2 200"

# ── Missing static asset must stay 404 ───────────────────────────────
curl -sI "https://rkteambuilder.com/assets/nonexistent-XXXXXXXX.js" | grep "HTTP/2 404"

# ── API must be completely unaffected ────────────────────────────────
curl -sI "https://rkteambuilder.com/api/nonexistent-endpoint-xyz" | grep "HTTP/2 404"

api_body=$(curl -s "https://rkteambuilder.com/api/nonexistent-endpoint-xyz")
echo "API 404 body: $api_body"
# Must be: {"detail":"Not Found"}

echo "$api_body" | grep -c "<!doctype"
# Must be: 0 (if 1, the CF Function is incorrectly intercepting API requests — rollback immediately)

# ── Confirm /dex body is index.html (React app, not S3 XML error) ────
curl -s https://rkteambuilder.com/dex | grep -c "<!doctype"
# Must be: 1
```

Re-run the Playwright script from Section 9 after Phase 2 as well to confirm robots tags are still correct.

---

## Section 11 — Phase 2 Write Commands

> **Do not run any command in this section until explicitly approved.**

### Step 1 — Backup current distribution config

```bash
# [WRITE — safe backup, no production change]
# Use a named variable — avoids glob concatenation bugs if this step is run more than once
CF_BACKUP=/tmp/cf-backup-$(date +%Y%m%d-%H%M%S).json
aws cloudfront get-distribution-config --id E1S4H9ALERPPY0 --region us-east-1 > "$CF_BACKUP"
echo "Backup written to $CF_BACKUP"
python3 -c "import json; print('ETag:', json.load(open('$CF_BACKUP'))['ETag'])"
```

### Step 2 — Write the function code to a local file

```bash
# [LOCAL ONLY — no AWS change]
cat > /tmp/rktb-spa-routing.js << 'EOF'
function handler(event) {
    var request = event.request;
    var uri = request.uri;
    if (uri.startsWith('/api/')) {
        return request;
    }
    if (uri !== '/' && !uri.includes('.')) {
        request.uri = '/index.html';
    }
    return request;
}
EOF
echo "Function code written to /tmp/rktb-spa-routing.js"
```

### Step 3 — Create the function

```bash
# [WRITE — creates function in DEVELOPMENT stage, not yet associated with distribution]
aws cloudfront create-function \
  --name "rktb-spa-routing" \
  --function-config '{"Comment":"Rewrite extensionless SPA routes to /index.html for React Router","Runtime":"cloudfront-js-2.0"}' \
  --function-code fileb:///tmp/rktb-spa-routing.js \
  --region us-east-1
# Save the FunctionARN from output: arn:aws:cloudfront::273130558025:function/rktb-spa-routing
# Save the ETag from output as FUNCTION_ETAG
```

### Step 4 — Publish the function

```bash
# [WRITE — promotes function to LIVE stage, still not associated with distribution]
FUNCTION_ETAG=$(aws cloudfront describe-function --name "rktb-spa-routing" \
  --region us-east-1 --query ETag --output text)
aws cloudfront publish-function \
  --name "rktb-spa-routing" \
  --if-match $FUNCTION_ETAG \
  --region us-east-1

# Verify LIVE status before proceeding
aws cloudfront describe-function --name "rktb-spa-routing" \
  --region us-east-1 --query "FunctionSummary.Status" --output text
# Must return: LIVE
```

### Step 5 — Fetch current config, patch, and save ETag atomically

> **Safety rule:** The config and ETag come from one fetch. The ETag written here is the only one used in Step 6. Do NOT re-fetch the ETag separately before applying. If significant time passes between this step and Step 6 (e.g. you paused, stepped away, or made any other CloudFront change), discard `/tmp/cf-dist-config-patched.json` and `/tmp/cf-dist-etag.txt` and re-run this step from scratch.

```bash
# [LOCAL ONLY — no AWS change, fetches config+ETag together, generates patched JSON for review]
python3 - << 'EOF'
import json, subprocess

result = subprocess.run(
    ["aws", "cloudfront", "get-distribution-config",
     "--id", "E1S4H9ALERPPY0", "--region", "us-east-1"],
    capture_output=True, text=True, check=True
)
data = json.loads(result.stdout)
etag = data["ETag"]
config = data["DistributionConfig"]

# Patch: add function to DefaultCacheBehavior only
config["DefaultCacheBehavior"]["FunctionAssociations"] = {
    "Quantity": 1,
    "Items": [{
        "FunctionARN": "arn:aws:cloudfront::273130558025:function/rktb-spa-routing",
        "EventType": "viewer-request"
    }]
}

with open("/tmp/cf-dist-config-patched.json", "w") as f:
    json.dump(config, f, indent=2)

# Write ETag alongside the patched config — Step 6 reads it from here, never re-fetches
with open("/tmp/cf-dist-etag.txt", "w") as f:
    f.write(etag)

print(f"ETag saved: {etag}")
print()
print("DefaultCacheBehavior FunctionAssociations (AFTER patch):")
print(json.dumps(config["DefaultCacheBehavior"]["FunctionAssociations"], indent=2))
print()
print("/api/* behavior FunctionAssociations (must be unchanged — Quantity: 0):")
print(json.dumps(config["CacheBehaviors"]["Items"][0]["FunctionAssociations"], indent=2))
EOF
```

Review the output carefully before proceeding. Must confirm:
- `DefaultCacheBehavior` shows `Quantity: 1` with the correct `FunctionARN`
- `/api/*` behavior shows `Quantity: 0` — unchanged

Then run a formal diff against the backup to prove only the intended field changed:

```bash
# [LOCAL ONLY — no AWS change]
python3 - << 'EOF'
import json

# Use the most recent backup file
import glob, os
backup_file = max(glob.glob("/tmp/cf-backup-*.json"), key=os.path.getmtime)
orig = json.load(open(backup_file))["DistributionConfig"]
patched = json.load(open("/tmp/cf-dist-config-patched.json"))

def find_diffs(a, b, path=""):
    keys = set(list(a) + list(b))
    for k in sorted(keys):
        p = f"{path}.{k}" if path else k
        av, bv = a.get(k), b.get(k)
        if isinstance(av, dict) and isinstance(bv, dict):
            find_diffs(av, bv, p)
        elif av != bv:
            print(f"DIFF: {p}")
            print(f"  was:    {json.dumps(av)[:120]}")
            print(f"  now:    {json.dumps(bv)[:120]}")

find_diffs(orig, patched)
EOF
# Expected output: exactly one DIFF block for DefaultCacheBehavior.FunctionAssociations
# If any other field is shown, DO NOT proceed — re-run Step 5
```

### Step 6 — Apply the update

> **Use the ETag saved in Step 5.** Do not re-fetch. If the files from Step 5 are stale (time passed, any other CloudFront change occurred), re-run Step 5 before continuing here.

```bash
# [WRITE — modifies live CloudFront distribution]
DIST_ETAG=$(cat /tmp/cf-dist-etag.txt)
echo "Applying with ETag: $DIST_ETAG"

aws cloudfront update-distribution \
  --id E1S4H9ALERPPY0 \
  --distribution-config file:///tmp/cf-dist-config-patched.json \
  --if-match "$DIST_ETAG" \
  --region us-east-1

# Wait for global propagation (typically 1-3 min, up to 15 min)
echo "Waiting for distribution to deploy..."
aws cloudfront wait distribution-deployed --id E1S4H9ALERPPY0 --region us-east-1
echo "Distribution deployed."
```

### Step 7 — Invalidate CloudFront cache

```bash
# [WRITE — clears all cached content so new routing takes effect immediately]
aws cloudfront create-invalidation \
  --distribution-id E1S4H9ALERPPY0 \
  --paths "/*" \
  --region us-east-1
```

---

## Section 12 — Google Search Console Follow-up

After smoke tests and Playwright verification pass:

1. **URL Inspection → `/dex`**
   - Click "Test Live URL"
   - Confirm rendered page shows the Dex content (jinglings list)
   - Confirm Coverage section shows "URL is on Google" or "Discovered — currently not indexed"
   - Confirm no "Noindex" signal detected
   - Click "Request Indexing"
2. **URL Inspection → `/`**
   - Confirm still indexed, canonical is `https://rkteambuilder.com/`
3. **URL Inspection → `/teams`**
   - Confirm "noindex" signal is detected in rendered page
   - Confirm excluded from indexing
4. **URL Inspection → `/build`**
   - Confirm canonical points to `https://rkteambuilder.com/`
   - Confirm no duplicate indexing issue
5. **Coverage report** — over the following days/weeks, monitor whether `/dex` moves from "Discovered" to "Indexed". Individual detail pages (`/dex/monsters/:id`) will be discovered by Google crawling links from `/dex` and will eventually be indexed automatically.

---

## Section 13 — Rollback Plan

Purpose: Restore the old 404-for-SPA-routes behavior without affecting anything else. Does not touch the `/api/*` behavior, origins, cache policies, or any other distribution setting.

> **Safety rule:** Same as Section 11 — fetch config and ETag together, patch together, apply immediately. Do not re-fetch the ETag separately before `update-distribution`.

```bash
# Step 1: Fetch current config+ETag atomically, patch, save both
python3 - << 'EOF'
import json, subprocess

result = subprocess.run(
    ["aws", "cloudfront", "get-distribution-config",
     "--id", "E1S4H9ALERPPY0", "--region", "us-east-1"],
    capture_output=True, text=True, check=True
)
data = json.loads(result.stdout)
etag = data["ETag"]
config = data["DistributionConfig"]

# Patch: remove ONLY the rktb-spa-routing function by ARN
# Filtering by ARN (not replacing with empty) ensures any other future function
# associations on the default behavior are not accidentally removed.
TARGET_ARN = "arn:aws:cloudfront::273130558025:function/rktb-spa-routing"
existing = config["DefaultCacheBehavior"].get("FunctionAssociations", {}).get("Items", [])
filtered = [i for i in existing if i["FunctionARN"] != TARGET_ARN]
config["DefaultCacheBehavior"]["FunctionAssociations"] = {
    "Quantity": len(filtered),
    "Items": filtered
}

with open("/tmp/cf-rollback.json", "w") as f:
    json.dump(config, f, indent=2)

# Write ETag alongside rollback config — Step 2 reads it from here, never re-fetches
with open("/tmp/cf-rollback-etag.txt", "w") as f:
    f.write(etag)

print(f"ETag saved: {etag}")
print("Rollback config written to /tmp/cf-rollback.json")
print("DefaultCacheBehavior FunctionAssociations after rollback:")
print(json.dumps(config["DefaultCacheBehavior"]["FunctionAssociations"], indent=2))
print("/api/* behavior (must be unchanged):")
print(json.dumps(config["CacheBehaviors"]["Items"][0]["FunctionAssociations"], indent=2))
EOF

# Step 2: Apply rollback — use the ETag saved above, not a new fetch
DIST_ETAG=$(cat /tmp/cf-rollback-etag.txt)
echo "Applying rollback with ETag: $DIST_ETAG"

aws cloudfront update-distribution \
  --id E1S4H9ALERPPY0 \
  --distribution-config file:///tmp/cf-rollback.json \
  --if-match "$DIST_ETAG" \
  --region us-east-1

# Step 3: Wait for propagation
aws cloudfront wait distribution-deployed --id E1S4H9ALERPPY0 --region us-east-1
echo "Rollback deployed. SPA routes return 404 again."

# Step 4: Verify rollback
curl -sI https://rkteambuilder.com/dex | grep "HTTP/2 404"
# Should return 404 again

# Step 5: Only delete the function AFTER confirming rollback is fully deployed
FUNCTION_ETAG=$(aws cloudfront describe-function --name "rktb-spa-routing" \
  --region us-east-1 --query ETag --output text)
aws cloudfront delete-function \
  --name "rktb-spa-routing" \
  --if-match $FUNCTION_ETAG \
  --region us-east-1
```

---

## Section 14 — Risk Checklist Before Approval

### Phase 1 (frontend code changes)

- [ ] All Section 4 changes (robots meta tag, `useSeoMeta`, `NoIndex`, page changes) are in a **single commit** — `setAttr` silently fails if `meta[name="robots"]` doesn't exist in the DOM yet
- [ ] `useSeoMeta` change is backwards-compatible — `noindex` and `nofollow` default to `undefined` (falsy), so all existing callers are unaffected
- [ ] `NoIndex` component renders `null` — no visual output, safe to add anywhere
- [ ] `BuilderPage.tsx` — `canonicalPath: "/"` already exists at line 302, verified, no change needed
- [ ] `TeamsListPage.tsx` — `noindex: true` added while preserving existing `canonicalPath: "/teams"`
- [ ] `sitemap.xml` change removes only `/teams` — `/` and `/dex` retained
- [ ] `index.html` robots default tag added — does not break anything, overridden per-page by JS
- [ ] CI/CD auto-deploys on push to main with `/*` CloudFront invalidation — no manual steps needed
- [ ] Playwright Phase 1 run: all robots tags correct, all canonical URLs correct for indexable pages

### Phase 2 (CloudFront Function)

- [ ] Phase 1 verified via Playwright script (run against localhost) — all routes pass
- [ ] AWS account confirmed as `273130558025`
- [ ] Distribution ID confirmed as `E1S4H9ALERPPY0`
- [ ] Preflight confirms `DefaultFunctions: 0` and `ApiFunctions: 0` before proceeding
- [ ] Config and ETag fetched together in one step; ETag saved to `/tmp/cf-dist-etag.txt`; `update-distribution` reads ETag from that file — never re-fetched separately
- [ ] Diff output shows exactly one changed field: `DefaultCacheBehavior.FunctionAssociations` — no other diffs
- [ ] `/api/*` behavior `FunctionAssociations.Quantity` confirmed as `0` in diff
- [ ] Function published as `LIVE` status before association
- [ ] Backup file written to named `$CF_BACKUP` variable (not glob)
- [ ] `/*` CloudFront invalidation queued after `update-distribution`
- [ ] Waited ≥ 2 minutes after `distribution-deployed` before running smoke tests and Playwright
- [ ] Smoke tests pass — especially: API 404 body is JSON (not HTML), missing assets return 404, all SPA routes return 200
- [ ] Playwright Phase 2 run (against production): all robots and canonical checks pass
- [ ] Rollback script uses ARN-filtered removal — only `rktb-spa-routing` is removed, other functions unaffected
