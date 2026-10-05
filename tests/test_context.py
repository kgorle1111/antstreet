"""The context bundle: bounded, hashed, saved, and made only of what a worker may be told."""

import dataclasses
import hashlib
import random

import pytest

from boss import context
from boss.context import (
    DROP_ORDER,
    BundleTooBig,
    Handoff,
    SliceInputs,
    build_bundle,
    derive_reads,
    imported_modules,
    interfaces_section,
    verify,
    write_prompt,
)
from boss.gate import CheckResult, CheckStatus
from boss.ledger import Event, EventType
from boss.rundir import RunPaths
from boss.termsheet import CheckSpec, Dispatch, Round, Task, TermSheet

C_REV = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"
C_UP = (
    "import rev\nfrom up import shout, whisper\n\n"
    "def test_shout():\n    assert shout(rev.reverse('a')) == 'A!'\n"
)
SYSTEM = "You are a builder."


def sheet(*, reads=("t1",), idea="Reverse then shout."):
    d = lambda r: Dispatch("builder", None, "haiku", "default", "sonnet", 2, None, r)  # noqa: E731
    tasks = (
        Task("t1", "Create rev.py with reverse(s).", ("rev.py",), d(())),
        Task("t2", "Create up.py with shout(s) and whisper(s).", ("up.py",), d(reads)),
    )
    checks = (
        CheckSpec("c01", "reverses", "test_c01.py", "t1"),
        CheckSpec("c02", "shouts", "test_c02.py", "t2"),
    )
    return TermSheet(idea, 800_000, (Round(1, 800_000, 2),), checks, tasks, True, "firm")


@pytest.fixture
def checks_dir(tmp_path):
    folder = tmp_path / "checks"
    folder.mkdir()
    (folder / "test_c01.py").write_text(C_REV)
    (folder / "test_c02.py").write_text(C_UP)
    return folder


def bundle(s, task, checks_dir, **kw):
    inputs = kw.pop("inputs", SliceInputs())
    return build_bundle(s, task, checks_dir, system=SYSTEM, inputs=inputs, **kw)


def test_a_first_bundle_holds_the_idea_the_brief_and_the_tasks_own_checks_and_nothing_else(
    checks_dir,
):
    s = sheet()
    b = bundle(s, s.tasks[1], checks_dir)
    assert "> Reverse then shout." in b.prompt
    assert "Create up.py with shout(s) and whisper(s)." in b.prompt
    assert "def test_shout" in b.prompt
    assert "def test_word" not in b.prompt  # another task's check never reaches this worker
    assert set(b.parts) == {"task", "interfaces"} and b.dropped == ()


def test_the_interface_section_names_what_the_checks_take_from_other_tasks_and_no_code(
    checks_dir,
):
    s = sheet()
    section = interfaces_section(s, s.tasks[1], checks_dir)
    assert "- rev (built by task t1): reverse" in section  # `import rev` then `rev.reverse`
    assert "up" not in section.split("\n", 2)[-1]  # the task's own module is not an interface
    assert "def " not in section and "return" not in section
    assert interfaces_section(sheet(reads=()), sheet(reads=()).tasks[1], checks_dir) == ""
    assert interfaces_section(s, s.tasks[0], checks_dir) == ""  # t1 reads nothing


def test_reads_are_found_from_the_tasks_own_check_imports(checks_dir):
    assert derive_reads(sheet(), checks_dir) == {"t1": (), "t2": ("t1",)}


def test_a_task_that_owns_the_whole_workspace_is_never_an_interface():
    assert not context.owns_module(Task("t", "b", (".",)), "anything")
    assert context.owns_module(Task("t", "b", ("pkg",)), "pkg")
    assert context.owns_module(Task("t", "b", ("rev.py",)), "rev")


def test_imports_are_read_by_the_parser_and_unparsable_code_names_none():
    assert imported_modules("import a.b\nfrom c.d import e\nfrom . import f") == {"a", "c"}
    assert imported_modules("def broken(:") == set()


