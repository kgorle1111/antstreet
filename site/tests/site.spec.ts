import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { copyFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const SHOTS = process.env.SHOTS_DIR ?? "../posts/marketing/site-shots";
mkdirSync(SHOTS, { recursive: true });
const WIDTHS = [360, 375, 768, 1440];
const SCHEMES = ["light", "dark"] as const;
const MOTIONS = ["no-preference", "reduce"] as const;
type Opts = { w?: number; scheme?: (typeof SCHEMES)[number]; motion?: (typeof MOTIONS)[number] };

/** Opens the page with the given viewport and media, and collects every console error or warning. */
async function open(page: Page, { w = 1440, scheme = "dark", motion = "reduce" }: Opts = {}) {
  const problems: string[] = [];
  page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") problems.push(`${m.type()}: ${m.text()}`); });
  page.on("pageerror", (e) => problems.push(`pageerror: ${e.message}`));
  await page.addInitScript(() => {
    (window as any).__cls = 0;
    new PerformanceObserver((l) => {
      for (const e of l.getEntries() as any[]) if (!e.hadRecentInput) (window as any).__cls += e.value;
    }).observe({ type: "layout-shift", buffered: true });
  });
  await page.setViewportSize({ width: w, height: w < 768 ? 800 : w < 1024 ? 1024 : 900 });
  await page.emulateMedia({ colorScheme: scheme, reducedMotion: motion });
  await page.goto("./");
  if (motion === "no-preference") await page.waitForFunction(() => (window as any).__hookDone === true, null, { timeout: 12_000 });
  else await page.waitForLoadState("load");
  return problems;
}

async function scrollTo(page: Page, y: number) {
  await page.evaluate((y) => window.scrollTo(0, y), y);
  await page.waitForTimeout(1500); // scrub smoothing settles
}

for (const w of WIDTHS) {
  for (const scheme of SCHEMES) {
    for (const motion of MOTIONS) {
      test(`screens ${w} ${scheme} ${motion}`, async ({ page }) => {
        const problems = await open(page, { w, scheme, motion });
        const name = join(SHOTS, `${w}-${scheme}-${motion === "reduce" ? "reduced" : "motion"}`);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(w);
        await page.screenshot({ path: `${name}-top.png` });
        if (motion === "reduce") {
          await page.screenshot({ path: `${name}-full.png`, fullPage: true });
        } else {
          // mid-scroll stills: half-way through the 77's pin and the gate's pin, and the quiz
          for (const [id, f] of [["problem", 0.45], ["how", 0.55], ["quiz", 0]] as const) {
            const y = await page.evaluate(([id, f]) => {
              const s = document.getElementById(id)!;
              const spacer = s.querySelector(".pin-spacer") as HTMLElement | null;
              const top = s.getBoundingClientRect().top + scrollY;
              return top + (spacer ? spacer.offsetHeight * f : 0);
            }, [id, f] as const);
            await scrollTo(page, y);
            await page.screenshot({ path: `${name}-${id}.png` });
          }
        }
        expect(problems).toEqual([]);
      });
    }
  }
}

for (const scheme of SCHEMES) {
  for (const motion of MOTIONS) {
    test(`axe AA ${scheme} ${motion}`, async ({ page }) => {
      await open(page, { scheme, motion });
      const res = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
      expect(res.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
    });
  }
}

test("reduced motion: nothing runs, nothing pins, no smooth scroll, final frames", async ({ page }) => {
  const problems = await open(page, { motion: "reduce" });
  await page.waitForTimeout(1000);
  const state = await page.evaluate(() => ({
    running: document.getAnimations().filter((a) => a.playState === "running").length,
    pins: document.querySelectorAll(".pin-spacer").length,
    lenis: document.documentElement.classList.contains("lenis"),
    motion: Boolean((window as any).__antMotion),
    fails: document.querySelectorAll(".cell.is-fail").length,
    panels: getComputedStyle(document.querySelector(".how-panels")!).display,
  }));
  expect(state).toEqual({ running: 0, pins: 0, lenis: false, motion: false, fails: 29, panels: "grid" });
  await expect(page.getByText("It wrote its own checks.")).toBeVisible();
  await expect(page.locator(".hook-sub")).toBeVisible();
  expect(problems).toEqual([]);
});

test("motion: the hook ends level and still, smooth scroll on desktop, pins exist", async ({ page }) => {
  await open(page, { motion: "no-preference" });
  const state = await page.evaluate(() => ({
    transforms: [...document.querySelectorAll<HTMLElement>(".hook-stage .layer")].map((l) => l.style.transform),
    lenis: document.documentElement.classList.contains("lenis"),
    pins: document.querySelectorAll(".pin-spacer").length,
  }));
  for (const t of state.transforms) expect(t).toBe("translate(0px, 0px) scale(1) rotate(0deg)");
  expect(state.lenis).toBe(true);
  expect(state.pins).toBe(2);
});

for (const motion of MOTIONS) {
  test(`layout shift is 0 (${motion})`, async ({ page }) => {
    await open(page, { motion });
    for (let y = 0; y < 6; y++) { await page.mouse.wheel(0, 900); await page.waitForTimeout(150); }
    await page.waitForTimeout(800);
    expect(await page.evaluate(() => (window as any).__cls)).toBe(0);
  });
}

test("keyboard: skip link, a 3 px focus ring on every stop, the grid moves by arrows", async ({ page }) => {
  await open(page, { motion: "reduce" });
  await page.keyboard.press("Tab");
  const skip = page.locator(".skip");
  await expect(skip).toBeFocused();
  await expect(skip).toBeInViewport();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
  const stops: string[] = [];
  for (let i = 0; i < 60; i++) {
    await page.keyboard.press("Tab");
    const s = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement;
      const cs = getComputedStyle(el);
      return { label: (el.getAttribute("aria-label") ?? el.textContent ?? "").trim().slice(0, 40), ring: cs.outlineWidth, style: cs.outlineStyle, tag: el.tagName };
    });
    if (s.tag === "BODY") break;
    expect(s.style, s.label).toBe("solid");
    expect(s.ring, s.label).toBe("3px");
    stops.push(s.label);
  }
  const cells = stops.filter((s) => / run (heldout3|final3), rep /.test(s));
  expect(cells.length).toBe(1); // one tab stop for the whole grid
  for (const want of ["Try antstreet audit", "Strict count", "Yes", "Copy the install commands", "Honest limits", "Star on GitHub"]) {
    expect(stops.some((s) => s.startsWith(want)), want).toBe(true);
  }
  const first = page.locator(".cell").first();
  await first.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator(".cell").nth(1)).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.locator(".cell").nth(12)).toBeFocused();
  await expect(page.locator("#inspector")).toContainText("Hidden check failed");
});

