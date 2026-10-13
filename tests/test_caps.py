"""`fund --boss-cap`, `--boss-timeout` and `--role-cap` (R3).

The boss's $0.25 cap, its 300 s timeout and each role's cap were constants: Opus 5.5 hit the boss
cap drafting a 39 KB spec and wasted the $0.25. These tests hold that each flag reaches the CLI's
argv (or the subprocess timeout), is validated before anything is spent, is recorded on `started`
so `resume` calls the roles with it, and that budget accounting charges a lost role call at the
cap it was really given. Defaults stay as they were.
"""

import pytest
from docs_support import run_cli
from test_pipeline import EXIT_INTERRUPTED, EXIT_OK, critic_finds, every_role, finding, ok

from antstreet import boss, budget, cli
from antstreet.errors import Outcome
from antstreet.ledger import EventType, LedgerWriter, read_events
from antstreet.pipeline import BY_OPTION, Caps, Setup, recorded_setup
from antstreet.roles import registry
from antstreet.roles.base import RoleError
from antstreet.roles.examiner import run_examiner
from antstreet.rundir import RunPaths
from antstreet.stream import Usage
from antstreet.termsheet import CheckSpec, Round, Task, TermSheet
from antstreet.worker import usd

USAGE = cli.EXIT_USAGE


def logged(fx, who):
    return [c for c in fx.calls(full=True) if c["who"] == who]


# --- validation: refused before anything is spent ---------------------------------------------


@pytest.mark.parametrize(
    "flag",
    [
        ("--boss-cap", "0"),
        ("--boss-cap", "-1"),
        ("--boss-cap", "abc"),
        ("--boss-cap", "5.000001"),
        ("--boss-timeout", "0"),
        ("--boss-timeout", "-5"),
        ("--boss-timeout", "nan"),
        ("--boss-timeout", "3600.5"),
        ("--boss-timeout", "soon"),
        ("--role-cap", "critic"),
        ("--role-cap", "nosuch=1.00"),
        ("--role-cap", "critic=0"),
        ("--role-cap", "critic=5.01"),
    ],
)
def test_a_cap_out_of_bounds_or_malformed_is_a_usage_error(tmp_path, flag):
    with pytest.raises(SystemExit) as raised:
        run_cli(tmp_path, ["fund", "x", "--budget", "0.50", "--roles", "critic", *flag])
    assert raised.value.code == USAGE


def test_the_bounds_themselves_are_accepted():
    assert cli._call_cap_arg("5.00") == boss.MAX_CAP_MICROS
    assert cli._timeout_arg("3600") == boss.MAX_TIMEOUT_S
    assert cli._role_cap_arg(" critic =0.000001") == ("critic", 1)


@pytest.mark.parametrize(
    ("extra", "said"),
    [
        (["--role-cap", "critic=1.00"], "which this run does not call"),
        (["--role-cap", "examiner=1.00"], "the examiner comes with --held-out"),
        (
            ["--roles", "critic", "--role-cap", "critic=1", "--role-cap", "critic=2"],
            "more than once",
        ),
    ],
)
def test_a_role_cap_that_would_do_nothing_or_twice_is_refused_with_no_run_folder(
    tmp_path, extra, said
):
    code, run_dir, out = run_cli(tmp_path, ["fund", "x", "--budget", "0.50", *extra])
    assert code == USAGE and run_dir is None
    assert any(said in line for line in out)


# --- the boss's call ---------------------------------------------------------------------------


def test_defaults_are_unchanged_and_nothing_extra_is_recorded(fx):
    fx.set("critic", ok({"findings": []}))
    assert fx.fund("--roles", "critic").code == EXIT_OK
    assert [c["cap"] for c in logged(fx, "boss")] == [usd(boss.DEFAULT_CAP_MICROS)]
    assert [c["cap"] for c in logged(fx, "critic")] == [usd(400_000)]
    [started] = fx.events(EventType.STARTED)
    assert "caps" not in started.data["roles"]
    assert recorded_setup(fx.events()).caps == Caps()


def test_the_boss_cap_and_timeout_reach_the_boss_call(fx, monkeypatch):
    timeouts = []
    real = boss._call

    def spy(argv, env, timeout_s):
        timeouts.append(timeout_s)
        return real(argv, env, timeout_s)

    monkeypatch.setattr(boss, "_call", spy)
    out = fx.fund("--boss-cap", "1.25", "--boss-timeout", "900")
    assert out.code == EXIT_OK
    assert [c["cap"] for c in logged(fx, "boss")] == [usd(1_250_000)]
    assert timeouts == [900.0]
    assert "Caps set for this run: boss calls capped at $1.25; boss calls time out after 900s." in (
        out.text
    )
    [started] = fx.events(EventType.STARTED)
    assert started.data["roles"] == {
        "names": [],
        "model": "haiku",
        "thinking_tokens": None,
        "caps": {"boss_micros": 1_250_000, "boss_timeout_s": 900.0},
    }


def test_without_the_flags_the_boss_keeps_its_300s_timeout(fx, monkeypatch):
    timeouts = []
    real = boss._call
    monkeypatch.setattr(boss, "_call", lambda a, e, t: timeouts.append(t) or real(a, e, t))
    fx.fund()
    assert timeouts == [boss.DEFAULT_TIMEOUT_S]


# --- every role, and resume --------------------------------------------------------------------