def test_the_hash_is_of_the_system_prompt_a_nul_and_the_prompt_and_equals_the_saved_file(
    checks_dir, tmp_path
):
    s = sheet()
    b = bundle(s, s.tasks[0], checks_dir)
    assert b.sha256 == hashlib.sha256(SYSTEM.encode() + b"\0" + b.prompt.encode()).hexdigest()
    paths = RunPaths(tmp_path / "run")
    write_prompt(paths, "w1", 1, b)
    assert paths.prompt("w1", 1).read_bytes() == b.file_bytes()
    assert hashlib.sha256(paths.prompt("w1", 1).read_bytes()).hexdigest() == b.sha256
    assert b.start_data()["context_chars"] == len(b.prompt)
    assert sum(b.start_data()["context_parts"].values()) == len(b.prompt)  # NUL joins add nothing


def start_event(worker, number, b, run="r1"):
    return Event(
        run=run, round=1, actor=f"worker:{worker}", event=EventType.SLICE_START,
        data={"slice": number, "task": "t1", "cap_micros": 1, "session": "s"} | b.start_data(),
    )  # fmt: skip


def test_verify_finds_a_changed_or_missing_prompt_file_and_only_the_latest_start_counts(
    checks_dir, tmp_path
):
    s = sheet()
    b = bundle(s, s.tasks[0], checks_dir)
    other = bundle(s, s.tasks[1], checks_dir)
    paths = RunPaths(tmp_path / "run")
    write_prompt(paths, "w1", 1, b)
    assert verify(paths, [start_event("w1", 1, b)]) == []
    paths.prompt("w1", 1).write_bytes(b.file_bytes() + b" ")
    assert verify(paths, [start_event("w1", 1, b)]) == [
        "w1 slice 1: its prompt file is not what was recorded"
    ]
    # a slice started twice (the first was cut off) is held to its latest start only
    assert verify(paths, [start_event("w1", 1, b), start_event("w1", 1, other)]) != []
    write_prompt(paths, "w1", 1, other)
    assert verify(paths, [start_event("w1", 1, b), start_event("w1", 1, other)]) == []
    paths.prompt("w1", 1).unlink()
    assert verify(paths, [start_event("w1", 1, b)]) == ["w1 slice 1: its prompt file is missing"]
    plain = Event(run="r1", round=1, actor="worker:w1", event=EventType.SLICE_START)
    assert verify(paths, [plain]) == []  # a run without dispatch records no hash


@pytest.mark.parametrize("bad", ["1", 1.0, True, None, [1], {"n": 1}])
def test_verify_skips_a_slice_number_that_is_not_an_int_instead_of_crashing(
    checks_dir, tmp_path, bad
):
    s = sheet()
    b = bundle(s, s.tasks[0], checks_dir)
    e = start_event("w1", 1, b)
    e = Event(run=e.run, round=e.round, actor=e.actor, event=e.event, data={**e.data, "slice": bad})
    assert verify(RunPaths(tmp_path / "run"), [e]) == []


def test_mandatory_parts_are_never_cut_and_too_big_a_brief_is_refused_with_its_sizes(checks_dir):
    s = sheet(idea="x " * 400)
    full = bundle(s, s.tasks[1], checks_dir)
    with pytest.raises(BundleTooBig) as err:
        bundle(s, s.tasks[1], checks_dir, bound=full.parts["task"] - 1)
    assert "task t2" in str(err.value) and f"task {full.parts['task']}" in str(err.value)
    assert "limit is" in str(err.value)


def test_the_interface_part_is_the_first_to_go(checks_dir):
    s = sheet()
    full = bundle(s, s.tasks[1], checks_dir)
    tight = bundle(s, s.tasks[1], checks_dir, bound=len(full.prompt) - 1)
    assert tight.dropped == ("interfaces",) and "interfaces" not in tight.parts
    assert tight.prompt == full.prompt.removesuffix(full.prompt[len(tight.prompt) :]).rstrip()


def handoff(tmp_path, tail="boom\n" * 400):
    kept = tmp_path / "kept"
    kept.mkdir()
    (kept / "rev.py").write_text("x = 1\n")
    fired = Event(
        run="r1", round=1, actor="rule", event=EventType.FIRED,
        data={"worker": "w1", "task": "t1", "reason": "no progress", "evidence": {}},
    )  # fmt: skip
    gate = [CheckResult("c01", CheckStatus.FAILED, 1, "1 failed", tail, 0.1)]
    return Handoff(fired, [], gate, kept)


