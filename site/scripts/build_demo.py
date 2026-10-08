"""Write docs/assets/demo.svg (and its byte-identical copy in site/public/assets/): an animated
replay of a real `antstreet audit` run with the test suite's fake model.

The lines come from posts/marketing/audit-demo-capture-2026-10-08.txt, a real run; paths and
environment lines are trimmed. tests/test_docs_showcase.py re-runs the audit and checks that every
output line shown is one a real run prints (run id, hashes and timings normalised).

    python3 -I site/scripts/build_demo.py
"""

import html
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "assets" / "demo.svg"
COPY = ROOT / "site" / "public" / "assets" / "demo.svg"
RUN = "20261008T220910Z-cf301f"
LABEL = "replay of a test-suite run (fake model), not a live recording · output trimmed"

# (text, kind): "$" typed command, "#" narration, "" output, "v" verdict, "p" a pass, "b" blank
LINES = [
    ("$ uv run antstreet audit plan --request request.txt", "$"),
    ("Running the checks on the base...", ""),
    ("Check c01 [t1] runs of symbols become one hyphen", ""),
    ("Check c02 [t1] hyphens are trimmed at both ends", ""),
    ("Check c03 [t1] a plain word is unchanged", ""),
    ("Check c04 [t1] needs a library", ""),
    ("  c01: fails on the base: counted", ""),
    ("  c02: fails on the base: counted", ""),
    ("  c03: passes on the base: shown, not counted", ""),
    ("  c04: cannot run here: not counted (needs module 'nosuchlib_zq')", ""),
    ("2 of 4 checks will be counted.", ""),
    (f"Sealed audit run {RUN}: 2 of 4 checks fail on the base and will be counted.", ""),
    ("", "b"),
    ("# the agent works on its own branch, then runs its own tests:", "#"),
    ("$ python -m pytest -q tests", "$"),
    ("2 passed in 0.00s", "p"),
    ("", "b"),
    ("$ uv run antstreet audit check --claim done", "$"),
    (f"Run {RUN}: head b9cde65e3eef on base 450109a66507", ""),
    ("Verdict: REFUTED (claim: done, pre-registered)", "v"),
    ("Counted checks (failing on the base): 2; failing on the head: 2", ""),
    ("  c01 failed: runs of symbols become one hyphen", "v"),
    ("  c02 failed: hyphens are trimmed at both ends", "v"),
    ("", "b"),
    ("$ uv run antstreet audit report", "$"),
    ("  b9cde65e3eef [(no label)] pre-registered: refuted, failed c01, c02 of 2 counted", ""),
    ("A floor, not a measurement of the agent: an unrefuted claim is not a correct one.", ""),
]
W, TOP, LH, CH = 960, 62, 20, 9.0  # width, first baseline, line height, mono advance at 15px
TOTAL = 22.0  # seconds; plays once and holds the last frame


def main() -> None:
    style = [
        "text{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace;"
        "font-size:15px;white-space:pre;fill:#c9d1d9}",
        ".m{fill:#8b949e}.c{fill:#e6edf3}.d{fill:#ffc61a}.v{fill:#ff7b72;font-weight:700}"
        ".p{fill:#3fb950}.n{fill:#8b949e;font-style:italic}.lab{font-size:13px;fill:#8b949e}",
    ]
    body = []
    t = 0.4
    for i, (text, kind) in enumerate(LINES):
        y = TOP + i * LH
        if kind == "b":
            t += 0.5
            continue
        cls = {"$": "c", "#": "n", "v": "v", "p": "p", "": "m"}[kind]
        if text.startswith(("Verdict", "Sealed", "2 of 4", "A floor")):
            cls = "c" if kind == "" else cls
        esc = html.escape(text, quote=False)
        if kind == "$":
            chars = len(text)
            dur = round(min(1.6, 0.035 * chars), 2)
            width = round(chars * CH + 4, 1)
            style.append(
                f"#k{i}{{animation:w{i} {dur}s steps({chars},end) {t:.2f}s both}}"
                f"@keyframes w{i}{{from{{width:0}}to{{width:{width}px}}}}"
            )
            body.append(
                f'<clipPath id="q{i}"><rect id="k{i}" x="20" y="{y - 15}" height="{LH}" '
                f'width="{width}"/></clipPath>'
                f'<text x="24" y="{y}" class="{cls}" clip-path="url(#q{i})">'
                f'<tspan class="d">$</tspan>{html.escape(text[1:], quote=False)}</text>'
            )
            t += dur + 0.5
        else:
            style.append(f".l{i}{{animation:a 0.01s steps(1,end) {t:.2f}s both}}")
            body.append(f'<text x="24" y="{y}" class="{cls} l{i}">{esc}</text>')
            t += 0.42 if kind != "v" else 0.6
    assert t < TOTAL, t
    style.append("@keyframes a{from{opacity:0}to{opacity:1}}")
    style.append("@media (prefers-reduced-motion:reduce){*{animation:none!important}}")
    h = TOP + len(LINES) * LH + 10
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="{W}" height="{h}" '
        'role="img" aria-label="Replay of an antstreet audit run with a fake model: audit plan '
        "seals 2 of 4 checks, the agent's own tests pass, audit check says REFUTED with c01 and "
        'c02 failed, and audit report adds the floor sentence">'
        f"<style>{''.join(style)}</style>"
        f'<rect width="{W}" height="{h}" rx="12" fill="#0d1117"/>'
        f'<rect width="{W}" height="34" rx="12" fill="#161b22"/>'
        f'<rect y="22" width="{W}" height="12" fill="#161b22"/>'
        '<circle cx="20" cy="17" r="6" fill="#ff5f57"/>'
        '<circle cx="40" cy="17" r="6" fill="#febc2e"/>'
        '<circle cx="60" cy="17" r="6" fill="#28c840"/>'
        f'<text x="{W / 2}" y="22" text-anchor="middle" class="lab">{html.escape(LABEL)}</text>'
        + "".join(body)
        + "</svg>\n"
    )
    OUT.write_text(svg)
    shutil.copyfile(OUT, COPY)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(svg.encode())} bytes), ends at {t:.1f}s")


if __name__ == "__main__":
    main()
