// Dev aid: seek a CSS-animated SVG to set times and screenshot it. node scripts/svgframes.mjs FILE OUT scheme t1,t2,...
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";

const [file, out, scheme = "dark", times = "0", motion = "no-preference"] = process.argv.slice(2);
const svg = readFileSync(file, "utf8");
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1200, height: 700 }, colorScheme: scheme, reducedMotion: motion });
await page.setContent(`<body style="margin:0;background:#888">${svg}</body>`);
await page.waitForTimeout(200);
for (const t of times.split(",").map(Number)) {
  await page.evaluate((ms) => document.getAnimations().forEach((a) => { a.pause(); a.currentTime = ms; }), t);
  await page.screenshot({ path: `${out}-${scheme}-${motion}-${t}.png`, clip: { x: 0, y: 0, width: 1200, height: 640 } });
}
await browser.close();
