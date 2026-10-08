// Everything driven by scrolling, loaded after the hook has started so it is not in the first
// view's JavaScript. Only imported when motion is allowed.
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import Lenis from "lenis";
import { how } from "./how";
import { problemMotion } from "./problem";
import { E } from "./rig";

gsap.registerPlugin(ScrollTrigger);

export function scroll() {
  const problem = document.querySelector<HTMLElement>("#problem");
  // smooth scroll on desktop with a mouse only; never on touch
  if (matchMedia("(hover: hover) and (pointer: fine) and (min-width: 1024px)").matches) {
    const lenis = new Lenis({ lerp: 0.1 });
    lenis.on("scroll", ScrollTrigger.update);
    gsap.ticker.add((t) => lenis.raf(t * 1000));
    gsap.ticker.lagSmoothing(0);
    (window as any).__lenis = lenis;
  }
  if (problem) problemMotion(problem);
  how();

  // results: rise 24 px and fade in, 80 ms apart, then still
  const cards = gsap.utils.toArray<HTMLElement>("#no .no-card");
  gsap.set(cards, { autoAlpha: 0, y: 24 });
  ScrollTrigger.batch(cards, { start: "top 90%", once: true, onEnter: (els) => gsap.to(els, { autoAlpha: 1, y: 0, duration: 0.6, ease: E.outExpo, stagger: 0.08 }) });

  // counters land exactly on the source number
  document.querySelectorAll<HTMLElement>("#built-by [data-count]").forEach((el) => {
    const final = el.textContent!;
    const to = Number(el.dataset.count);
    const fmt = (n: number) => ({ plus: `${Math.round(n).toLocaleString("en-US")}+`, pct: `${Math.round(n)}%`, int: `${Math.round(n)}` })[el.dataset.fmt as "plus"];
    const o = { n: 0 };
    el.textContent = fmt(0);
    gsap.to(o, {
      n: to, duration: 0.9, ease: E.outExpo,
      scrollTrigger: { trigger: el, start: "top 90%", once: true },
      onUpdate: () => { el.textContent = fmt(o.n); },
      onComplete: () => { el.textContent = final; },
    });
  });
  if (document.readyState === "complete") ScrollTrigger.refresh();
  else addEventListener("load", () => ScrollTrigger.refresh());
}
