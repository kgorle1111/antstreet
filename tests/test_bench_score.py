"""Scoring a draft's checks as a classifier: precision on the reference, recall on the mutants."""

from pathlib import Path

import pytest

from boss.bench import score as score_module
from boss.bench.score import DraftScore, count_wrong_checks, draft_checks, score_draft
from boss.bench.tasks import BenchTask, load_task
from boss.gate import Check

TASKS = Path(__file__).parent.parent / "bench" / "tasks"

# A tiny task: f(x) is x + 1. The reference does that; each mutant gets f(1) and f(2) wrong or not.
REFERENCE = "def f(x):\n    return x + 1\n"
SOUND = "from demo import f\n\ndef test_one():\n    assert f(1) == 2\n"
# Demands f(2) == 100, which the idea (x + 1) does not support: the reference fails it.
WRONG = "from demo import f\n\ndef test_two():\n    assert f(2) == 100\n"


def make_task(root: Path, mutants: dict[str, str]) -> BenchTask:
    (root / "reference").mkdir(parents=True)
    (root / "reference" / "demo.py").write_text(REFERENCE)
    for name, source in mutants.items():
        (root / "mutants" / name).mkdir(parents=True)
        (root / "mutants" / name / "demo.py").write_text(source)
    return BenchTask("demo", "Demo", "easy", root)


def make_draft(root: Path, **checks: str) -> Path:
    """`c01=...` becomes test_c01.py in a fresh folder."""
    root.mkdir(parents=True)
    for check_id, code in checks.items():
        (root / f"test_{check_id}.py").write_text(code)
    return root


# A fails the sound check (f(1) is wrong) and also the wrong one. B keeps f(1) right, so only the
# wrong check fails it. C is right on f(1) and gives the wrong check its demanded 100: it passes
# everything the draft asks.
A = "def f(x):\n    return x\n"
B = "def f(x):\n    return x + 1 if x == 1 else 0\n"
C = "def f(x):\n    return 2 if x == 1 else 100\n"


def test_one_wrong_check_one_sound_killer_and_a_mutant_only_the_wrong_check_kills(tmp_path):
    task = make_task(tmp_path / "task", {"a": A, "b": B})
    score = score_draft(task, make_draft(tmp_path / "checks", c01=SOUND, c02=WRONG))
    assert score == DraftScore(
        checks=2,
        wrong=("c02",),
        mutants=2,
        killed=("a",),
        killed_only_by_wrong=("b",),
        survived=(),
    )
    assert score.precision == 1 / 2  # one of two checks is sound
    assert score.recall == 1 / 2  # b is not detected: the wrong check rejects everything


def test_a_mutant_that_passes_every_check_survives_even_the_wrong_one(tmp_path):
    task = make_task(tmp_path / "task", {"a": A, "b": B, "c": C})
    score = score_draft(task, make_draft(tmp_path / "checks", c01=SOUND, c02=WRONG))
    assert (score.killed, score.killed_only_by_wrong, score.survived) == (("a",), ("b",), ("c",))
    assert score.recall == 1 / 3


def test_a_mutant_failing_both_a_sound_and_a_wrong_check_counts_as_killed(tmp_path):
    task = make_task(tmp_path / "task", {"a": A})
    score = score_draft(task, make_draft(tmp_path / "checks", c01=SOUND, c02=WRONG))
    assert score.killed == ("a",) and score.killed_only_by_wrong == ()


def test_a_sound_draft_has_full_precision_and_a_draft_of_wrong_checks_has_none(tmp_path):
    task = make_task(tmp_path / "task", {"a": A, "b": B})
    sound = score_draft(task, make_draft(tmp_path / "s", c01=SOUND))
    assert (sound.precision, sound.wrong, sound.recall) == (1.0, (), 1 / 2)
    assert sound.survived == ("b",)
    wrong = score_draft(task, make_draft(tmp_path / "w", c01=WRONG, c02=WRONG.replace("100", "7")))
    assert (wrong.precision, wrong.wrong) == (0.0, ("c01", "c02"))
    assert wrong.recall == 0.0 and wrong.killed_only_by_wrong == ("a", "b")


def test_every_check_runs_on_every_mutant_in_one_gate_run_each(tmp_path, monkeypatch):
    task = make_task(tmp_path / "task", {"a": A, "b": B, "c": C})
    draft = make_draft(tmp_path / "checks", c01=SOUND, c02=WRONG, c03=SOUND)
    calls = []
    real = score_module.run_gate

    def counting(workspace, checks_dir, checks, *args, **kwargs):
        calls.append((Path(workspace).name, Path(checks_dir), [c.id for c in checks]))
        return real(workspace, checks_dir, checks, *args, **kwargs)

    monkeypatch.setattr(score_module, "run_gate", counting)
    score_draft(task, draft)
    assert calls == [(name, draft, ["c01", "c02", "c03"]) for name in ("reference", "a", "b", "c")]


def test_a_check_that_hangs_a_mutant_has_caught_it(tmp_path, monkeypatch):
    monkeypatch.setattr(score_module, "MUTANT_TIMEOUT_S", 1.0)
    task = make_task(tmp_path / "task", {"loops": "def f(x):\n    while True:\n        pass\n"})
    score = score_draft(task, make_draft(tmp_path / "checks", c01=SOUND))
    assert score.killed == ("loops",)


def test_a_check_that_cannot_import_the_module_fails_the_reference_too(tmp_path):
    task = make_task(tmp_path / "task", {"a": A})
    draft = make_draft(
        tmp_path / "checks", c01="from nowhere import f\n\ndef test_x():\n    pass\n"
    )
    score = score_draft(task, draft)
    assert score.wrong == ("c01",) and score.killed_only_by_wrong == ("a",)


