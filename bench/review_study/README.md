# Review study: planted checks

Does an investor reviewing a boss draft catch a check that is wrong? The study answers that by
planting known-bad checks into real archived drafts and recording what reviewers approve. This
folder holds its method; `bench/METHOD.md` stays about the firm-versus-single-agent benchmark.

## Harness core (`antstreet.bench.plants`)

`materialize(source_run_dir, task_dir, out_root, seed)` copies one archived draft's
`term_sheet.json` and `checks/` (never the ledger, logs or an investor key) into
`<out_root>/sessions/<sid>/proj/.boss/runs/<run id>/`, and writes the answer key to
`<out_root>/keys/<sid>.json`, mode 0600, outside the session. One `random.Random(seed)` draws k in
{0, 1, 2} plant positions, their kinds and the kinds' choices, so a seed reproduces a session byte
for byte. Planted checks keep the draft's ids and file names; a kind that writes "plant" into a
file is refused. Drafts are model output: files are read size-capped (`audit.MAX_PARSE_BYTES`) with
symlinks refused, the sheet is parsed by `TermSheet.from_json` and validated structurally on the
copy (`termsheet.structural_problems`, which parses and never runs a check), and the draft's idea
must equal the task's `idea.md`. Every file in the source run folder and its `checks/` is hashed
before and after; a change is an error and no session is kept. An `out_root` that is missing, a
symlink, inside any git checkout, or overlapping the source is refused. The registered kinds and
their oracles are below.

## Plant kinds and their oracles (`antstreet.bench.plant_kinds`)

Three kinds are made by machine; the hand-written ones of the design (contradicts_idea,
over_specified_literal, impl_detail) come later. A kind rewrites one check file: it parses it with
`ast`, picks a node with the seed's rng, and splices only the replacement in at that node's byte
offsets, so comments, quoting and spacing stay the draft's own and a planted file does not look
re-formatted beside its neighbours. A planted check is never imported or run in-process: every
oracle runs it through the sandboxed gate (`gate.run_gate`), with the repo's timeouts, through the
code that already wraps it.

| kind | what changes | oracle (must hold, or the plant is not used) |
| --- | --- | --- |
| `wrong_value` | the literal on the right of one `assert <expr> == <literal>`: an int or float moves by 1, a str gets one digit (or, with no digit, one letter) changed, in the draft's own quotes | the reference solution passes the original and fails the planted check (`bench/score.py` `count_wrong_checks`) |
| `vacuous` | each test function keeps its imports and asserts only that the imported names exist (`assert callable(name)`) | the planted check still fails on an empty workspace, so approval's T08 run (`termsheet.empty_checks_problems`) does not catch it; it passes on a stub product that defines the imported names with no logic, which the original fails |
| `under_specified` | one assert alone in a block that keeps another statement, or one of two or more test functions, is dropped | the reference still passes, and a mutant under `bench/tasks/<id>/mutants` that the original killed survives the planted check (`bench/score.py` `score_draft`, one check at a time) |

"Prefer an edge-case assert" is the oracle's job, not a guess: a drop is kept only if it lets a
known-wrong implementation through. `plants.plant_one` draws up to `MAX_ATTEMPTS` (12) plants for a
check from an rng seeded once from the session's rng, so the number of draws one plant needs never
shifts the next plant's choices; a draw seen before is not judged again. When none holds, or the
draft's own check leaves nothing to show (no literal compared, the reference already fails it, it
kills no mutant), the check stays as drafted and the key records the plant as `inapplicable` with
the reason. A kind may not add a comment, nor a word that names the study (`plant`, `vacuous`,
`oracle`, `mutant`, `stub`, `perturb`, `under_spec`, `wrong`) that the draft did not already hold.

After the files are written, the session is validated exactly as approval validates a sheet
before an investor may approve it (`termsheet.validate`, approval.py `_load_valid`): structure,
then every check on an empty workspace. A plant approval would refuse is put back to the draft's
check and recorded as `caught` with `caught_by: "T08"` (or `"validate"` for any other refusal); it
is never shown. Each key entry carries `status` (`shown`, `inapplicable` or `caught`),
`caught_by`, the planted file's `sha256` (null when nothing was planted) and `oracle`
(`holds`, `detail`, `attempts`).

On the bytesize fixture (`tests/fixtures/plants_draft_bytesize`, 8 checks, 5 mutants), with the
oracle holding: `wrong_value` 6 of 8 (c04 and c08 compare to no literal), `vacuous` 8 of 8,
`under_specified` 4 of 8 (c02, c03, c06, c07: the only checks that kill a mutant on their own).
Untested on other tasks and drafts so far.
