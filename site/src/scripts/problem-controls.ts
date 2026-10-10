// The 77-cell explorer without motion: the strict toggle, the inspector and arrow-key movement.
import { AUDIT_CASES } from "../data/links";
import { FRAME } from "./rig";

type Cell = { cell: number; run: string; task: string; rep: number; false_pass: boolean; strict_drop: string | null; case: number | null; hidden_failed: string[]; idea: string | null };
const COLS = 11;

const esc = (t: string) => t.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

export function problemControls(section: HTMLElement) {
  const cells = [...section.querySelectorAll<HTMLButtonElement>(".cell")];
  const data: Cell[] = JSON.parse(section.querySelector("#grid-data")!.textContent!);
  const inspector = section.querySelector<HTMLElement>("#inspector")!;
  const toggle = section.querySelector<HTMLButtonElement>(".strict-toggle")!;
  const note = section.querySelector<HTMLElement>(".strict-note")!;

  // strict count: 13 cells go hollow, 2 frames apart; the "16 of 77" span is highlighted
  const drops = cells.filter((c) => c.dataset.drop);
  drops.forEach((c, i) => c.style.setProperty("--d", `${Math.round(i * 2 * FRAME * 1000)}ms`));
  toggle.addEventListener("click", () => {
    const on = toggle.getAttribute("aria-pressed") !== "true";
    toggle.setAttribute("aria-pressed", String(on));
    section.classList.toggle("strict-on", on);
    note.hidden = !on;
  });

  // inspector: one panel the HUD owns; a cell is selected on focus, hover or click
  const show = (btn: HTMLButtonElement) => {
    const c = data[Number(btn.dataset.cell)];
    cells.forEach((x) => x.removeAttribute("aria-current"));
    btn.setAttribute("aria-current", "true");
    const head = `<p class="ins-title">${esc(c.task)} <span class="mute" data-literal>· run ${esc(c.run)} · rep ${c.rep}</span></p>`;
    inspector.innerHTML = c.false_pass
      ? `${head}<p>Its own checks passed. Hidden check failed: <code>${c.hidden_failed.map(esc).join("</code>, <code>")}</code>${c.strict_drop ? " (the strict count drops it)" : ""}.</p>` +
        `<p>The task says: <q data-literal>${esc((c.idea ?? "").replace(/^"|"$/g, ""))}</q></p>` +
        `<p><a href="${AUDIT_CASES}" data-literal>Audit case ${c.case}, read against the task text</a></p>`
      : `${head}<p>Its own checks passed, and so did every hidden check.</p>`;
  };
  cells.forEach((btn, i) => {
    btn.tabIndex = i === 0 ? 0 : -1;
    btn.addEventListener("focus", () => show(btn));
    btn.addEventListener("mouseenter", () => show(btn));
    btn.addEventListener("click", () => show(btn));
    btn.addEventListener("keydown", (e) => {
      const step: Record<string, number> = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: COLS, ArrowUp: -COLS, Home: -i, End: cells.length - 1 - i };
      if (!(e.key in step)) return;
      e.preventDefault();
      const next = cells[Math.min(cells.length - 1, Math.max(0, i + step[e.key]))];
      btn.tabIndex = -1;
      next.tabIndex = 0;
      next.focus();
    });
  });
}
