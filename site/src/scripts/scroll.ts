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

  // Reveals never make content visible: every element is visible by default and stays visible if
  // its reveal never fires. A reveal starts only when an IntersectionObserver sees the element on
  // screen, so no trigger position can be stale (pins, fonts, Lenis).
  const onSight = (els: Element[], enter: (el: HTMLElement, i: number) => void) => {
    let batch = 0;
    const io = new IntersectionObserver((entries) => {
      entries.filter((e) => e.isIntersecting).forEach((e) => {
        io.unobserve(e.target);
        enter(e.target as HTMLElement, batch++);
      });
      batch = 0;
    }, { rootMargin: "0px 0px -8% 0px" });
    els.forEach((el) => io.observe(el));
  };

  // results: rise 24 px and fade in, 80 ms apart, then still
  onSight(gsap.utils.toArray<HTMLElement>("#no .no-card"), (el, i) =>
    gsap.from(el, { y: 24, autoAlpha: 0, duration: 0.6, ease: E.outExpo, delay: i * 0.08, clearProps: "all" }),
  );

  // counters: the real number never leaves the page text; the count-up is an aria-hidden copy
  // drawn over it, removed when it lands exactly on the source number
  onSight([...document.querySelectorAll<HTMLElement>("#built-by [data-count]")], (el) => {
    const to = Number(el.dataset.count);
    const fmt = (n: number) => ({ plus: `${Math.round(n).toLocaleString("en-US")}+`, pct: `${Math.round(n)}%`, int: `${Math.round(n)}` })[el.dataset.fmt as "plus"];
    const shadow = document.createElement("span");
    shadow.className = "num-anim";
    shadow.setAttribute("aria-hidden", "true");
    el.append(shadow);
    el.classList.add("counting");
    const o = { n: 0 };
    shadow.textContent = fmt(0);
    gsap.to(o, {
      n: to, duration: 0.9, ease: E.outExpo,
      onUpdate: () => { shadow.textContent = fmt(o.n); },
      onComplete: () => { shadow.remove(); el.classList.remove("counting"); },
    });
  });
  document.fonts.ready.then(() => ScrollTrigger.refresh());
  if (document.readyState === "complete") ScrollTrigger.refresh();
  else addEventListener("load", () => ScrollTrigger.refresh());
}