def test_scoring_a_draft_needs_checks_and_mutants(tmp_path):
    task = make_task(tmp_path / "task", {"a": A})
    with pytest.raises(ValueError, match="no checks"):
        score_draft(task, tmp_path / "missing")
    (tmp_path / "empty").mkdir()
    (tmp_path / "empty" / "notes.txt").write_text("not a check")
    with pytest.raises(ValueError, match="no checks"):
        score_draft(task, tmp_path / "empty")
    bare = make_task(tmp_path / "bare", {})
    with pytest.raises(ValueError, match="task demo has no mutants"):
        score_draft(bare, make_draft(tmp_path / "checks", c01=SOUND))


def test_scoring_leaves_the_reference_the_mutants_and_the_draft_untouched(tmp_path):
    task = make_task(tmp_path / "task", {"a": A})
    draft = make_draft(tmp_path / "checks", c01=SOUND)

    def snapshot():
        return sorted(
            (p.relative_to(tmp_path), p.read_bytes()) for p in tmp_path.rglob("*") if p.is_file()
        )

    before = snapshot()
    score_draft(task, draft)
    assert snapshot() == before
    assert not list(tmp_path.rglob("__pycache__"))


# --- draft_checks and count_wrong_checks (moved here from the runner) ----------------------------


def test_checks_are_named_by_their_files_sorted_and_only_test_py(tmp_path):
    draft = make_draft(tmp_path / "d", c02=SOUND, c01=SOUND)
    (draft / "helper.py").write_text("")
    (draft / "test_notes.txt").write_text("")
    assert draft_checks(draft) == [Check("c01", "test_c01.py"), Check("c02", "test_c02.py")]
    assert draft_checks(tmp_path / "missing") == []


def test_wrong_checks_are_counted_and_none_means_no_draft(tmp_path):
    task = make_task(tmp_path / "task", {"a": A})
    assert count_wrong_checks(task, tmp_path / "missing") is None
    assert count_wrong_checks(task, make_draft(tmp_path / "empty")) is None
    assert count_wrong_checks(task, make_draft(tmp_path / "sound", c01=SOUND)) == 0
    both = make_draft(tmp_path / "both", c01=SOUND, c02=WRONG, c03=WRONG)
    assert count_wrong_checks(task, both) == 2


# --- the DraftScore value ----------------------------------------------------------------------


def score_of(**changes) -> DraftScore:
    fields = {
        "checks": 4,
        "wrong": ("c02",),
        "mutants": 5,
        "killed": ("a", "b", "c"),
        "killed_only_by_wrong": ("d",),
        "survived": ("e",),
    }
    return DraftScore(**(fields | changes))


def test_precision_and_recall_are_ratios_of_checks_and_of_mutants():
    score = score_of()
    assert score.precision == 3 / 4
    assert score.recall == 3 / 5
    assert score_of(wrong=()).precision == 1.0
    assert score_of(wrong=("c01", "c02", "c03", "c04")).precision == 0.0


@pytest.mark.parametrize(
    "changes",
    [
        {"checks": 0, "wrong": ()},
        {"mutants": 0, "killed": (), "killed_only_by_wrong": (), "survived": ()},
        {"wrong": ("c01", "c02", "c03", "c04", "c05")},
        {"survived": ()},
        {"killed": ("a", "b", "c", "x")},
    ],
    ids=["no-checks", "no-mutants", "more-wrong-than-checks", "mutants-lost", "mutants-added"],
)
def test_a_score_that_does_not_add_up_is_refused(changes):
    with pytest.raises(ValueError):
        score_of(**changes)


def test_a_score_survives_a_round_trip_through_json_types():
    score = score_of()
    raw = score.to_dict()
    assert raw["killed"] == ("a", "b", "c")
    as_json = {k: list(v) if isinstance(v, tuple) else v for k, v in raw.items()}
    assert DraftScore.from_dict(as_json) == score


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.pop("wrong"),
        lambda d: d.update(extra=1),
        lambda d: d.update(checks="4"),
        lambda d: d.update(checks=True),
        lambda d: d.update(mutants=5.0),
        lambda d: d.update(wrong="c02"),
        lambda d: d.update(killed=[1, 2, 3]),
        lambda d: d.update(killed=["a", 1, "c"]),
        lambda d: d.update(survived=None),
    ],
    ids=[
        "missing",
        "extra",
        "str-int",
        "bool-int",
        "float-int",
        "str-list",
        "int-names",
        "mixed-names",
        "none",
    ],
)
def test_a_malformed_saved_score_is_refused(mutate):
    raw = {k: list(v) if isinstance(v, tuple) else v for k, v in score_of().to_dict().items()}
    mutate(raw)
    with pytest.raises(ValueError):
        DraftScore.from_dict(raw)
    with pytest.raises(ValueError):
        DraftScore.from_dict([])


# --- against the real corpus ---------------------------------------------------------------------


def test_a_real_check_kills_the_real_mutant_it_targets_and_reference_passes_it(tmp_path):
    task = load_task(TASKS / "slugify")
    check = (
        "from slugify import slugify\n\n"
        "def test_accents():\n    assert slugify('Caf\\u00e9 cr\\u00e8me') == 'cafe-creme'\n"
    )
    score = score_draft(task, make_draft(tmp_path / "checks", c01=check))
    assert score.wrong == ()
    assert score.killed == ("accents_dropped_not_folded",)
    assert set(score.survived) == {"max_length_zero_accepted", "pilot_firm", "pilot_single"}
