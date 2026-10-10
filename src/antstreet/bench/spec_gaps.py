"""Eval of the spec-gap questions (`antstreet.questions`, prompt `spec_gaps_v1.md`).

The cases (`bench/spec_gaps/cases.json`) are rules a benchmark idea states that the boss's checks
missed in a false-pass cell. A case is surfaced when one question matches one of its patterns.
Reported: the fraction surfaced (recall), and the fraction of cases whose questions are at most
five and all yes/no. The match is lexical, so it is generous: read the questions of a live run
before trusting a number.

  python -m antstreet.bench.spec_gaps estimate              # tokens and dollars; no call
  python -m antstreet.bench.spec_gaps score --questions F   # score saved questions; no call
  python -m antstreet.bench.spec_gaps live --yes-spend --out F   # real calls: spends money

`live` drafts checks for each idea as `boss fund` does (one call), then asks for the questions
(a second call), and saves the questions with the measured cost.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from antstreet import boss, questions
from antstreet.worker import CLI, EXECUTABLE_VAR, worker_env

ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "bench" / "spec_gaps" / "cases.json"
TASKS = ROOT / "bench" / "tasks"
CHARS_PER_TOKEN = 4  # a rough English/code ratio; the live run prints the measured cost
# Output per call, guessed from live drafts (3-8 checks of a few lines each) and the questions'
# shape (5 questions, two short checks each). The live run prints the measured figure.
DRAFT_OUT_TOKENS = 2_000
QUESTIONS_OUT_TOKENS = 2_500
CLI_OVERHEAD_TOKENS = 1_500  # the claude CLI's own framing per call, a guess
# Claude Haiku 4.5, first-party API, USD per million tokens (claude-api skill table, 2026-10-06).
PRICE_IN, PRICE_OUT = 1.00, 5.00


@dataclass(frozen=True, slots=True)
class Case:
    id: str
    task: str
    rule: str
    source: str
    match: tuple[str, ...]

    def idea(self, tasks: Path = TASKS) -> str:
        return (tasks / self.task / "idea.md").read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class Scored:
    case: str
    surfaced: bool
    count: int
    yes_no: bool  # every question is a yes/no question

    @property
    def well_formed(self) -> bool:
        return self.count <= questions.MAX_QUESTIONS and self.yes_no


def load_cases(path: Path = CASES) -> list[Case]:
    raw = json.loads(path.read_text(encoding="utf-8"))["cases"]
    return [Case(c["id"], c["task"], c["rule"], c["source"], tuple(c["match"])) for c in raw]


def score(case: Case, asked: Sequence[str]) -> Scored:
    surfaced = any(re.search(p, q, re.IGNORECASE) for p in case.match for q in asked)
    return Scored(case.id, surfaced, len(asked), all(questions.is_yes_no(q) for q in asked))


def report(scored: Sequence[Scored]) -> str:
    n = len(scored)
    hit = sum(s.surfaced for s in scored)
    formed = sum(s.well_formed for s in scored)
    lines = [f"{'case':28} surfaced  questions  yes/no"]
    lines += [f"{s.case:28} {'yes' if s.surfaced else 'no':8}  {s.count:9}  {s.yes_no}"
              for s in scored]  # fmt: skip
    lines.append(f"Recall: {hit} of {n} known-missing rules surfaced ({hit / n:.0%}).")
    lines.append(f"Well formed (at most {questions.MAX_QUESTIONS}, all yes/no): {formed} of {n}.")
    return "\n".join(lines)


def estimate(cases: Sequence[Case], tasks: Path = TASKS) -> tuple[int, int, float]:
    """Input tokens, output tokens and dollars for one live run over `cases`, from the prompt and
    idea sizes and the output guesses above."""
    draft_prompt = len(boss.load_prompt(boss.TERM_SHEET_PROMPT))
    gaps_prompt = len(boss.load_prompt(questions.PROMPT))
    tokens_in = tokens_out = 0
    for case in cases:
        idea = len(case.idea(tasks))
        drafted = DRAFT_OUT_TOKENS * CHARS_PER_TOKEN  # the questions call reads the drafted checks
        tokens_in += (draft_prompt + idea) // CHARS_PER_TOKEN + CLI_OVERHEAD_TOKENS
        tokens_in += (gaps_prompt + idea + drafted) // CHARS_PER_TOKEN + CLI_OVERHEAD_TOKENS
        tokens_out += DRAFT_OUT_TOKENS + QUESTIONS_OUT_TOKENS
    usd = (tokens_in * PRICE_IN + tokens_out * PRICE_OUT) / 1_000_000
    return tokens_in, tokens_out, usd


def live(
    cases: Sequence[Case],
    *,
    env: Mapping[str, str],
    model: str = boss.DEFAULT_MODEL,
    executable: str = CLI,
    tasks: Path = TASKS,
) -> tuple[dict[str, list[str]], int]:
    """Each case's questions and the micro-dollars spent. A failed call leaves that case with no
    questions (it scores as missed), and its spend is still counted when the CLI reported it."""
    found: dict[str, list[str]] = {}
    spent = 0
    for case in cases:
        with tempfile.TemporaryDirectory(prefix="spec_gaps_") as tmp:
            checks = Path(tmp) / "checks"
            try:
                draft = boss.draft_term_sheet(
                    case.idea(tasks), 1_000_000, checks, env=env, model=model,
                    executable=executable,
                )  # fmt: skip
                spent += draft.usage.cost_micros or 0
                asked, usage = questions.draft(
                    draft.sheet, checks, env=env, model=model, executable=executable
                )
                spent += usage.cost_micros or 0
            except boss.BossError as exc:
                spent += exc.usage.cost_micros or 0
                print(f"{case.id}: {exc}", file=sys.stderr)
                asked = []
        found[case.id] = [q.text for q in asked]
    return found, spent


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m antstreet.bench.spec_gaps")
    parser.add_argument("--cases", type=Path, default=CASES)
    steps = parser.add_subparsers(dest="step", required=True)
    steps.add_parser("estimate", help="tokens and dollars of one live run; no call")
    scored = steps.add_parser("score", help="score saved questions; no call")
    scored.add_argument("--questions", type=Path, required=True, help="JSON: case id -> list")
    run = steps.add_parser("live", help="real calls: draft checks, then ask; spends money")
    run.add_argument("--yes-spend", action="store_true", help="required: this spends money")
    run.add_argument("--out", type=Path, required=True, help="where to save the questions")
    run.add_argument("--model", default=boss.DEFAULT_MODEL)
    args = parser.parse_args(argv)
    cases = load_cases(args.cases)
    tokens_in, tokens_out, usd = estimate(cases)
    print(
        f"Estimate for {len(cases)} cases, 2 calls each: {tokens_in:,} tokens in, "
        f"{tokens_out:,} out, about ${usd:.2f} at Haiku 4.5 prices (${PRICE_IN:.2f}/"
        f"${PRICE_OUT:.2f} per million)."
    )
    if args.step == "estimate":
        return 0
    if args.step == "score":
        saved = json.loads(args.questions.read_text(encoding="utf-8"))
        print(report([score(c, saved.get(c.id, [])) for c in cases]))
        return 0
    if not args.yes_spend:
        print("Not run: `live` makes real model calls. Add --yes-spend to run it.")
        return 2
    environ = dict(environ if environ is not None else os.environ)
    found, spent = live(
        cases,
        env=worker_env(environ),
        model=args.model,
        executable=environ.get(EXECUTABLE_VAR, CLI),
    )
    args.out.write_text(json.dumps(found, indent=1, ensure_ascii=False), encoding="utf-8")
    print(report([score(c, found.get(c.id, [])) for c in cases]))
    print(f"Spent ${spent / 1_000_000:.4f} (measured). Questions saved to {args.out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
