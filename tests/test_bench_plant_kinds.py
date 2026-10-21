"""The automatic plant kinds and their oracles, on a real archived draft (the bytesize fixture) and
the real bench task's reference solution and mutants (bench/review_study/README.md)."""

from __future__ import annotations

import difflib
import json
import random
import shutil
from pathlib import Path

import pytest

from antstreet.bench import plants
from antstreet.bench.plant_kinds import (
    Inapplicable,
    OracleResult,
    UnderSpecified,
    Vacuous,
    WrongValue,
)
from antstreet.bench.plants import KINDS, PlantError, materialize, plant_one, select_plants
from antstreet.bench.tasks import load_task
from antstreet.gate import Check
from antstreet.termsheet import empty_checks_problems

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "plants_draft_bytesize"
TASK_DIR = ROOT / "bench" / "tasks" / "bytesize"
RUN_ID = "20261013T081410Z-cc00d0"
CHECK_IDS = tuple(f"c0{n}" for n in range(1, 9))
FILES = {c: f"test_{c}.py" for c in CHECK_IDS}
HINTS = ("plant", "vacuous", "oracle", "mutant", "stub", "perturb", "under_spec", "wrong")

# What each kind can plant in this draft with its oracle holding (measured 2026-10-21, seed 7).
APPLICABLE = {
    "wrong_value": {"c01", "c02", "c03", "c05", "c06", "c07"},  # c04, c08 compare no literal
    "vacuous": set(CHECK_IDS),
    "under_specified": {"c02", "c03", "c06", "c07"},  # the only checks that kill a mutant
}


def original(check_id: str) -> bytes:
    return (FIXTURE / "checks" / FILES[check_id]).read_bytes()


def draw(kind: object, check_id: str, seed: int) -> bytes | str:
    try:
        return kind.plant(original(check_id), random.Random(seed))  # type: ignore[attr-defined]
    except Inapplicable as exc:
        return f"inapplicable: {exc}"


def changed_lines(before: bytes, after: bytes) -> list[str]:
    diff = difflib.ndiff(before.decode().splitlines(), after.decode().splitlines())
    return [line for line in diff if line[:1] in "+-"]


@pytest.fixture
def source(tmp_path: Path) -> Path:
    run = tmp_path / "archive" / "rep1" / ".boss" / "runs" / RUN_ID
    shutil.copytree(FIXTURE, run)
    return run


def out(tmp_path: Path, name: str = "study") -> Path:
    path = tmp_path / name
    path.mkdir()
    return path


def seed_planting(want: int, kind_names: list[str]) -> int:
    for seed in range(200):
        if len(select_plants(CHECK_IDS, sorted(kind_names), random.Random(seed))) == want:
            return seed
    raise AssertionError(f"no seed below 200 plants {want}")


# --- transforms: no gate ----------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_each_kinds_transform_is_deterministic_per_seed(kind):
    for check_id in CHECK_IDS:
        for seed in range(6):
            assert draw(KINDS[kind], check_id, seed) == draw(KINDS[kind], check_id, seed)


def test_wrong_value_changes_one_literal_and_the_seed_chooses_which():
    seen = set()
    for seed in range(20):
        planted = draw(WrongValue(), "c06", seed)
        assert isinstance(planted, bytes)
        removed, added = changed_lines(original("c06"), planted)
        assert removed.startswith("- ") and added.startswith("+ ")
        # Same call, same quotes, one literal different.
        assert removed.split("==")[0][2:] == added.split("==")[0][2:]
        assert removed.split("==")[1] != added.split("==")[1]
        seen.add(planted)
    assert len(seen) > 5


def test_wrong_value_is_inapplicable_where_no_assert_compares_to_a_literal():
    for check_id in ("c04", "c08"):
        assert "literal" in str(draw(WrongValue(), check_id, 0))


def test_vacuous_keeps_the_imports_and_asserts_only_that_the_names_exist():
    assert draw(Vacuous(), "c04", 0) == (
        b"def test_parse_size_errors():\n"
        b"    from bytesize import parse_size\n"
        b"    assert callable(parse_size)"
    )


def test_under_specified_drops_one_assert_line_and_nothing_else():
    for check_id in CHECK_IDS:
        for seed in range(6):
            planted = draw(UnderSpecified(), check_id, seed)
            assert isinstance(planted, bytes)
            (removed,) = changed_lines(original(check_id), planted)
            assert removed.strip().startswith("- ") and "assert" in removed


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_the_planted_text_never_hints_at_the_plant(kind):
    for check_id in CHECK_IDS:
        for seed in range(10):
            planted = draw(KINDS[kind], check_id, seed)
            if isinstance(planted, str):
                continue
            # The harness's own guard accepts it: no hint word, no new comment, still Python.
            assert plants._planted(KINDS[kind], original(check_id), planted, check_id) == planted
            text = planted.decode().lower()
            for word in HINTS:
                assert word not in text, (kind, check_id, word)


