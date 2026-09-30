import json

import pytest

from boss.errors import INFRASTRUCTURE, Outcome
from boss.rule import Decision, FiringPolicy, SliceRecord, Verdict, decide

CHECKS = frozenset({"a", "b", "c"})
POLICY = FiringPolicy(stall_slices=2, max_slices=6)


def rec(
    n: int,
    passing: set[str] | frozenset[str] = frozenset(),
    outcome: Outcome = Outcome.COMPLETED,
    status: str = "continuing",
    cost: int | None = 100,
    disputed: set[str] | frozenset[str] = frozenset(),
) -> SliceRecord:
    return SliceRecord(n, cost, outcome, status, frozenset(passing), frozenset(disputed))


def run(*history: SliceRecord, policy: FiringPolicy = POLICY) -> Verdict:
    return decide(CHECKS, list(history), policy)


def test_empty_history_raises() -> None:
    with pytest.raises(ValueError):
        decide(CHECKS, [], POLICY)


def test_empty_task_checks_raises() -> None:
    with pytest.raises(ValueError):
        decide(frozenset(), [rec(1, {"a"})], POLICY)


def test_done_on_first_slice() -> None:
    v = run(rec(1, {"a", "b", "c"}, cost=250))
    assert v.decision is Decision.DONE
    assert v.reason == "all checks pass"
    assert v.evidence == {
        "counted_slices": 1,
        "stalled_slices": 0,
        "passing": ["a", "b", "c"],
        "best": ["a", "b", "c"],
        "missing": [],
        "disputed": [],
        "spent_micros": 250,
        "unknown_cost_slices": 0,
    }


def test_done_wins_over_infrastructure() -> None:
    v = run(rec(1, {"a"}), rec(2, {"a", "b", "c"}, Outcome.API_ERROR))
    assert v.decision is Decision.DONE
    assert v.reason == "all checks pass"
    assert v.evidence["counted_slices"] == 1


def test_done_wins_over_slice_limit() -> None:
    history = [rec(1, {"a"}), rec(2, {"a", "b"}), rec(3, {"a", "b", "c"})]
    v = run(*history, policy=FiringPolicy(stall_slices=5, max_slices=3))
    assert v.decision is Decision.DONE


def test_worker_saying_done_means_nothing_without_the_checks() -> None:
    v = run(rec(1, {"a"}, status="done"))
    assert v.decision is Decision.CONTINUE
    assert v.evidence["missing"] == ["b", "c"]


@pytest.mark.parametrize("outcome", sorted(INFRASTRUCTURE))
def test_infrastructure_retries(outcome: Outcome) -> None:
    v = run(rec(1, {"a"}), rec(2, {"a"}, outcome))
    assert v.decision is Decision.RETRY
    assert v.reason == f"infrastructure: {outcome.value}"
    assert v.evidence["counted_slices"] == 1
    assert v.evidence["stalled_slices"] == 0


def test_retry_beats_blocked_and_slice_limit() -> None:
    history = [rec(1, {"a"}), rec(2, {"a"}, Outcome.RATE_LIMITED, status="blocked")]
    v = run(*history, policy=FiringPolicy(stall_slices=5, max_slices=1))
    assert v.decision is Decision.RETRY


def test_infrastructure_slices_do_not_consume_the_stall_count() -> None:
    # counted: s1 (progress), s4 (no progress); s2 and s3 are infrastructure and uncounted.
    # Were they counted, stalled would be 3 >= 2 and this would fire.
    v = run(
        rec(1, {"a"}),
        rec(2, set(), Outcome.API_ERROR),
        rec(3, set(), Outcome.LOGIN),
        rec(4, {"a"}),
    )
    assert v.decision is Decision.CONTINUE
    assert v.reason == "progressing"
    assert v.evidence["counted_slices"] == 2
    assert v.evidence["stalled_slices"] == 1


def test_infrastructure_slice_between_stalls_does_not_break_the_run() -> None:
    v = run(rec(1, {"a"}), rec(2, {"a"}), rec(3, {"a"}, Outcome.API_ERROR), rec(4, {"a"}))
    assert v.decision is Decision.FIRE
    assert v.reason == "no progress"
    assert v.evidence["counted_slices"] == 3
    assert v.evidence["stalled_slices"] == 2


def test_check_first_seen_in_an_infrastructure_slice_is_not_later_progress() -> None:
    v = run(rec(1, set()), rec(2, {"a"}, Outcome.API_ERROR), rec(3, {"a"}))
    assert v.evidence["counted_slices"] == 2
    assert v.evidence["stalled_slices"] == 2
    assert v.evidence["best"] == ["a"]


def test_blocked_escalates_even_with_progress() -> None:
    v = run(rec(1, {"a"}), rec(2, {"a", "b"}, status="blocked"))
    assert v.decision is Decision.ESCALATE
    assert v.reason == "blocked"
    assert v.evidence["stalled_slices"] == 0