test("strict count: 13 cells go hollow and 16 of 77 is highlighted", async ({ page }) => {
  await open(page, { motion: "reduce" });
  const toggle = page.getByRole("button", { name: "Strict count", exact: true });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  expect(await page.locator("#problem.strict-on .cell.is-fail[data-drop]").count()).toBe(13);
  await expect(page.locator(".strict-note")).toBeVisible();
  await expect(page.locator(".strict-mark")).toHaveCSS("background-color", "rgb(255, 198, 26)");
});

for (const motion of MOTIONS) {
  test(`quiz: either answer reveals every beat (${motion})`, async ({ page }) => {
    await open(page, { motion });
    await page.getByRole("button", { name: "No", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Yes. Arabic-Indic digits." })).toBeVisible();
    if (motion === "no-preference") {
      for (let i = 0; i < 4; i++) { await page.getByRole("button", { name: "Next" }).click(); await page.waitForTimeout(900); }
      await expect(page.getByRole("button", { name: "Next" })).toBeHidden();
    }
    for (const beat of ["task", "code", "hidden", "data"]) await expect(page.locator(`[data-beat="${beat}"]`)).toBeVisible();
    await expect(page.locator('[data-beat="data"]')).toContainText("9 of the 29 failed only on non-ASCII input");
    await expect(page.locator('[data-beat="data"]')).toContainText("16 of 77 under a strict count");
    const roll = await page.evaluate(() => (document.querySelector(".quiz-stage .layer") as HTMLElement).style.transform);
    expect(roll).not.toContain("rotate(-"); // level when the data card is on screen
    await page.locator('[data-beat="code"]').scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(SHOTS, `quiz-answered-${motion === "reduce" ? "reduced" : "motion"}.png`) });
  });
}

test("LCP under 2.0 s on a throttled phone profile", async ({ page }) => {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", { offline: false, latency: 150, downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8 });
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  await page.setViewportSize({ width: 375, height: 800 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("./");
  await page.waitForTimeout(4000);
  const lcp = await page.evaluate(() => new Promise<number>((r) => {
    new PerformanceObserver((l) => { const e = l.getEntries(); r(e[e.length - 1].startTime); }).observe({ type: "largest-contentful-paint", buffered: true });
  }));
  test.info().annotations.push({ type: "lcp-ms", description: String(Math.round(lcp)) });
  expect(lcp).toBeLessThan(2000);
});

for (const scheme of SCHEMES) {
  test(`no flashes in the hook (${scheme})`, async ({ browser }) => {
    const dir = join(test.info().outputDir, "video");
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: scheme, reducedMotion: "no-preference", recordVideo: { dir, size: { width: 720, height: 450 } }, baseURL: "http://localhost:4321/antstreet/" });
    const page = await ctx.newPage();
    const bg = scheme === "dark" ? "#0f1b2d" : "#f4f1ea";
    await page.setContent(`<body style="margin:0;background:${bg}"></body>`);
    await page.waitForTimeout(1000);
    await page.goto("./");
    await page.waitForFunction(() => (window as any).__hookDone === true, null, { timeout: 12_000 });
    await page.waitForTimeout(500);
    const video = await page.video()!.path();
    await ctx.close();
    copyFileSync(video, join(SHOTS, `hook-${scheme}.webm`));
    const out = execFileSync("ffmpeg", ["-v", "error", "-i", video, "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-", "-f", "null", "-"], { encoding: "utf8", maxBuffer: 1 << 26 });
    const y = [...out.matchAll(/YAVG=([\d.]+)/g)].map((m) => Number(m[1]));
    const fps = 25; // Playwright records at 25 fps
    const ref = y[Math.round(0.8 * fps)]; // the same-colour page before the site
    const start = y.findIndex((v, i) => i > 0.8 * fps && Math.abs(v - ref) > 0.5) - 1; // the site's first frame
    const series = y.slice(Math.max(0, start));
    const jumps = series.slice(1).map((v, i) => Math.abs(v - series[i]));
    const perSecond = new Map<number, number>();
    jumps.forEach((d, i) => { if (d > 25) perSecond.set(Math.floor(i / fps), (perSecond.get(Math.floor(i / fps)) ?? 0) + 1); });
    test.info().annotations.push({ type: "flash", description: JSON.stringify({ frames: series.length, firstStep: jumps[0], maxStep: Math.max(...jumps) }) });
    expect(Math.max(0, ...perSecond.values())).toBeLessThanOrEqual(3);
    // jumps[0] is the page's own first paint over a same-colour page (content appearing, reported);
    // frame 0 -> 1 of the page's timeline must not jump.
    expect(jumps[1]).toBeLessThan(8);
  });
}

