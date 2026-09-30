"""Funding rounds by story priority: hand-worked cases, what the count can and cannot guarantee,
and validity for any input."""

import random
from itertools import combinations

import pytest

from boss.budget import min_round_budget, plan_rounds, unlocked
from boss.roles.planning import plan_rounds_by_priority
from boss.roles.stories import Stories, parse_stories
from boss.termsheet import CheckSpec, Round, TermSheet, _money_problems, _round_problems

FLOOR = min_round_budget()


def stories_of(*priorities: tuple[str, int]) -> Stories:
    """S1, S2, ... with the given priority and number of criteria: S1.1, S1.2, ..."""
    return parse_stories(
        {
            "stories": [
                {
                    "id": f"S{n}",
                    "as_a": "a",
                    "i_want": "b",
                    "so_that": "c",
                    "priority": priority,
                    "criteria": [
                        {"id": f"S{n}.{m}", "given": "g", "when": "w", "then": "t", "source": "s"}
                        for m in range(1, count + 1)
                    ],
                }
                for n, (priority, count) in enumerate(priorities, start=1)
            ]
        }
    )


def checks_citing(*cited: tuple[str, ...]) -> tuple[CheckSpec, ...]:
    return tuple(
        CheckSpec(f"c{n:02d}", "d", f"test_c{n:02d}.py", "t1", criteria)
        for n, criteria in enumerate(cited, start=1)
    )


# S1 must (S1.1, S1.2), S2 should (S2.1), S3 could (S3.1); six checks:
#   c01 S1.1, c02 S1.2, c03 S1.1+S3.1 (must, the higher of the two)  -> M = 3
#   c04 S2.1, c05 S3.1+S2.1 (should)                                  -> S = 2
#   c06 S3.1                                                          -> C = 1
STORIES = stories_of(("must", 2), ("should", 1), ("could", 1))
CHECKS = checks_citing(
    ("S1.1",), ("S1.2",), ("S1.1", "S3.1"), ("S2.1",), ("S3.1", "S2.1"), ("S3.1",)
)


def test_three_priorities_give_three_rounds_unlocking_at_3_then_5_then_6_checks():
    # floor 105_000 per round; the other 1_000_000 - 3 * 105_000 = 685_000 is split 3 : 2 : 1,
    # 342_500 + 228_333 + 114_166 = 684_999, and the last micro-dollar goes to round 1.
    assert plan_rounds_by_priority(STORIES, CHECKS, 1_000_000, 3) == (
        Round(1, 105_000 + 342_501, 3),
        Round(2, 105_000 + 228_333, 5),
        Round(3, 105_000 + 114_166, 6),
    )


def test_fewer_rounds_than_priorities_merge_the_last_ones_and_keep_must_first():
    # unlocks 3 and 6, weights 3 : 3, 790_000 to share
    assert plan_rounds_by_priority(STORIES, CHECKS, 1_000_000, 2) == (
        Round(1, 105_000 + 395_000, 3),
        Round(2, 105_000 + 395_000, 6),
    )
    assert plan_rounds_by_priority(STORIES, CHECKS, 1_000_000, 1) == (Round(1, 1_000_000, 6),)


def test_more_rounds_than_priorities_gives_one_round_per_priority():
    assert plan_rounds_by_priority(STORIES, CHECKS, 1_000_000, 9) == plan_rounds_by_priority(
        STORIES, CHECKS, 1_000_000, 3
    )


def test_a_budget_too_small_for_n_rounds_drops_rounds_from_the_end_not_below_the_minimum():
    # 3 rounds need 315_000; 300_000 funds two rounds of the floor plus 45_000 each
    assert plan_rounds_by_priority(STORIES, CHECKS, 300_000, 3) == (
        Round(1, 150_000, 3),
        Round(2, 150_000, 6),
    )
    # 150_000 cannot fund two rounds, so it is one
    assert plan_rounds_by_priority(STORIES, CHECKS, 150_000, 3) == (Round(1, 150_000, 6),)
    assert plan_rounds_by_priority(STORIES, CHECKS, 2, 5) == (Round(1, 2, 6),)


def test_a_priority_without_checks_adds_no_round():
    # S1 (must) has no check: only S2 (should, 2 checks) and S3 (could, 1 check) have
    stories = stories_of(("must", 1), ("should", 1), ("could", 1))
    checks = checks_citing(("S2.1",), ("S2.1",), ("S3.1",))
    assert plan_rounds_by_priority(stories, checks, 500_000, 2) == (
        Round(1, 105_000 + 193_334, 2),
        Round(2, 105_000 + 96_666, 3),
    )


def test_a_check_with_no_known_criterion_counts_as_could_and_one_known_is_enough():
    stories = stories_of(("must", 1), ("should", 1))
    checks = checks_citing(("S1.1",), ("S9.9",), (), ("S9.9", "S2.1"))
    # c01 must; c04 should (the unknown citation is ignored); c02 and c03 could: tiers 1, 2, 4
    assert plan_rounds_by_priority(stories, checks, 1_000_000, 3) == (
        Round(1, 105_000 + 171_250, 1),
        Round(2, 105_000 + 171_250, 2),
        Round(3, 105_000 + 342_500, 4),
    )


def test_all_checks_of_one_priority_give_nothing_to_split_on_so_the_house_plan_is_used():
    stories = stories_of(("must", 2))
    checks = checks_citing(("S1.1",), ("S1.2",), ("S1.1",), ("S1.2",))
    assert plan_rounds_by_priority(stories, checks, 1_000_000, 2) == plan_rounds(1_000_000, 4, 2)
    assert plan_rounds_by_priority(stories, checks, 1_000_000, 2) == (
        Round(1, 500_000, 2),
        Round(2, 500_000, 4),
    )