def test_after_the_interface_the_file_list_goes_and_then_the_older_gate_output(
    checks_dir, tmp_path
):
    s = sheet()
    inputs = SliceInputs(handoff=handoff(tmp_path))
    sizes = [len(bundle(s, s.tasks[1], checks_dir, inputs=inputs, bound=10**9).prompt)]
    seen = {}
    for level in DROP_ORDER[1:]:
        parts = context._parts(s, s.tasks[1], checks_dir, inputs, level)
        seen[level] = len("\n\n".join(t for _, t in parts))
    assert sizes[0] > seen[DROP_ORDER[1]] > seen[DROP_ORDER[2]] > seen[DROP_ORDER[3]]
    for bound, dropped in (
        (seen[DROP_ORDER[1]], ("interfaces",)),
        (seen[DROP_ORDER[2]], ("interfaces", "files")),
        (seen[DROP_ORDER[3]], ("interfaces", "files", "tails")),
    ):
        got = bundle(s, s.tasks[1], checks_dir, inputs=inputs, bound=bound)
        assert got.dropped == dropped and len(got.prompt) <= bound
    assert "previous_attempt/" in bundle(s, s.tasks[1], checks_dir, inputs=inputs).prompt
    cut = bundle(s, s.tasks[1], checks_dir, inputs=inputs, bound=seen[DROP_ORDER[3]])
    assert "previous_attempt/" not in cut.prompt and "boom" not in cut.prompt
    assert "The previous builder was stopped: no progress" in cut.prompt  # the reason stays


def test_a_resumed_slice_is_the_gate_feedback_and_the_investors_words(checks_dir):
    s = sheet()
    gate = [CheckResult("c02", CheckStatus.FAILED, 1, "1 failed", "assert 1 == 2", 0.1)]
    inputs = SliceInputs(resume=True, gate_results=gate, notes=("Investor: keep it simple.",))
    b = bundle(s, s.tasks[1], checks_dir, inputs=inputs)
    assert list(b.parts) == ["gate"] and "assert 1 == 2" in b.prompt
    assert "Investor: keep it simple." in b.prompt


def test_a_bundle_never_exceeds_its_bound_or_refuses_cleanly_for_any_input(checks_dir):
    rng = random.Random(5001)
    s = sheet()
    for _ in range(300):
        bound = rng.randint(100, 4_000)
        idea = "w " * rng.randint(0, 800)
        notes = tuple("n" * rng.randint(0, 600) for _ in range(rng.randint(0, 3)))
        sh = dataclasses.replace(s, idea=idea or "idea")
        try:
            got = bundle(sh, sh.tasks[1], checks_dir, inputs=SliceInputs(notes=notes), bound=bound)
        except BundleTooBig:
            continue
        assert len(got.prompt) <= bound


def test_hostile_sentinels_outside_the_tasks_own_brief_reach_no_bundle(tmp_path):
    folder = tmp_path / "run" / "checks"
    folder.mkdir(parents=True)
    (folder / "test_c01.py").write_text(C_REV + "# T1-CHECK-SENTINEL\n")
    (folder / "test_c02.py").write_text(C_UP)
    held = tmp_path / "run" / "held_out"
    held.mkdir()
    (held / "test_h01.py").write_text("# HELD-OUT-SENTINEL\ndef test_h():\n    pass\n")
    key = tmp_path / ".boss"
    key.mkdir()
    (key / "investor.key").write_text("KEY-SENTINEL")
    hidden = tmp_path / "hidden_checks"
    hidden.mkdir()
    (hidden / "test_hidden.py").write_text("# HIDDEN-SENTINEL\n")
    s = sheet()
    for task in s.tasks:
        got = bundle(s, task, folder)
        for sentinel in ("HELD-OUT-SENTINEL", "KEY-SENTINEL", "HIDDEN-SENTINEL"):
            assert sentinel not in got.prompt and sentinel not in got.system
    assert "T1-CHECK-SENTINEL" in bundle(s, s.tasks[0], folder).prompt  # its own check: yes
    assert "T1-CHECK-SENTINEL" not in bundle(s, s.tasks[1], folder).prompt  # t2's worker: no