def test_the_hint_guard_refuses_a_new_comment_or_word():
    base = original("c01")
    with pytest.raises(PlantError, match="comment"):
        plants._planted(WrongValue(), base, base + b"# see c03\n", "c01")
    with pytest.raises(PlantError, match="mutant"):
        plants._planted(WrongValue(), base, base + b"x = 'mutant'\n", "c01")


# --- oracles: the real gate -------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize("kind", sorted(KINDS))
def test_each_kinds_oracle_holds_on_the_fixture_or_the_kind_says_why(kind):
    task = load_task(TASK_DIR)
    planted = set()
    for check_id in CHECK_IDS:
        outcome = plant_one(
            KINDS[kind], original(check_id), FILES[check_id], task, random.Random(7)
        )
        if outcome.data is not None:
            assert outcome.oracle.holds and outcome.data != original(check_id)
            planted.add(check_id)
        else:
            assert not outcome.oracle.holds
            assert outcome.oracle.detail.startswith("inapplicable: "), outcome.oracle.detail
    assert planted == APPLICABLE[kind]


@pytest.mark.slow
@pytest.mark.parametrize("kind", sorted(KINDS))
def test_a_no_op_plant_fails_each_oracle(kind):
    """Mutation proof that each oracle can fail: the draft's own check, presented as planted."""
    task = load_task(TASK_DIR)
    check = original("c02")  # every kind can plant c02
    assert KINDS[kind].oracle(check, check, FILES["c02"], task).holds is False


class Cosmetic(WrongValue):
    """Changes the file without making the check wrong: wrong_value's oracle must reject it."""

    name = "wrong_value"

    def plant(self, original: bytes, rng: random.Random) -> bytes:
        return original + b"\n"


class PassesEmpty(WrongValue):
    """A plant approval itself refuses: it passes on an empty workspace (T08). Its oracle holds
    so that only approval's validation stands between it and the reviewer."""

    name = "wrong_value"

    def plant(self, original: bytes, rng: random.Random) -> bytes:
        return b"def test_parse_size():\n    assert len('1.5 KiB') == 7\n"

    def oracle(self, original: bytes, planted: bytes, file: str, task: object) -> OracleResult:
        return OracleResult(True, "holds by construction")


@pytest.mark.slow
def test_a_draw_whose_oracle_does_not_hold_is_never_shown(source, tmp_path):
    seed = seed_planting(1, ["wrong_value"])
    session = materialize(source, TASK_DIR, out(tmp_path), seed, kinds={"wrong_value": Cosmetic()})
    (plant,) = json.loads(session.key_path.read_text())["plants"]
    assert plant["status"] == "inapplicable" and plant["sha256"] is None
    assert plant["oracle"]["holds"] is False and plant["oracle"]["attempts"] == plants.MAX_ATTEMPTS
    assert session.plants == ()
    shown = session.run_dir / "checks" / plant["file"]
    assert shown.read_bytes() == (source / "checks" / plant["file"]).read_bytes()


@pytest.mark.slow
def test_a_plant_approval_would_refuse_is_recorded_as_caught_by_t08_not_shown(source, tmp_path):
    seed = seed_planting(2, ["wrong_value"])
    session = materialize(
        source, TASK_DIR, out(tmp_path), seed, kinds={"wrong_value": PassesEmpty()}
    )
    key = json.loads(session.key_path.read_text())
    assert len(key["plants"]) == 2
    for plant in key["plants"]:
        assert plant["status"] == "caught" and plant["caught_by"] == "T08"
        shown = session.run_dir / "checks" / plant["file"]
        assert shown.read_bytes() == (source / "checks" / plant["file"]).read_bytes()
    assert session.plants == ()


@pytest.mark.slow
def test_vacuous_is_not_caught_by_the_empty_workspace_validation(source, tmp_path):
    seed = seed_planting(2, ["vacuous"])
    session = materialize(source, TASK_DIR, out(tmp_path), seed, kinds={"vacuous": Vacuous()})
    key = json.loads(session.key_path.read_text())
    assert [p["status"] for p in key["plants"]] == ["shown", "shown"]
    assert [p["caught_by"] for p in key["plants"]] == [None, None]
    checks = [Check(p["check_id"], p["file"]) for p in key["plants"]]
    assert empty_checks_problems(checks, session.run_dir / "checks") == []
    for plant in key["plants"]:
        assert b"callable(" in (session.run_dir / "checks" / plant["file"]).read_bytes()


@pytest.mark.slow
def test_the_same_seed_gives_the_same_session_with_the_real_kinds(source, tmp_path):
    seed = seed_planting(2, sorted(KINDS))
    a = materialize(source, TASK_DIR, out(tmp_path, "a"), seed)
    b = materialize(source, TASK_DIR, out(tmp_path, "b"), seed)
    assert a.key_path.read_bytes() == b.key_path.read_bytes()
    for check_id in CHECK_IDS:
        name = FILES[check_id]
        assert (a.run_dir / "checks" / name).read_bytes() == (
            b.run_dir / "checks" / name
        ).read_bytes()
    assert all(
        p["oracle"]["holds"]
        for p in json.loads(a.key_path.read_text())["plants"]
        if p["status"] == "shown"
    )
