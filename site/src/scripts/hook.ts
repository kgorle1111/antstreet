// 5.1 The seal that cracks: plays once on load (~5.4 s), ends level and still. The text timings
// come from data/hook.json, which tests/test_site_facts.py lints against the reading floor.
import { gsap } from "gsap";
import hookData from "../data/hook.json";
import { E, FRAME, lineIn, nudge, rig } from "./rig";

const at = (id: string) => hookData.lines.find((l) => l.id === id)!;

export function hook() {
  const stage = document.querySelector<HTMLElement>(".hook-stage");
  if (!stage) return;
  const q = <T extends Element = SVGElement>(s: string) => stage.querySelector<T>(s)!;
  const world = q<HTMLElement>(".world");
  const sealLayer = q<HTMLElement>(".seal-layer");
  const seal = q("#hk-seal");
  const halves = stage.querySelectorAll(".hk-half");
  const crack = q(".hk-crack");
  const env = q<HTMLElement>(".env");
  const flap = q<HTMLElement>("#hk-flap");
  const card = q("#hk-card");
  const shape = q("#hk-shape");
  const xs = stage.querySelectorAll("#hk-x line");
  const pill = q("#hk-pill");
  const wax = q("#hk-wax");
  const caption = q<HTMLElement>('[data-hook="caption"]');
  const sub = document.querySelector('[data-hook="sub"]');
  const ctas = document.querySelector('[data-hook="ctas"]');
  const { cam, apply } = rig(stage);
  const b = hookData.beats;
  const s = (ms: number) => ms / 1000;

  // Frame 0 of 1A: the seal is the subject, in focus, whole; the envelope is not in the world yet.
  sealLayer.dataset.p = "1";
  gsap.set(sealLayer, { filter: "blur(0px) brightness(1)" });
  gsap.set(seal, { attr: { transform: "translate(320 240) scale(1.06)" } });
  gsap.set(halves[0], { attr: { transform: "translate(0 0) rotate(0)" } });
  gsap.set(halves[1], { attr: { transform: "translate(0 0) rotate(0)" } });
  gsap.set(crack, { attr: { "stroke-dashoffset": 1 } });
  gsap.set(env, { autoAlpha: 0 });
  gsap.set(flap, { rotateX: 0, zIndex: 3 });
  gsap.set(card, { attr: { transform: "translate(320 300)" } });
  gsap.set(shape, { attr: { rx: 32, transform: "rotate(0)", fill: "#e3a82e" } });
  gsap.set(xs, { attr: { "stroke-dashoffset": 1 } });
  gsap.set(pill, { autoAlpha: 0 });
  gsap.set(wax, { attr: { opacity: 1 } });
  gsap.set(".hk-wax-l, .hk-wax-r", { attr: { transform: "translate(0 0) rotate(0)" } });
  gsap.set(caption, { autoAlpha: 0 });
  apply();
  gsap.set(world, { visibility: "visible" });

  const tl = gsap.timeline({ onUpdate: apply, onComplete: () => { (window as any).__hookDone = true; } });
  // 1A: the seal lands, then a slow push-in.
  tl.to(seal, { attr: { transform: "translate(320 240) scale(1)" }, duration: 4 * FRAME, ease: E.outExpo }, s(b.land));
  tl.add(nudge(world), s(b.land));
  tl.to(cam, { zoom: 1.03, duration: s(b.cut - b.land) - 4 * FRAME, ease: E.drift }, s(b.land) + 4 * FRAME);

  // 1B: match cut to the wax seal (same centre, same on-screen diameter), pull-out, rack focus, tilt.
  tl.call(() => {
    sealLayer.dataset.p = "0.8";
    gsap.set(seal, { attr: { transform: "translate(95 110) scale(0.75)" } });
    gsap.set(env, { autoAlpha: 1 });
    cam.zoom = 1.45;
    apply();
  }, [], s(b.cut));
  tl.to(cam, { zoom: 1, duration: 1.0, ease: E.inOut }, s(b.cut));
  tl.to(sealLayer, { filter: "blur(10px) brightness(0.6)", duration: 0.5, ease: E.inOut }, s(b.cut));
  tl.add(lineIn(caption), s(at("caption").inMs));
  tl.to(cam, { roll: -3, duration: 1.5, ease: E.drift }, s(b.cut) + 1.0);

  // 1C: the wax breaks, the flap opens, the card rises and turns from circle to diamond, X, crack.
  const o = s(b.open);
  tl.to(caption, { autoAlpha: 0, duration: 3 * FRAME, ease: "none" }, o);
  tl.to(".hk-wax-l", { attr: { transform: "translate(-10 0) rotate(-10)" }, duration: 3 * FRAME, ease: E.snap }, o);
  tl.to(".hk-wax-r", { attr: { transform: "translate(10 0) rotate(10)" }, duration: 3 * FRAME, ease: E.snap }, o);
  tl.to(wax, { attr: { opacity: 0 }, duration: 0.15, ease: "none" }, o + 0.1);
  tl.to(flap, { rotateX: -180, duration: 0.27, ease: E.inOut }, o);
  tl.set(flap, { zIndex: 0 }, o + 0.135);
  tl.to(card, { attr: { transform: "translate(320 105)" }, duration: 0.23, ease: E.outExpo }, o + 0.27);
  tl.to(shape, { attr: { rx: 5, transform: "rotate(45)", fill: "#ff5a4f" }, duration: 0.17, ease: E.snap }, o + 0.33);
  tl.to(pill, { autoAlpha: 1, duration: 3 * FRAME, ease: "none" }, s(at("pill").inMs));
  tl.to(xs, { attr: { "stroke-dashoffset": 0 }, duration: 2 * FRAME, ease: "none", stagger: 2 * FRAME }, o + 0.4);
  const hit = o + 0.5;
  tl.to(cam, { zoom: 1.06, duration: 0.17, ease: E.outExpo }, hit);
  tl.add(nudge(world), hit);
  tl.to(crack, { attr: { "stroke-dashoffset": 0 }, duration: 4 * FRAME, ease: "none" }, hit);
  tl.to(halves[0], { attr: { transform: "translate(-14 4) rotate(-6)" }, duration: 4 * FRAME, ease: E.snap }, hit);
  tl.to(halves[1], { attr: { transform: "translate(14 -4) rotate(6)" }, duration: 4 * FRAME, ease: E.snap }, hit);

  // Settle: level and still; the sub and the calls to action enter as whole lines.
  const st = s(b.settle);
  tl.to(cam, { roll: 0, zoom: 1, duration: 0.6, ease: E.inOut }, st);
  if (sub) tl.add(lineIn(sub), s(at("sub").inMs));
  if (ctas) tl.add(lineIn(ctas), s(at("sub").inMs) + 0.3);
  return tl;
}
