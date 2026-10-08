// Every interactive part works without motion; motion is added only when the reader allows it
// (prefers-reduced-motion: no-preference). Without this script the page shows every final frame.
import { hook } from "./hook";
import { problemControls } from "./problem-controls";
import { quiz } from "./quiz";

const motion = matchMedia("(prefers-reduced-motion: no-preference)").matches;
const problem = document.querySelector<HTMLElement>("#problem");

// copy buttons, with a polite status for screen readers
const status = document.createElement("p");
status.className = "visually-hidden";
status.setAttribute("role", "status");
document.body.append(status);
document.querySelectorAll<HTMLButtonElement>("button.copy").forEach((b) =>
  b.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(b.dataset.copy ?? "");
      b.textContent = "Copied";
      status.textContent = "Commands copied";
    } catch {
      b.textContent = "Select and copy";
    }
    setTimeout(() => { b.textContent = "Copy"; status.textContent = ""; }, 1800);
  }),
);

// the replay plays once when it is in view, then holds its last frame (reduced motion: the SVG
// itself shows only the last frame)
const demo = document.querySelector<HTMLImageElement>("img.demo-img[data-src]");
if (demo) {
  const load = () => { demo.src = demo.dataset.src!; };
  if (!motion || !("IntersectionObserver" in window)) load();
  else {
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.intersectionRatio >= 0.4)) { load(); io.disconnect(); } }, { threshold: [0.4] });
    io.observe(demo);
  }
}

if (problem) problemControls(problem);
quiz(motion);

if (motion) {
  (window as any).__antMotion = true;
  Promise.race([document.fonts.ready, new Promise((r) => setTimeout(r, 300))]).then(() => {
    hook();
    import("./scroll").then((m) => m.scroll());
  });
}
