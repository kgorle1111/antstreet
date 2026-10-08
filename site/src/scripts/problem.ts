// 5.2 The 77: a scanner bar crosses the grid and each false pass it crosses turns into a diamond;
// a FLIP sort brings the 29 to the front. B1 and its caveat are HUD text: always on screen, never
// moved, never gated by the animation.
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { E } from "./rig";

export function problemMotion(section: HTMLElement) {
  const cells = [...section.querySelectorAll<HTMLButtonElement>(".cell")];
  const layer = section.querySelector<HTMLElement>(".grid-layer")!;
  const grid = section.querySelector<HTMLElement>(".cells")!;
  const scanner = section.querySelector<HTMLElement>(".scanner")!;
  const fails = cells.filter((c) => c.dataset.fp);

  // FLIP: the document order is the sorted order; every cell starts at its original slot.
  let slots: number[][] = [];
  let rowMid: number[] = [];
  let H = 0;
  const measure = () => {
    slots = cells.map((c) => [c.offsetLeft, c.offsetTop]); // layout boxes ignore transforms
    rowMid = fails.map((c) => slots[Number(c.dataset.cell)][1] + c.offsetHeight / 2);
    H = grid.offsetHeight;
  };
  measure();
  const from = (axis: 0 | 1) => (k: number, c: HTMLElement) => slots[Number(c.dataset.cell)][axis] - slots[k][axis];
  fails.forEach((c) => c.classList.remove("is-fail"));
  scanner.style.display = "block";

  const follow = { k: 1 };
  const update = () => {
    const bar = Number(gsap.getProperty(scanner, "y"));
    fails.forEach((c, i) => c.classList.toggle("is-fail", bar >= rowMid[i]));
    // the camera follows the bar at 0.12x; the 34 px under the label covers its largest travel (0.06·H)
    gsap.set(layer, { y: -0.12 * follow.k * (bar - H / 2) });
  };

  const sortSpan = 24 + 0.4 * (cells.length - 1); // frames: each move takes 24, they start 0.4 apart
  const tl = gsap.timeline({ paused: true, onUpdate: () => update() });
  tl.fromTo(scanner, { y: -8 }, { y: () => H + 2, duration: 2, ease: E.inOut }, 0);
  tl.to(scanner, { autoAlpha: 0, duration: 0.05, ease: "none" }, 2);
  tl.to(follow, { k: 0, duration: 0.3, ease: E.inOut }, 2);
  tl.fromTo(cells, { x: from(0), y: from(1) }, { x: 0, y: 0, duration: 24 / sortSpan, ease: E.inOut, stagger: 0.4 / sortSpan }, 2);

  const mm = gsap.matchMedia();
  mm.add({ pin: "(min-width: 960px) and (min-height: 700px)", flow: "not ((min-width: 960px) and (min-height: 700px))" }, (ctx) => {
    const pinned = Boolean(ctx.conditions?.pin);
    ScrollTrigger.create({
      trigger: pinned ? section.querySelector(".problem-grid")! : section.querySelector(".grid-stage")!,
      start: pinned ? "center center" : "top 80%",
      end: pinned ? "+=240%" : "bottom 30%",
      pin: pinned,
      scrub: 1,
      animation: tl,
      invalidateOnRefresh: true,
      onRefreshInit: measure,
      onRefresh: update,
    });
  });
  update();
}
