// The camera rig and the easing set from posts/marketing/video (DIRECTORS-TREATMENT §2), as code.
// One camera per stage; every [data-p] layer gets translate(-x·p, -y·p) scale(1 + (zoom-1)·p)
// rotate(roll) about the stage centre. The HUD is never a layer, so it never moves.
import { gsap } from "gsap";
import { CustomEase } from "gsap/CustomEase";

gsap.registerPlugin(CustomEase);

export const E = {
  outExpo: CustomEase.create("outExpo", ".16,1,.3,1"),
  inOut: CustomEase.create("inOut", ".65,0,.35,1"),
  drift: CustomEase.create("drift", ".45,0,.55,1"),
  snap: CustomEase.create("snap", ".7,0,.2,1"),
  whipIn: CustomEase.create("whipIn", ".55,0,1,.45"),
  whipOut: CustomEase.create("whipOut", "0,.55,.45,1"),
  inExpo: CustomEase.create("inExpo", ".7,0,.84,0"),
  caption: CustomEase.create("caption", ".2,.8,.2,1"),
};

export const FRAME = 1 / 30; // seconds

export type Cam = { x: number; y: number; zoom: number; roll: number };

export function rig(stage: HTMLElement) {
  const layers = [...stage.querySelectorAll<HTMLElement>("[data-p]")];
  const cam: Cam = { x: 0, y: 0, zoom: 1, roll: 0 };
  let centres: [number, number][] = [];
  const measure = () => {
    const s = stage.getBoundingClientRect();
    // the stage centre in each layer's own box (a layer may be offset or wider than the stage)
    centres = layers.map((l) => [s.width / 2 - l.offsetLeft, s.height / 2 - l.offsetTop]);
  };
  const apply = () => {
    layers.forEach((l, i) => {
      const p = Number(l.dataset.p);
      const [cx, cy] = centres[i] ?? [0, 0];
      l.style.transformOrigin = `${cx + cam.x * p}px ${cy + cam.y * p}px`;
      l.style.transform = `translate(${-cam.x * p}px, ${-cam.y * p}px) scale(${1 + (cam.zoom - 1) * p}) rotate(${cam.roll}deg)`;
    });
  };
  measure();
  addEventListener("resize", () => { measure(); apply(); });
  return { cam, apply, measure };
}

/** One damped vertical bounce over 4 frames: physical impacts only, at most 3 per page. */
export function nudge(target: Element) {
  return gsap.timeline().set(target, { y: 6 }).set(target, { y: 3 }, FRAME).set(target, { y: -1 }, 2 * FRAME).set(target, { y: 0 }, 3 * FRAME);
}

/** A HUD line enters whole: 5 frames, translateY 16 → 0, caption easing. */
export function lineIn(target: gsap.TweenTarget, at?: number) {
  return gsap.fromTo(target, { autoAlpha: 0, y: 16 }, { autoAlpha: 1, y: 0, duration: 5 * FRAME, ease: E.caption, delay: at ?? 0 });
}
export function lineOut(target: gsap.TweenTarget) {
  return gsap.to(target, { autoAlpha: 0, duration: 3 * FRAME, ease: "none" });
}
