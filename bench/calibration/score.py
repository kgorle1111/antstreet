"""Score the calibration cases by hand, one criterion at a time, with the rubric on screen.

    uv run python bench/calibration/score.py stories
    uv run python bench/calibration/score.py usage [--redo c07]

Your scores are written into the case file after every finished case, so you can quit with `q`
and carry on later. It makes no model call. Nothing in the file changes except the scores.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from boss.roles.judge import ANCHOR_POINTS, MAX_SCORE, MIN_SCORE, Rubric, load_rubric

HERE = Path(__file__).resolve().parent


def rubric_card(rubric: Rubric) -> str:
    lines = [f"Rubric {rubric.id} v{rubric.version}: {rubric.title}"]
    for c in rubric.criteria:
        lines += ["", f"{c.id}: {c.question}"]
        lines += [f"  {p}: {t}" for p, t in zip(ANCHOR_POINTS, c.anchors, strict=True)]
        lines.append("  (2 sits between 1 and 3, 4 between 3 and 5)")
    return "\n".join(lines)


def save(path: Path, cases: list[dict]) -> None:
    text = "\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)  # a crash mid-write must not lose earlier labels


def score_file(
    path: Path,
    *,
    redo: str | None = None,
    ask: Callable[[str], str] = input,
    out: Callable[[str], None] = print,
) -> tuple[int, int]:
    """Prompt for every unscored case; returns (scored, total). EOF or `q` stops and keeps what
    is saved."""
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    rubric = load_rubric(cases[0]["rubric"])
    if redo is not None and redo not in {c["id"] for c in cases}:
        raise SystemExit(f"no case {redo!r} in {path.name}")
    # the old scores of a redone case stay in the file until the new ones are complete
    todo = [c for c in cases if c["id"] == redo or any(v is None for v in c["scores"].values())]
    for n, case in enumerate(todo, start=1):
        out("\n" + "=" * 78)
        out(f"Case {case['id']}  (number {n} of {len(todo)} to score now)")
        out("\n--- judged against ---\n" + case["context"])
        out("\n--- the artifact ---\n" + case["artifact"])
        out("\n" + rubric_card(rubric) + "\n")
        scores: dict[str, int] = {}
        for c in rubric.criteria:
            while c.id not in scores:
                try:
                    answer = ask(f"{c.id} ({MIN_SCORE}-{MAX_SCORE}, q to quit): ").strip().lower()
                except EOFError:
                    answer = "q"
                if answer == "q":
                    save(path, cases)
                    return _count(cases), len(cases)
                if answer.isdigit() and MIN_SCORE <= int(answer) <= MAX_SCORE:
                    scores[c.id] = int(answer)
                else:
                    out(f"  type a whole number from {MIN_SCORE} to {MAX_SCORE}, or q")
        case["scores"] = scores
        save(path, cases)
    save(path, cases)
    return _count(cases), len(cases)


def _count(cases: list[dict]) -> int:
    return sum(all(v is not None for v in c["scores"].values()) for c in cases)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score the calibration cases by hand.")
    parser.add_argument("rubric", help="stories or usage")
    parser.add_argument("--redo", metavar="CASE_ID", help="clear one case's scores and ask again")
    args = parser.parse_args(argv)
    path = HERE / args.rubric / "cases.jsonl"
    if not path.is_file():
        print(f"error: no case file {path}", file=sys.stderr)
        return 1
    scored, total = score_file(path, redo=args.redo)
    print(f"\n{scored} of {total} cases scored in {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
