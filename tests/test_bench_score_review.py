"""Scoring a critic's verified findings against a task's reference solution: the number that
decides whether the critic is ever switched on. Real gate; no model call."""

import pytest
import test_roles_critic as shared
from test_roles_critic import CORRECT, HEAD, LEADING, QUOTE, RUN_OF_SPACES, SLEEPS, finding

from antstreet.bench.score import ReviewScore, score_review
from antstreet.bench.tasks import BenchTask
from antstreet.roles.critic import Finding, Rejected, Review

product = shared.product  # fixtures shared with the critic's tests
review_with = shared.review_with


@pytest.fixture
def task(tmp_path):
    root = tmp_path / "task" / "rev"
    (root / "reference").mkdir(parents=True)
    (root / "reference" / "rev.py").write_text(CORRECT)
    return BenchTask("rev", "reverse words", "easy", root)


def found(n, code):
    return Finding(n, "high", f"claim {n}", QUOTE, code)


def test_precision_is_the_share_of_verified_findings_whose_test_the_reference_passes(task):
    # Hand-worked. The reference splits on any whitespace and joins with one space.
    #   f01 "a  b" -> "b a": reference passes            right
    #   f02 "a b" -> "a b": reference gives "b a"        wrong (demands no reversal)
    #   f03 " a b" -> "b a": reference passes            right
    #   f04 needs rev.shout, the reference has none      wrong (AttributeError)
    #   f05 sleeps past the timeout on the reference     wrong
    review = Review(
        (
            found(1, RUN_OF_SPACES),
            found(2, HEAD + 'def test_x():\n    assert reverse_words("a b") == "a b"\n'),
            found(3, LEADING),
            found(4, "import rev\n\n\ndef test_x():\n    assert rev.shout('a') == 'A'\n"),
            found(
                5,
                SLEEPS,
            ),
        ),
        (),
        (),
    )
    # ponytail: timeout must exceed normal test execution under parallel load,
    # but stay well below SLEEPS (f05 sleeps 30s). Empirically, f01/f03 need ~5s headroom
    # under heavy pytest -n auto load; set to 10.0 for safety margin.
    score = score_review(task, review, timeout_s=10.0)
    assert score.verified == ("f01", "f02", "f03", "f04", "f05")
    assert score.wrong == ("f02", "f04", "f05") and score.right == ("f01", "f03")
    assert score.precision == 2 / 5


def test_a_review_whose_findings_all_pass_on_the_reference_has_precision_one(task):
    score = score_review(task, Review((found(1, RUN_OF_SPACES), found(2, LEADING)), (), ()))
    assert (score.wrong, score.precision) == ((), 1.0)


def test_a_review_with_nothing_verified_has_no_precision_and_runs_no_gate(tmp_path):
    missing = BenchTask("rev", "t", "easy", tmp_path / "no" / "such" / "task")
    score = score_review(missing, Review((), (Rejected(1, "c", "r"),), ()))
    assert score == ReviewScore((), ()) and score.precision is None


def test_a_critic_run_against_the_buggy_product_is_scored_against_the_reference(review_with, task):
    review, _ = review_with(
        [
            finding(RUN_OF_SPACES),
            finding(HEAD + 'def test_x():\n    assert reverse_words("a b") == "a b"\n'),
        ]
    )
    assert [f.n for f in review.verified] == [1, 2]  # both fail on the buggy product
    score = score_review(task, review)
    assert (score.wrong, score.precision) == (("f02",), 0.5)  # the reference exposes the second


def test_a_score_refuses_findings_that_are_not_among_the_verified_or_repeat():
    with pytest.raises(ValueError):
        ReviewScore(("f01",), ("f02",))
    with pytest.raises(ValueError):
        ReviewScore(("f01", "f01"), ())
