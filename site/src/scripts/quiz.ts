// 5.3 "Same number?": either answer reveals the reply, then one beat per "Next". With reduced
// motion every card appears at once, stacked. The one whip-pan on the page lives here.
import { gsap } from "gsap";
import { E, FRAME, lineIn, rig } from "./rig";

const ORDER = ["answer", "task", "code", "hidden", "data"] as const;

export function quiz(motion: boolean) {
  const section = document.querySelector<HTMLElement>("#quiz");
  if (!section) return;
  const beats = Object.fromEntries(ORDER.map((id) => [id, section.querySelector<HTMLElement>(`[data-beat="${id}"]`)!]));
  const answers = [...section.querySelectorAll<HTMLButtonElement>(".quiz-answer")];
  const next = section.querySelector<HTMLButtonElement>(".quiz-next")!;
  const stage = section.querySelector<HTMLElement>(".quiz-stage")!;
  const world = stage.querySelector<HTMLElement>(".world")!;
  const { cam, apply } = rig(stage);
  let step = -1;

  const reveal = (id: (typeof ORDER)[number]) => {
    const el = beats[id];
    el.classList.add("shown");
    return el;
  };
  const focusBeat = (el: HTMLElement) => {
    const target = el.querySelector<HTMLElement>(".beat-h") ?? el;
    if (!target.hasAttribute("tabindex")) target.tabIndex = -1;
    target.focus({ preventScroll: true });
    el.scrollIntoView({ block: "nearest", behavior: motion ? "smooth" : "auto" });
  };

  const run: Record<string, () => void> = {
    answer() {
      const el = reveal("answer");
      if (motion) {
        // dolly: ١٢٣ moves to the centre, 123 leaves frame left
        const b = section.querySelector<HTMLElement>(".num-b")!;
        gsap.to(cam, { x: b.offsetLeft + b.offsetWidth / 2 - stage.clientWidth / 2, duration: 20 * FRAME, ease: E.inOut, onUpdate: apply });
        gsap.to(section.querySelector(".num-a"), { autoAlpha: 0, duration: 12 * FRAME, ease: "none" });
        gsap.to(section.querySelector(".eq"), { opacity: 1, duration: 5 * FRAME, ease: E.caption, delay: 20 * FRAME });
        lineIn(el, 20 * FRAME);
      }
      focusBeat(el);
    },
    task() {
      const el = reveal("task");
      if (motion) gsap.from(el, { y: -24, autoAlpha: 0, duration: 0.4, ease: E.outExpo });
      focusBeat(el);
    },
    code() {
      const el = reveal("code");
      if (motion) {
        const typed = el.querySelector(".typed")!;
        const chars = typed.textContent!.length; // ≤ 20 characters: terminal texture only
        const tl = gsap.timeline();
        tl.from(el, { y: 24, autoAlpha: 0, duration: 0.4, ease: E.outExpo });
        tl.fromTo(typed, { clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0% 0 0)", duration: chars * 2 * FRAME, ease: `steps(${chars})` });
        tl.from(el.querySelectorAll(".arrow, .result"), { autoAlpha: 0, duration: 3 * FRAME, ease: "none" }, "+=0.5");
        tl.from(el.querySelectorAll(".caveat, .verdict"), { autoAlpha: 0, y: 16, duration: 5 * FRAME, ease: E.caption }, "+=0.2");
      }
      focusBeat(el);
    },
    hidden() {
      const el = reveal("hidden");
      if (motion) {
        // the one whip-pan: out, cut, in; directional blur only along x
        const blur = document.querySelector("#whipblur feGaussianBlur");
        const w = stage.clientWidth;
        const b = { v: 0 };
        const setBlur = () => blur?.setAttribute("stdDeviation", `${b.v} 0`);
        world.style.filter = "url(#whipblur)";
        const tl = gsap.timeline({ onComplete: () => { world.style.filter = ""; } });
        tl.to(world, { x: -0.6 * w, duration: 4 * FRAME, ease: E.whipIn });
        tl.to(b, { v: 24, duration: 4 * FRAME, ease: E.whipIn, onUpdate: setBlur }, 0);
        tl.add(() => {
          gsap.set(section.querySelector(".scene-digits"), { autoAlpha: 0 });
          gsap.set(section.querySelector(".scene-hidden"), { autoAlpha: 1 });
          cam.x = 0;
          apply();
        });
        tl.fromTo(world, { x: 0.6 * w }, { x: 0, duration: 4 * FRAME, ease: E.whipOut });
        tl.to(b, { v: 0, duration: 4 * FRAME, ease: E.whipOut, onUpdate: setBlur }, "<");
        tl.to(cam, { roll: -3, duration: 0.8, ease: E.drift, onUpdate: apply });
        tl.from(el, { y: 24, autoAlpha: 0, duration: 0.4, ease: E.outExpo }, 8 * FRAME);
      } else {
        gsap.set(section.querySelector(".scene-digits"), { autoAlpha: 0 });
        gsap.set(section.querySelector(".scene-hidden"), { autoAlpha: 1 });
      }
      focusBeat(el);
    },
    data() {
      const el = reveal("data");
      if (motion) {
        // level first, then the data card arrives on a still frame
        const tl = gsap.timeline();
        tl.to(cam, { roll: 0, duration: 0.5, ease: E.inOut, onUpdate: apply });
        tl.from(el, { autoAlpha: 0, y: 16, duration: 5 * FRAME, ease: E.caption });
      }
      focusBeat(el);
    },
  };

  const advance = () => {
    step += 1;
    run[ORDER[step]]();
    next.hidden = step >= ORDER.length - 1;
  };
  answers.forEach((a) =>
    a.addEventListener("click", () => {
      answers.forEach((x) => x.setAttribute("aria-pressed", String(x === a)));
      if (step >= 0) return;
      if (!motion) {
        // reduced motion: every card at once, stacked, nothing moves
        ORDER.forEach((id) => reveal(id));
        gsap.set(section.querySelector(".eq"), { opacity: 1 });
        step = ORDER.length - 1;
        focusBeat(beats.answer);
        return;
      }
      advance();
    }),
  );
  next.addEventListener("click", advance);
}