def test_blocked_beats_slice_limit() -> None:
    v = run(rec(1, {"a"}), rec(2, {"a"}, status="blocked"), policy=FiringPolicy(2, 2))
    assert v.decision is Decision.ESCALATE
    assert v.reason == "blocked"


def test_refusal_escalates() -> None:
    v = run(rec(1, {"a"}), rec(2, {"a", "b"}, Outcome.REFUSAL))
    assert v.decision is Decision.ESCALATE
    assert v.reason == "refusal"


def test_refusal_beats_stall() -> None:
    v = run(rec(1, {"a"}), rec(2, {"a"}), rec(3, {"a"}, Outcome.REFUSAL))
    assert v.decision is Decision.ESCALATE
    assert v.reason == "refusal"


def test_stall_of_exactly_stall_slices_fires() -> None:
    v = run(rec(1, {"a"}), rec(2, {"a"}), rec(3, {"a"}))
    assert v.decision is Decision.FIRE
    assert v.reason == "no progress"
    assert v.evidence["stalled_slices"] == 2
    assert v.evidence["counted_slices"] == 3


def test_one_fewer_than_stall_slices_continues() -> None:
    v = run(rec(1, {"a"}), rec(2, {"a"}))
    assert v.decision is Decision.CONTINUE
    assert v.reason == "progressing"
    assert v.evidence["stalled_slices"] == 1


def test_first_slice_with_nothing_passing_is_a_stall() -> None:
    v = run(rec(1, set()), policy=FiringPolicy(stall_slices=1, max_slices=6))
    assert v.decision is Decision.FIRE
    assert v.reason == "no progress"
    assert v.evidence["stalled_slices"] == 1


def test_progress_resets_the_stall_count() -> None:
    v = run(rec(1, {"a"}), rec(2, {"a"}), rec(3, {"a", "b"}), rec(4, {"a", "b"}))
    assert v.decision is Decision.CONTINUE
    assert v.evidence["stalled_slices"] == 1
    assert v.evidence["counted_slices"] == 4


def test_regression_is_not_progress() -> None:
    v = run(rec(1, {"a", "b"}), rec(2, {"a"}), policy=FiringPolicy(stall_slices=1, max_slices=6))
    assert v.decision is Decision.FIRE
    assert v.reason == "no progress"
    assert v.evidence["stalled_slices"] == 1
    assert v.evidence["passing"] == ["a"]
    assert v.evidence["best"] == ["a", "b"]
    assert v.evidence["missing"] == ["b", "c"]


def test_regression_alone_does_not_fire() -> None:
    v = run(rec(1, {"a", "b"}), rec(2, {"a"}))
    assert v.decision is Decision.CONTINUE
    assert v.evidence["stalled_slices"] == 1


def test_recovering_a_regressed_check_is_not_progress() -> None:
    v = run(rec(1, {"a", "b"}), rec(2, {"a"}), rec(3, {"a", "b"}))
    assert v.decision is Decision.FIRE
    assert v.evidence["stalled_slices"] == 2


def test_slice_limit_fires_even_when_progressing() -> None:
    v = run(rec(1, {"a"}), rec(2, {"a", "b"}), policy=FiringPolicy(stall_slices=5, max_slices=2))
    assert v.decision is Decision.FIRE
    assert v.reason == "slice limit"
    assert v.evidence["stalled_slices"] == 0
    assert v.evidence["counted_slices"] == 2


def test_slice_limit_ignores_infrastructure_slices() -> None:
    history = [rec(1, {"a"}), rec(2, set(), Outcome.API_ERROR), rec(3, {"a", "b"})]
    v = run(*history, policy=FiringPolicy(stall_slices=5, max_slices=3))
    assert v.decision is Decision.CONTINUE
    assert v.evidence["counted_slices"] == 2


def test_slice_limit_reason_wins_over_no_progress() -> None:
    v = run(rec(1, {"a"}), rec(2, {"a"}), rec(3, {"a"}), policy=FiringPolicy(2, 3))
    assert v.decision is Decision.FIRE
    assert v.reason == "slice limit"


@pytest.mark.parametrize(
    "outcome", [Outcome.CAPPED, Outcome.TIMEOUT, Outcome.CRASHED, Outcome.MAX_TURNS]
)
def test_non_infrastructure_failures_are_counted(outcome: Outcome) -> None:
    v = run(rec(1, {"a"}, outcome), rec(2, {"a"}, outcome))
    assert v.decision is Decision.CONTINUE
    assert v.evidence["counted_slices"] == 2
    assert v.evidence["stalled_slices"] == 1
    v = run(rec(1, {"a"}, outcome), rec(2, {"a"}, outcome), rec(3, {"a"}, outcome))
    assert v.decision is Decision.FIRE
    assert v.reason == "no progress"
    assert v.evidence["counted_slices"] == 3


