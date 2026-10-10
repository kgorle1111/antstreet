// 5.4 The gate: one pinned camera over one world, four beats. Captions enter only when the camera
// is still; the world itself is the same <use> the static 2×2 panels show.
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { E, lineIn, lineOut, rig } from "./rig";

export function how() {
  const section = document.querySelector<HTMLElement>("#how");
  if (!section) return;
  const pin = section.querySelector<HTMLElement>(".how-pin")!;
  const stage = section.querySelector<HTMLElement>(".how-stage")!;
  const caps = [...section.querySelectorAll<HTMLElement>(".how-pin .how-cap")];
  const w = (s: string) => document.querySelectorAll(`#how-world ${s}`);
  const one = (s: string) => document.querySelector(`#how-world ${s}`)!;
  const { cam, apply, measure } = rig(stage);
  const W = () => stage.clientWidth; // one scene is one stage width

  // the first frame of each beat
  gsap.set(one("#how-sign"), { attr: { "stroke-dashoffset": 1 } });
  gsap.set(one("#how-wax"), { attr: { transform: "translate(410 372) scale(1.4)", opacity: 0 } });
  const blocks = [...w(".how-block")];
  const blockAt = blocks.map((b) => b.getAttribute("transform")!);
  blocks.forEach((b, i) => gsap.set(b, { attr: { transform: blockAt[i].replace(/(\d+(\.\d+)?)\)$/, (m, y) => `${Number(y) - 300})`), opacity: 0 } }));
  gsap.set(one("#how-arm"), { attr: { transform: "translate(296 268) rotate(0)" } });
  gsap.set(one("#how-fail"), { attr: { transform: "translate(-150 330)" } });
  gsap.set(one("#how-pass"), { attr: { transform: "translate(-150 330)" } });
  gsap.set(one("#how-receipt"), { attr: { transform: "translate(0 330)" } });
  gsap.set(w(".how-row"), { attr: { opacity: 0 } });
  gsap.set(w(".how-link"), { attr: { "stroke-dashoffset": 1 } });
  gsap.set(caps, { autoAlpha: 0 });

  const tl = gsap.timeline({ paused: true, defaults: { duration: 0.1 }, onUpdate: () => { apply(); captions(); } });
  // a: approve, sign, seal (slow push-in)
  tl.to(cam, { zoom: 1.03, duration: 0.18, ease: E.drift }, 0);
  tl.to(one("#how-sign"), { attr: { "stroke-dashoffset": 0 }, duration: 0.09, ease: "none" }, 0.03);
  tl.to(one("#how-wax"), { attr: { transform: "translate(410 372) scale(1)", opacity: 1 }, duration: 0.03, ease: E.outExpo }, 0.12);
  // b: truck to the blind pane; blocks are built behind it
  tl.to(cam, { x: () => W(), zoom: 1, duration: 0.12, ease: E.inOut }, 0.18);
  blocks.forEach((b, i) => tl.to(b, { attr: { transform: blockAt[i], opacity: 1 }, duration: 0.035, ease: E.outExpo }, 0.31 + i * 0.04));
  // c: truck to the gate; the diamond is bounced, the circle goes through
  tl.to(cam, { x: () => 2 * W(), duration: 0.1, ease: E.inOut }, 0.48);
  tl.to(one("#how-fail"), { attr: { transform: "translate(150 330)" }, duration: 0.05, ease: E.inOut }, 0.59);
  tl.to(one("#how-fail"), { attr: { transform: "translate(40 330)" }, duration: 0.03, ease: E.outExpo }, 0.64);
  tl.to(one("#how-pass"), { attr: { transform: "translate(150 330)" }, duration: 0.04, ease: E.inOut }, 0.67);
  tl.to(one("#how-arm"), { attr: { transform: "translate(296 268) rotate(-80)" }, duration: 0.025, ease: E.snap }, 0.71);
  tl.to(one("#how-pass"), { attr: { transform: "translate(470 330)" }, duration: 0.045, ease: E.inOut }, 0.735);
  // d: truck in close on the slot, then pull out while the receipt prints and the links draw
  tl.to(cam, { x: () => 3 * W(), zoom: 1.3, duration: 0.08, ease: E.inOut }, 0.78);
  tl.to(cam, { zoom: 1, duration: 0.1, ease: E.inOut }, 0.86);
  tl.to(one("#how-receipt"), { attr: { transform: "translate(0 0)" }, duration: 0.1, ease: "none" }, 0.86);
  tl.to(w(".how-row"), { attr: { opacity: 1 }, duration: 0.001, stagger: 0.016, ease: "none" }, 0.87);
  tl.to(w(".how-link"), { attr: { "stroke-dashoffset": 0 }, duration: 0.012, stagger: 0.008, ease: "none" }, 0.95);

  // which caption, if any: each enters when its beat's camera move has finished
  const windows: [number, number][] = [[0, 0.18], [0.3, 0.48], [0.58, 0.78], [0.96, 1.01]];
  let active = -1;
  function captions() {
    const p = tl.progress();
    const now = windows.findIndex(([a, b]) => p >= a && p < b);
    if (now === active) return;
    if (active >= 0) lineOut(caps[active]);
    if (now >= 0) lineIn(caps[now]);
    active = now;
  }

  ScrollTrigger.create({
    trigger: pin,
    start: "center center",
    end: "+=320%",
    pin: true,
    scrub: 0.8,
    animation: tl,
    invalidateOnRefresh: true,
    onRefreshInit: measure,
  });
  apply();
  captions();
}
