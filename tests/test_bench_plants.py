"""The planted-check harness core: a draft copied into a scratch session, plants chosen by seed,
and the key kept outside the reviewer's folder (bench/METHOD.md, "Planted checks")."""

from __future__ import annotations

import hashlib
import json
import random
import shutil
import stat
from pathlib import Path

import pytest

from antstreet.bench import plants
from antstreet.bench.plants import PlantError, materialize, select_plants

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "plants_draft_bytesize"  # a real archived draft
TASK = ROOT / "bench" / "tasks" / "bytesize"
RUN_ID = "20261013T081410Z-cc00d0"
CHECK_IDS = tuple(f"c0{n}" for n in range(1, 9))


class AppendTest:
    """Test-only kind: adds one more test function. Real kinds come with their oracles (PR 2)."""

    name = "append_test"

    def plant(self, original: bytes, rng: random.Random) -> bytes:
        return original.rstrip(b"\n") + b"\n\n\ndef test_more():\n    assert %d\n" % rng.randint(
            1, 9
        )


class Telltale:
    name = "telltale"

    def plant(self, original: bytes, rng: random.Random) -> bytes:
        return original + b"\n# PLANTED\n"


KINDS = {"append_test": AppendTest()}


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """A boss project as the archive keeps it: the draft plus a ledger, logs and an investor key."""
    project = tmp_path / "archive" / "rep1"
    run = project / ".boss" / "runs" / RUN_ID
    shutil.copytree(FIXTURE, run)
    (run / "ledger.jsonl").write_text('{"type": "run_started"}\n')
    (run / "logs").mkdir()
    (run / "logs" / "w1.jsonl").write_text("{}\n")
    (project / ".boss" / "investor.key").write_bytes(b"not a real key, a stand-in\n")
    return run


def out(tmp_path: Path, name: str = "study") -> Path:
    path = tmp_path / name
    path.mkdir()
    return path


def digests(root: Path) -> dict[str, str]:
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def planted_seed(want: int) -> int:
    """The first seed that plants exactly `want` checks in the 8-check fixture."""
    for seed in range(200):
        if len(select_plants(CHECK_IDS, sorted(KINDS), random.Random(seed))) == want:
            return seed
    raise AssertionError(f"no seed below 200 plants {want}")


def test_the_same_seed_gives_a_byte_identical_key_and_session(source, tmp_path):
    seed = planted_seed(2)
    a = materialize(source, TASK, out(tmp_path, "a"), seed, kinds=KINDS)
    b = materialize(source, TASK, out(tmp_path, "b"), seed, kinds=KINDS)
    assert a.key_path.read_bytes() == b.key_path.read_bytes()
    assert a.plants == b.plants and len(a.plants) == 2
    assert digests(a.run_dir) == digests(b.run_dir)


def test_different_seeds_choose_different_plants():
    chosen = {select_plants(CHECK_IDS, ["a", "b"], random.Random(seed)) for seed in range(30)}
    assert len(chosen) > 10
    assert {len(c) for c in chosen} == {0, 1, 2}
    for selection in chosen:
        ids = [check_id for check_id, _ in selection]
        assert len(set(ids)) == len(ids) and set(ids) <= set(CHECK_IDS)


def test_the_selection_is_capped_by_the_number_of_checks():
    for seed in range(30):
        assert len(select_plants(("c01",), ["a"], random.Random(seed))) <= 1
        assert select_plants((), ["a"], random.Random(seed)) == ()


