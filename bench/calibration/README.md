# Calibration set for the judge

The judge scores two things: the user stories (`stories`) and the usage note `USAGE.md`
(`usage`). Its scores are advisory until it agrees with you. This folder holds 20 cases per
rubric for you to score by hand. Then `calibrate` runs the judge on the same cases and compares.

## What a case is

One line of `stories/cases.jsonl` or `usage/cases.jsonl`. It has:

- `artifact`: the thing to score (the stories, or the whole `USAGE.md`).
- `context`: what it is judged against (the idea).
- `scores`: one score per criterion, 1 to 5. These start empty. They are yours to fill in.

The judge sees only the context and the artifact. Score from the same two things. For `usage`,
"the code shown" means the demo script and its printed output inside `USAGE.md`.

## What you do (about 15 minutes per rubric)

Run these from the repository root. The scorer shows each case with the rubric text under it,
asks for one score per criterion, and saves after every case. Type `q` to stop and carry on later.

    uv run python bench/calibration/score.py stories
    uv run python bench/calibration/score.py usage

Rules for scoring:

1. Use the rubric's 1, 3 and 5 descriptions. A 2 sits between 1 and 3, a 4 between 3 and 5.
2. Score each criterion on its own. A case can be a 5 on one and a 1 on another.
3. Score what is written, not what you expect. Some cases are confident but wrong, padded, or
   missing something on purpose.
4. Use the whole scale. If you give the same score to everything, agreement cannot be measured.
5. Score all 20 cases. The bar needs 20 scored cases, so skipping one means it cannot pass.
6. Do not open `manifest.json` until you have finished. It says what each case was built to test.

To change a score you gave: `uv run python bench/calibration/score.py stories --redo c07`.
You can also edit the number in the file by hand. Do not edit the file after you run `calibrate`.

## Then run the judge

This spends money. It makes 20 calls per rubric. Each call is capped at $0.15, so at most $3 per
rubric. First look at the calls and the ceiling, with no calls made:

    uv run python -m antstreet.roles.judge calibrate --cases bench/calibration/stories/cases.jsonl --out <project>/.boss/calibration/stories.json --dry-run

Then run it for real: the same command without `--dry-run`. Do the same for `usage`.

- `<project>` is the folder you run `boss fund` in. The pipeline looks for
  `<project>/.boss/calibration/<rubric_id>.json`, so create that folder first with
  `mkdir -p <project>/.boss/calibration`. `--out` must not already exist.
- `--model` defaults to `haiku`. Use the model the pipeline judges with. A calibration only
  applies to the same rubric version, model, prompt and skills it was run with.
- `python -m antstreet.roles.judge show <file>` prints the result again without any call.

## What counts as agreeing

`meets_bar` checks the overall figures. All three must hold:

- at least 20 scored cases (a failed judge call is not a scored case);
- quadratic-weighted kappa of at least 0.6;
- at least 80% of all score pairs within one point of yours.

A failed judge call counts against agreement. It is never dropped. These numbers are a starting
point, not a claim about the right values.

## If the judge misses the bar

Nothing breaks. The judge stays advisory. Every judgement is labelled `uncalibrated`, and
`require_calibrated` refuses to let any code act on it. The report still shows the score.

`show` lists which criteria are below the bar. To improve it, change the rubric wording or the
judge prompt, then calibrate again to a new `--out`. A rubric edit that changes a criterion needs
a version bump. It also changes the criteria in these cases, so `tests/test_calibration_set.py`
fails until the cases are updated, and you score again.

## Where the cases came from

All 40 artifacts were written by hand (by Claude), not saved from real runs. The benchmark's
saved runs hold no `stories.json` and no `USAGE.md`. What is real: every context is a benchmark
task idea (`bench/tasks/*/idea.md`), and every `USAGE.md` demo and its output was run against
the task's reference module. A judge calibrated on these may not agree the same way on real
artifacts. When real runs produce stories and usage notes, add some here and score them too.
