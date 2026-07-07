/**
 * SEO verification for the bilingual URL refactor.
 *
 * Meta tags (canonical, hreflang, robots, og:url) are written by client-side
 * JS (useSeoMeta/NoIndex), so a real browser is required — this uses
 * Playwright. Run against the dev server or production:
 *
 *   BASE=http://localhost:5173 node scripts/verify-seo.mjs
 *   BASE=https://rkteambuilder.com node scripts/verify-seo.mjs
 *
 * Requires: npm i -D playwright && npx playwright install chromium
 */
import { chromium } from "playwright";

const BASE = process.env.BASE || "http://localhost:5173";
const SITE = "https://rkteambuilder.com";

// [path, canonical, hreflang-en, hreflang-zh, hreflang-x-default, robots, htmlLang]
const tests = [
  ["/en/",               `${SITE}/en/`,               `${SITE}/en/`,               `${SITE}/zh/`,               `${SITE}/en/`,               "index, follow",    "en"],
  ["/zh/",               `${SITE}/zh/`,               `${SITE}/en/`,               `${SITE}/zh/`,               `${SITE}/en/`,               "index, follow",    "zh"],
  ["/en/dex",            `${SITE}/en/dex`,            `${SITE}/en/dex`,            `${SITE}/zh/dex`,            `${SITE}/en/dex`,            "index, follow",    "en"],
  ["/zh/dex",            `${SITE}/zh/dex`,            `${SITE}/en/dex`,            `${SITE}/zh/dex`,            `${SITE}/en/dex`,            "index, follow",    "zh"],
  ["/en/dex/monsters/1", `${SITE}/en/dex/monsters/1`, `${SITE}/en/dex/monsters/1`, `${SITE}/zh/dex/monsters/1`, `${SITE}/en/dex/monsters/1`, "index, follow",    "en"],
  ["/zh/dex/monsters/1", `${SITE}/zh/dex/monsters/1`, `${SITE}/en/dex/monsters/1`, `${SITE}/zh/dex/monsters/1`, `${SITE}/en/dex/monsters/1`, "index, follow",    "zh"],
  ["/en/dex/moves/1",    `${SITE}/en/dex/moves/1`,    `${SITE}/en/dex/moves/1`,    `${SITE}/zh/dex/moves/1`,    `${SITE}/en/dex/moves/1`,    "index, follow",    "en"],
  ["/en/announcements",  `${SITE}/en/announcements`,  `${SITE}/en/announcements`,  `${SITE}/zh/announcements`,  `${SITE}/en/announcements`,  "index, follow",    "en"],
  ["/zh/announcements",  `${SITE}/zh/announcements`,  `${SITE}/en/announcements`,  `${SITE}/zh/announcements`,  `${SITE}/en/announcements`,  "index, follow",    "zh"],
  // noindex pages: hreflang still emitted (NoIndex component), robots noindex
  ["/en/teams",          null,                        `${SITE}/en/teams`,          `${SITE}/zh/teams`,          `${SITE}/en/teams`,          "noindex, follow",  "en"],
  ["/en/auth/login",     null,                        `${SITE}/en/auth/login`,     `${SITE}/zh/auth/login`,     `${SITE}/en/auth/login`,     "noindex, nofollow", "en"],
  ["/zh/auth/login",     null,                        `${SITE}/en/auth/login`,     `${SITE}/zh/auth/login`,     `${SITE}/en/auth/login`,     "noindex, nofollow", "zh"],
  ["/en/feedback",       null,                        `${SITE}/en/feedback`,       `${SITE}/zh/feedback`,       `${SITE}/en/feedback`,       "noindex, follow",  "en"],
];

const browser = await chromium.launch();
const page = await browser.newPage();
let pass = 0, fail = 0;

function check(path, name, actual, expected) {
  if (expected === null) return; // not asserted for this page
  if (actual === expected) { pass++; }
  else { fail++; console.log(`  FAIL ${path} ${name}:\n    expected ${expected}\n    actual   ${actual}`); }
}

for (const [path, canonical, hrefEn, hrefZh, hrefXd, robots, htmlLang] of tests) {
  await page.goto(BASE + path, { waitUntil: "domcontentloaded", timeout: 30000 });
  // Wait until useSeoMeta/NoIndex have written the hreflang tags (client-side).
  await page.waitForSelector('link[rel="alternate"][hreflang="zh"]', { timeout: 15000 })
    .catch(() => {});
  await page.waitForTimeout(300);

  const got = await page.evaluate(() => ({
    canonical: document.querySelector('link[rel="canonical"]')?.href ?? null,
    hrefEn: document.querySelector('link[rel="alternate"][hreflang="en"]')?.href ?? null,
    hrefZh: document.querySelector('link[rel="alternate"][hreflang="zh"]')?.href ?? null,
    hrefXd: document.querySelector('link[rel="alternate"][hreflang="x-default"]')?.href ?? null,
    robots: document.querySelector('meta[name="robots"]')?.content ?? null,
    htmlLang: document.documentElement.lang,
    title: document.title,
  }));

  check(path, "canonical", got.canonical, canonical);
  check(path, "hreflang=en", got.hrefEn, hrefEn);
  check(path, "hreflang=zh", got.hrefZh, hrefZh);
  check(path, "hreflang=x-default", got.hrefXd, hrefXd);
  check(path, "robots", got.robots, robots);
  check(path, "html lang", got.htmlLang, htmlLang);
  console.log(`${path}  →  lang=${got.htmlLang}  robots="${got.robots}"  title="${got.title.slice(0, 40)}..."`);
}

await browser.close();
console.log(`\n${pass} checks passed, ${fail} failed`);
process.exit(fail > 0 ? 1 : 0);