def test_the_key_is_outside_the_session_and_only_its_owner_can_read_it(source, tmp_path):
    root = out(tmp_path)
    session = materialize(source, TASK, root, planted_seed(1), kinds=KINDS)
    assert session.key_path == root / "keys" / f"{session.sid}.json"
    assert not session.key_path.is_relative_to(root / "sessions")
    assert stat.S_IMODE(session.key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE((root / "keys").stat().st_mode) == 0o700
    assert list((root / "sessions").rglob("*.json")) == [session.run_dir / "term_sheet.json"]


def test_the_key_names_each_plant_its_kind_and_the_planted_files_hash(source, tmp_path):
    seed = planted_seed(2)
    session = materialize(source, TASK, out(tmp_path), seed, kinds=KINDS)
    key = json.loads(session.key_path.read_text())
    assert key["seed"] == seed and key["task"] == "bytesize" and key["run_id"] == RUN_ID
    assert key["source"] == str(source.resolve())
    assert set(key["source_sha256"]) == {"term_sheet.json"} | {
        f"checks/test_{c}.py" for c in CHECK_IDS
    }
    assert len(key["plants"]) == 2
    for plant in key["plants"]:
        planted = session.run_dir / "checks" / plant["file"]
        assert plant["kind"] == "append_test" and plant["oracle"] is None
        assert plant["sha256"] == hashlib.sha256(planted.read_bytes()).hexdigest()
        assert plant["sha256"] != key["source_sha256"][f"checks/{plant['file']}"]


def test_the_reviewer_sees_normal_ids_and_nothing_that_names_a_plant(source, tmp_path):
    session = materialize(source, TASK, out(tmp_path), planted_seed(2), kinds=KINDS)
    sheet = session.run_dir / "term_sheet.json"
    assert sheet.read_bytes() == (source / "term_sheet.json").read_bytes()
    names = sorted(p.name for p in (session.run_dir / "checks").iterdir())
    assert names == [f"test_{c}.py" for c in CHECK_IDS]
    for path in session.project.rglob("*"):
        assert "plant" not in path.as_posix().removeprefix(str(session.project)).lower()
        if path.is_file():
            assert b"plant" not in path.read_bytes().lower()
    for check_id, _ in session.plants:
        assert check_id in CHECK_IDS


def test_a_kind_whose_output_names_a_plant_is_refused(source, tmp_path):
    with pytest.raises(PlantError, match="plant"):
        materialize(source, TASK, out(tmp_path), planted_seed(1), kinds={"telltale": Telltale()})


def test_a_session_with_plants_but_no_kinds_is_refused(source, tmp_path):
    with pytest.raises(PlantError, match="no plant kinds"):
        materialize(source, TASK, out(tmp_path), planted_seed(1), kinds={})


def test_a_seed_with_no_plants_needs_no_kinds(source, tmp_path):
    session = materialize(source, TASK, out(tmp_path), planted_seed(0), kinds={})
    assert session.plants == ()
    assert digests(session.run_dir) == {
        k: v
        for k, v in digests(source).items()
        if k == "term_sheet.json" or k.startswith("checks/")
    }


def test_only_the_term_sheet_and_checks_are_copied_never_the_ledger_or_a_key(source, tmp_path):
    session = materialize(source, TASK, out(tmp_path), planted_seed(1), kinds=KINDS)
    copied = {p.relative_to(session.project).as_posix() for p in session.project.rglob("*")}
    run = f".boss/runs/{RUN_ID}"
    assert copied == {".boss", ".boss/runs", run, f"{run}/term_sheet.json", f"{run}/checks"} | {
        f"{run}/checks/test_{c}.py" for c in CHECK_IDS
    }


def test_the_source_is_byte_for_byte_unchanged(source, tmp_path):
    before = digests(source.parents[2])
    materialize(source, TASK, out(tmp_path), planted_seed(2), kinds=KINDS)
    assert digests(source.parents[2]) == before


def test_a_write_to_the_source_during_materialize_is_caught(source, tmp_path, monkeypatch):
    real = plants._write_new

    def leaky(path: Path, data: bytes) -> None:
        real(path, data)
        with (source / "term_sheet.json").open("ab") as fh:
            fh.write(b" ")

    monkeypatch.setattr(plants, "_write_new", leaky)
    with pytest.raises(PlantError, match="source changed"):
        materialize(source, TASK, out(tmp_path), planted_seed(1), kinds=KINDS)


def test_an_out_root_inside_this_repository_is_refused(source):
    with pytest.raises(PlantError, match="git checkout"):
        materialize(source, TASK, ROOT / "bench", 1, kinds=KINDS)


def test_an_out_root_inside_any_git_checkout_is_refused(source, tmp_path):
    repo = out(tmp_path, "repo")
    (repo / ".git").mkdir()
    (repo / "study").mkdir()
    with pytest.raises(PlantError, match="git checkout"):
        materialize(source, TASK, repo / "study", 1, kinds=KINDS)


def test_an_out_root_overlapping_the_source_is_refused(source, tmp_path):
    with pytest.raises(PlantError, match="overlap"):
        materialize(source, TASK, source.parents[2], 1, kinds=KINDS)


def test_a_missing_out_root_is_refused_not_created(source, tmp_path):
    with pytest.raises(PlantError, match="existing directory"):
        materialize(source, TASK, tmp_path / "nope", 1, kinds=KINDS)
    assert not (tmp_path / "nope").exists()


def test_a_symlinked_source_is_refused(source, tmp_path):
    link = tmp_path / "link"
    link.symlink_to(source, target_is_directory=True)
    with pytest.raises(PlantError, match="symlink"):
        materialize(link, TASK, out(tmp_path), 1, kinds=KINDS)


def test_a_symlinked_check_file_is_refused(source, tmp_path):
    secret = tmp_path / "elsewhere.py"
    secret.write_text("def test_x():\n    pass\n")
    (source / "checks" / "test_c03.py").unlink()
    (source / "checks" / "test_c03.py").symlink_to(secret)
    with pytest.raises(PlantError, match="symlink"):
        materialize(source, TASK, out(tmp_path), 1, kinds=KINDS)


def test_an_oversized_check_file_is_refused(source, tmp_path):
    big = b"def test_x():\n    pass\n" + b"#" * plants.MAX_FILE_BYTES
    (source / "checks" / "test_c02.py").write_bytes(big)
    with pytest.raises(PlantError, match="bytes"):
        materialize(source, TASK, out(tmp_path), 1, kinds=KINDS)


def test_a_term_sheet_that_is_not_valid_is_refused(source, tmp_path):
    (source / "term_sheet.json").write_text('{"idea": 3}')
    with pytest.raises(PlantError, match="term sheet"):
        materialize(source, TASK, out(tmp_path), 1, kinds=KINDS)


def test_a_draft_for_another_task_is_refused(source, tmp_path):
    with pytest.raises(PlantError, match="idea"):
        materialize(source, ROOT / "bench" / "tasks" / "roman", out(tmp_path), 1, kinds=KINDS)


def test_a_check_file_that_escapes_the_checks_folder_is_refused(source, tmp_path):
    sheet = json.loads((source / "term_sheet.json").read_text())
    sheet["checks"][0]["file"] = "../ledger.jsonl"
    (source / "term_sheet.json").write_text(json.dumps(sheet))
    with pytest.raises(PlantError, match="test_<name>.py"):
        materialize(source, TASK, out(tmp_path), 1, kinds=KINDS)


def test_materializing_the_same_session_twice_is_refused(source, tmp_path):
    root = out(tmp_path)
    materialize(source, TASK, root, 3, kinds=KINDS)
    with pytest.raises(PlantError, match="already exists"):
        materialize(source, TASK, root, 3, kinds=KINDS)


def test_a_sessions_folder_symlinked_out_of_out_root_is_refused(source, tmp_path):
    root = out(tmp_path)
    elsewhere = out(tmp_path, "elsewhere")
    (root / "sessions").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(PlantError, match="not under out_root"):
        materialize(source, TASK, root, 1, kinds=KINDS)
    assert list(elsewhere.iterdir()) == []