def test_checks_that_cite_nothing_fall_back_to_the_house_plan():
    plain = checks_citing((), (), (), ())
    assert plan_rounds_by_priority(STORIES, plain, 900_000, 3) == plan_rounds(900_000, 4, 3)


def test_a_story_with_a_priority_the_gate_would_refuse_is_treated_as_the_lowest():
    stories = stories_of(("must", 1), ("urgent", 1))
    checks = checks_citing(("S1.1",), ("S2.1",), ("S2.1",))
    # `urgent` counts as could: tiers 1 and 3. Read as must there would be one tier and the house
    # plan, which unlocks at 2 then 3.
    assert [r.unlock_checks for r in plan_rounds_by_priority(stories, checks, 1_000_000, 2)] == [
        1,
        3,
    ]


def test_a_budget_of_exactly_n_floors_funds_n_rounds_of_the_floor():
    assert plan_rounds_by_priority(STORIES, CHECKS, 2 * FLOOR, 2) == (
        Round(1, FLOOR, 3),
        Round(2, FLOOR, 6),
    )
    assert plan_rounds_by_priority(STORIES, CHECKS, 2 * FLOOR - 1, 2) == (
        Round(1, 2 * FLOOR - 1, 6),
    )


@pytest.mark.parametrize(
    ("budget", "n_rounds", "checks"),
    [(0, 2, CHECKS), (-1, 2, CHECKS), (100, 0, CHECKS), (100, -1, CHECKS), (100, 2, ())],
)
def test_input_that_cannot_be_planned_is_refused(budget, n_rounds, checks):
    with pytest.raises(ValueError, match="positive"):
        plan_rounds_by_priority(STORIES, checks, budget, n_rounds)


# --- what the count guarantees, and what it does not --------------------------------------------


def test_the_count_is_not_a_named_set_so_round_one_can_open_with_a_must_check_failing():
    stories = stories_of(("must", 1), ("should", 1))
    checks = checks_citing(("S1.1",), ("S2.1",), ("S2.1",), ("S2.1",))  # M = 1 of N = 4
    rounds = plan_rounds_by_priority(stories, checks, 1_000_000, 2)
    sheet = TermSheet("x", 1_000_000, rounds, checks, ())
    assert rounds[0].unlock_checks == 1
    # one passing check is enough, and it may be a `should` one: c02 passes, c01 (must) fails
    assert unlocked(sheet, 1, passing_checks=1)


def sheet_for(checks, rounds, budget) -> TermSheet:
    return TermSheet("x", budget, rounds, checks, ())


def must_indices(stories: Stories, checks) -> set[int]:
    must = {c.id for s in stories.stories if s.priority == "must" for c in s.criteria}
    return {i for i, check in enumerate(checks) if must & set(check.criteria)}


@pytest.mark.parametrize(
    "cited",
    [
        [("S1.1",), ("S2.1",), ("S2.1",), ("S2.1",)],  # M = 1 of 4
        [("S1.1",), ("S1.1",), ("S2.1",), ("S2.1",), ("S2.1",)],  # M = 2 of 5
        [("S1.1",)] * 5 + [("S2.1",)] * 2,  # M = 5 of 7
        [("S1.1",)] * 3 + [("S2.1",)] * 3,  # M = 3 of 6
    ],
)
def test_the_guarantee_is_exactly_M_minus_the_other_checks_and_no_more(cited):
    stories = stories_of(("must", 1), ("should", 1))
    checks = checks_citing(*cited)
    rounds = plan_rounds_by_priority(stories, checks, 1_000_000, 2)
    m, n = len(must_indices(stories, checks)), len(checks)
    assert rounds[0].unlock_checks == m
    fewest = min(
        len(set(passing) & must_indices(stories, checks))
        for size in range(m, n + 1)
        for passing in combinations(range(n), size)
    )
    assert fewest == max(0, m - (n - m))  # what the docstring promises, reached, not exceeded


# --- valid for any input ---------------------------------------------------------------------


def test_the_result_is_a_valid_set_of_rounds_for_any_stories_checks_budget_and_round_count():
    rng = random.Random(20260930)
    for _ in range(3_000):
        stories = stories_of(
            *[
                (rng.choice(["must", "should", "could", "odd"]), rng.randint(1, 3))
                for _ in range(rng.randint(1, 4))
            ]
        )
        ids = [c.id for c in stories.criteria()] + ["S9.9"]
        checks = checks_citing(
            *[tuple(rng.sample(ids, rng.randint(0, 2))) for _ in range(rng.randint(1, 9))]
        )
        budget = rng.choice([1, 2, 5, 104_999, 105_000, 210_000, 315_001, 999_999, 5_000_000])
        n_rounds = rng.randint(1, 6)
        rounds = plan_rounds_by_priority(stories, checks, budget, n_rounds)
        sheet = sheet_for(checks, rounds, budget)
        assert _round_problems(sheet) == [] and _money_problems(sheet) == []
        assert 1 <= len(rounds) <= min(n_rounds, budget)
        assert all(type(r.budget_micros) is int and r.budget_micros > 0 for r in rounds)
        if len(rounds) > 1 and rounds != plan_rounds(budget, len(checks), min(n_rounds, budget)):
            assert all(r.budget_micros >= FLOOR for r in rounds)  # split by priority: no dead round
