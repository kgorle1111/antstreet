// Renders public/assets/og.png (1200x630) from the README hero's final frame (reduced motion).
//   node scripts/og.mjs   (then quantised to 128 colours with PIL to stay well under 120 KB)
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";

const hero = readFileSync(new URL("../../docs/assets/hero.svg", import.meta.url), "utf8");
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, colorScheme: "dark", reducedMotion: "reduce" });
await page.setContent(`<body style="margin:0;background:#0f1b2d;display:grid;place-items:center;height:630px">${hero}</body>`);
await page.screenshot({ path: new URL("../public/assets/og.png", import.meta.url).pathname });
await browser.close();