def test_unknown_costs_are_zero_and_counted() -> None:
    v = run(rec(1, {"a"}, cost=300), rec(2, {"a", "b"}, cost=None), rec(3, {"a", "b"}, cost=50))
    assert v.evidence["spent_micros"] == 350
    assert v.evidence["unknown_cost_slices"] == 1


def test_infrastructure_slice_costs_are_included() -> None:
    v = run(rec(1, {"a"}, cost=10), rec(2, {"a"}, Outcome.API_ERROR, cost=5))
    assert v.evidence["spent_micros"] == 15


def test_evidence_shape_and_json() -> None:
    v = run(rec(1, {"b"}), rec(2, {"a", "b"}, cost=None))
    assert v.evidence == {
        "counted_slices": 2,
        "stalled_slices": 0,
        "passing": ["a", "b"],
        "best": ["a", "b"],
        "missing": ["c"],
        "disputed": [],
        "spent_micros": 100,
        "unknown_cost_slices": 1,
    }
    assert json.loads(json.dumps(v.evidence)) == v.evidence


@pytest.mark.parametrize("kwargs", [{"stall_slices": 0}, {"max_slices": 0}, {"stall_slices": -1}])
def test_firing_policy_rejects_values_below_one(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        FiringPolicy(**kwargs)


def test_firing_policy_accepts_one() -> None:
    assert FiringPolicy(stall_slices=1, max_slices=1).max_slices == 1


# Disputed checks. Pilot finding: the boss wrote wrong checks, and correct workers stalled on
# them until the rule fired them. A dispute sends the check to the investor instead.


def test_a_worker_whose_only_failing_check_is_disputed_is_escalated_not_fired() -> None:
    v = run(rec(1, {"a", "b"}), rec(2, {"a", "b"}), rec(3, {"a", "b"}, disputed={"c"}))
    assert (v.decision, v.reason) == (Decision.ESCALATE, "disputed")
    assert v.evidence["disputed"] == ["c"] and v.evidence["stalled_slices"] == 2
    undisputed = run(rec(1, {"a", "b"}), rec(2, {"a", "b"}), rec(3, {"a", "b"}))
    assert (undisputed.decision, undisputed.reason) == (Decision.FIRE, "no progress")


def test_a_dispute_never_makes_a_check_pass_or_a_task_done() -> None:
    v = run(rec(1, disputed={"a", "b", "c"}))
    assert v.decision is Decision.ESCALATE
    assert v.evidence["passing"] == [] and v.evidence["missing"] == ["a", "b", "c"]


def test_a_dispute_does_not_excuse_the_other_failing_checks() -> None:
    assert run(rec(1, {"a"}, disputed={"c"})).decision is Decision.CONTINUE
    stalled = run(rec(1, {"a"}, disputed={"c"}), rec(2, {"a"}), rec(3, {"a"}))
    assert (stalled.decision, stalled.reason) == (Decision.FIRE, "no progress")
    assert stalled.evidence["disputed"] == ["c"]


def test_a_dispute_stands_in_later_slices_until_its_check_passes() -> None:
    later = run(rec(1, {"a"}, disputed={"c"}), rec(2, {"a", "b"}))
    assert (later.decision, later.reason) == (Decision.ESCALATE, "disputed")
    withdrawn = run(rec(1, {"a"}, disputed={"c"}), rec(2, {"a", "c"}))
    assert withdrawn.decision is Decision.CONTINUE and withdrawn.evidence["disputed"] == []
    done = run(rec(1, {"a"}, disputed={"c"}), rec(2, {"a", "b", "c"}))
    assert done.decision is Decision.DONE


def test_a_dispute_of_a_check_outside_the_task_counts_for_nothing() -> None:
    v = run(rec(1, {"a", "b"}, disputed={"zzz"}), rec(2, {"a", "b"}), rec(3, {"a", "b"}))
    assert (v.decision, v.reason) == (Decision.FIRE, "no progress")
    assert v.evidence["disputed"] == []


def test_infrastructure_and_blocked_are_decided_before_a_dispute() -> None:
    retry = run(rec(1, {"a", "b"}, outcome=Outcome.RATE_LIMITED, disputed={"c"}))
    assert retry.decision is Decision.RETRY
    blocked = run(rec(1, {"a", "b"}, status="blocked", disputed={"c"}))
    assert (blocked.decision, blocked.reason) == (Decision.ESCALATE, "blocked")


def test_a_dispute_is_decided_before_the_slice_limit() -> None:
    policy = FiringPolicy(stall_slices=9, max_slices=1)
    v = run(rec(1, {"a", "b"}, disputed={"c"}), policy=policy)
    assert (v.decision, v.reason) == (Decision.ESCALATE, "disputed")
    assert run(rec(1, {"a", "b"}), policy=policy).reason == "slice limit"