/** Every text-bearing element in the section is fully visible: effective opacity ≥ 0.99 (its own
 *  and every ancestor's), visibility visible. Decorative aria-hidden art and content that is not
 *  rendered (display: none, e.g. an unanswered quiz beat) are out of scope; captions shown one at a
 *  time ([data-sequenced]) may have at most one visible. */
async function hiddenText(page: Page, id: string) {
  return page.evaluate((id) => {
    const section = document.getElementById(id)!;
    const bad: string[] = [];
    for (const el of section.querySelectorAll<HTMLElement>("*")) {
      const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent!.trim());
      if (!own || el.closest("[aria-hidden='true'], [data-sequenced], script, style, svg")) continue;
      if (!el.getClientRects().length) continue; // not rendered
      let opacity = 1;
      for (let a: HTMLElement | null = el; a && a !== document.body; a = a.parentElement) opacity *= Number(getComputedStyle(a).opacity);
      if (opacity < 0.99 || getComputedStyle(el).visibility !== "visible") bad.push(`${el.tagName}.${el.className}: ${el.textContent!.trim().slice(0, 40)} (${opacity.toFixed(2)}, ${getComputedStyle(el).visibility})`);
    }
    const seq = [...section.querySelectorAll<HTMLElement>("[data-sequenced]")].filter((e) => getComputedStyle(e).visibility === "visible" && Number(getComputedStyle(e).opacity) > 0.01);
    if (seq.length > 1) bad.push(`${seq.length} sequenced captions visible at once`);
    return bad;
  }, id);
}

const SECTIONS = ["problem", "quiz", "how", "try", "no", "next", "built-by", "cta"];
for (const w of [800, 1440]) {
  for (const how of ["anchor", "wheel"] as const) {
    test(`content stays visible after a ${how} jump (${w}, motion)`, async ({ page }) => {
      const problems = await open(page, { w, motion: "no-preference" });
      for (const id of SECTIONS) {
        if (how === "anchor") {
          await page.evaluate((id) => { location.hash = id; }, id);
        } else {
          await page.mouse.move(w / 2, 400);
          for (let i = 0; i < 40; i++) {
            const top = await page.evaluate((id) => document.getElementById(id)!.getBoundingClientRect().top, id);
            if (Math.abs(top) < 200) break;
            await page.mouse.wheel(0, Math.sign(top) * Math.min(2400, Math.abs(top)));
            await page.waitForTimeout(60);
          }
        }
        await page.waitForTimeout(1500);
        expect(await hiddenText(page, id), `${id} by ${how}`).toEqual([]);
      }
      expect(problems).toEqual([]);
    });
  }
}

for (const w of [800, 1440]) {
  test(`the scanner label never covers a cell (${w})`, async ({ page }) => {
    await open(page, { w, motion: "no-preference" });
    const range = await page.evaluate(() => {
      const s = document.getElementById("problem")!;
      const spacer = s.querySelector(".pin-spacer") as HTMLElement | null;
      const top = s.getBoundingClientRect().top + scrollY;
      return [top, top + (spacer ? spacer.offsetHeight : s.offsetHeight)];
    });
    for (let f = 0; f <= 1; f += 0.125) {
      await scrollTo(page, range[0] + (range[1] - range[0]) * f);
      const overlap = await page.evaluate(() => {
        const l = document.querySelector(".scan-label")!.getBoundingClientRect();
        return [...document.querySelectorAll(".cell")].some((c) => {
          const r = c.getBoundingClientRect();
          return r.left < l.right && r.right > l.left && r.top < l.bottom && r.bottom > l.top;
        });
      });
      expect(overlap, `at ${f}`).toBe(false);
    }
  });
}