def test_each_roles_own_cap_reaches_its_call_and_its_ledger_event(fx):
    every_role(fx)
    chosen = sorted(set(registry()) - set(BY_OPTION) - {"spec_mapper"})
    # a different amount per role, so a cap given to the wrong role is caught
    caps = {name: f"1.{n:02d}" for n, name in enumerate(chosen, start=1)}
    flags = [arg for name, amount in caps.items() for arg in ("--role-cap", f"{name}={amount}")]
    assert fx.fund("--roles", "all", *flags, answers={"Task": "d"}).code == EXIT_OK
    for name, amount in caps.items():
        calls = logged(fx, name)
        micros = cli.usd_arg(amount)
        assert calls and {c["cap"] for c in calls} == {usd(micros)}, name
        events = fx.role_calls(name)
        assert events and {e.data["cap_micros"] for e in events} == {micros}, name
    assert [c["cap"] for c in logged(fx, "boss")] == []  # the staged draft replaced the boss


def test_resume_calls_the_roles_with_the_caps_the_run_was_started_with(fx):
    critic_finds(fx, finding())
    out = fx.fund(
        "--roles", "critic", "--role-cap", "critic=1.50", answers={"Add these": KeyboardInterrupt}
    )
    assert out.code == EXIT_INTERRUPTED
    assert fx.run("resume").code == EXIT_OK  # the unanswered findings: the critic is asked again
    assert [c["cap"] for c in logged(fx, "critic")] == [usd(1_500_000)] * 2
    assert [e.data["cap_micros"] for e in fx.role_calls("critic")] == [1_500_000] * 2


def test_recorded_caps_load_and_bad_ones_fall_back_to_the_defaults():
    def setup(caps):
        from antstreet.ledger import Event

        raw = {"names": ["critic"], "model": "m", "thinking_tokens": None}
        if caps is not None:
            raw["caps"] = caps
        event = Event(run="r", round=0, actor="boss", event=EventType.STARTED, data={"roles": raw})
        return recorded_setup([event])

    assert setup(None) == Setup(("critic",), "m", None)  # a ledger from before the flags
    good = {"boss_micros": 2_000_000, "boss_timeout_s": 600, "roles": {"critic": 900_000}}
    assert setup(good).caps == Caps(2_000_000, 600.0, (("critic", 900_000),))
    assert setup(good).caps.data() == good | {"boss_timeout_s": 600.0}
    bad = {
        "boss_micros": boss.MAX_CAP_MICROS + 1,
        "boss_timeout_s": True,
        "roles": {"critic": 0, "judge": "1", "tester": 10**12},
    }
    assert setup(bad).caps == Caps()
    assert setup(["not", "an", "object"]).caps == Caps()
    assert setup({"boss_timeout_s": float("nan")}).caps == Caps()


# --- the examiner: its round-1 budget check and its lost-call charge ---------------------------

C01 = "from rev import reverse\n\ndef test_word():\n    assert reverse('ab') == 'ba'\n"


def examiner_run(tmp_path, monkeypatch, role_caps, examine):
    from antstreet.roles import examiner

    paths = RunPaths(tmp_path)
    paths.checks.mkdir(parents=True)
    (paths.checks / "test_c01.py").write_text(C01)
    sheet = TermSheet(
        "Reverse a string.",
        300_000,
        (Round(1, 300_000, 1),),
        (CheckSpec("c01", "reverses a word", "test_c01.py", "t1"),),
        (Task("t1", "Create rev.py with reverse(s).", ("rev.py",)),),
    )
    monkeypatch.setattr(examiner, "examine", examine)
    with LedgerWriter(paths.ledger) as ledger:
        run_examiner(
            sheet, paths, ledger, "r1", n=1, env={"HOME": "/h"}, model="haiku",
            role_caps=role_caps, say=lambda _: None,
        )  # fmt: skip
    return sheet, read_events(paths.ledger)


def test_a_higher_examiner_cap_is_what_the_round_1_room_check_uses(tmp_path, monkeypatch):
    def never(*_, **__):
        raise AssertionError("the examiner must not be called")

    # $0.30 in round 1: the default $0.15 cap leaves $0.15, enough for a slice; $0.25 does not
    _, events = examiner_run(tmp_path, monkeypatch, {"examiner": 250_000}, never)
    [call] = events
    assert call.data["outcome"] == "skipped" and call.data["cap_micros"] == 250_000


def test_a_lost_examiner_call_is_charged_at_the_cap_it_was_given(tmp_path, monkeypatch):
    seen = {}

    def lost(*_, role_caps=None, **__):
        seen["role_caps"] = role_caps
        raise RoleError("examiner", "killed", Outcome.TIMEOUT, Usage(None, 0, 0, 0))

    sheet, events = examiner_run(tmp_path, monkeypatch, {"examiner": 70_000}, lost)
    assert seen["role_caps"] == {"examiner": 70_000}
    [call] = events
    assert call.cost_micros is None and call.data["cap_micros"] == 70_000
    assert budget.remaining(sheet, events, 1) == 300_000 - 70_000


def test_fund_gives_the_examiner_its_cap_through_held_out(fx):
    from test_pipeline import EXAMINED, GOOD

    fx.set("examiner", ok(EXAMINED))
    fx.set("worker", {"files": {"rev.py": GOOD}})
    assert fx.fund("--held-out", "1", "--role-cap", "examiner=0.07").code == EXIT_OK
    assert [c["cap"] for c in logged(fx, "examiner")] == [usd(70_000)]
    [call] = fx.role_calls("examiner")
    assert call.data["cap_micros"] == 70_000 and call.data["kept"] == 1


@pytest.fixture
def fx(tmp_path):
    from test_pipeline import Fx

    return Fx(tmp_path)
