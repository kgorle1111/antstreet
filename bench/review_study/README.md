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
symlink, inside any git checkout, or overlapping the source is refused. No plant kinds are
registered yet (they arrive with their oracles), so today only a seed that plants nothing runs
without a caller-supplied kind; each key's `oracle` field is `null` until then.
