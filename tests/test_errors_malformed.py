"""classify reads JSON the CLI wrote, so any field can have any type; it must never raise, and a
field it cannot read must not turn into success."""

import itertools

import pytest

from boss.errors import Outcome, RunSignals, classify

GOOD = {"type": "result", "subtype": "success", "is_error": False}
FAILED = GOOD | {"is_error": True}
JUNK = [None, 0, 1, -1, 1.5, float("nan"), True, False, "", "x", [], [1, [2]], {}, {"a": 1}, (1,)]


def run(result=None, **kw):
    return classify(RunSignals(result=FAILED | (result or {}), **kw))


@pytest.mark.parametrize("field", ["subtype", "terminal_reason", "stop_reason", "is_error"])
@pytest.mark.parametrize("junk", JUNK, ids=repr)
def test_a_result_field_of_any_type_never_raises(field, junk):
    assert isinstance(classify(RunSignals(result=GOOD | {field: junk})), Outcome)
    assert isinstance(run({field: junk}), Outcome)


@pytest.mark.parametrize("field", ["api_error_status", "result", "errors"])
@pytest.mark.parametrize("junk", JUNK + [[["nested"]], [None, 3]], ids=repr)
def test_an_error_detail_of_any_type_never_raises(field, junk):
    assert isinstance(run({field: junk}), Outcome)


@pytest.mark.parametrize(
    "field", ["retry_errors", "message_errors", "rate_limit_status", "timed_out"]
)
@pytest.mark.parametrize("junk", JUNK + [[["nested"]], [{}], [[]]], ids=repr)
def test_a_signal_of_any_type_never_raises(field, junk):
    assert isinstance(classify(RunSignals(result=FAILED, **{field: junk})), Outcome)
    assert isinstance(classify(RunSignals(result=GOOD, **{field: junk})), Outcome)


@pytest.mark.parametrize("junk", [0, 1, "x", [], [1], {}, (), object(), 3.5])
def test_a_result_that_is_not_a_mapping_is_a_crash(junk):
    assert classify(RunSignals(result=junk)) is Outcome.CRASHED


@pytest.mark.parametrize("junk", [None, 0, "", "false", "true", 1, [], {}, "False"])
def test_is_error_that_is_not_the_bool_false_is_not_success(junk):
    assert classify(RunSignals(result=GOOD | {"is_error": junk})) is not Outcome.COMPLETED


def test_a_missing_is_error_is_not_success():
    assert classify(RunSignals(result={"type": "result", "subtype": "success"})) is Outcome.CRASHED


@pytest.mark.parametrize("junk", [5, None, {}, {"a": "b"}, 1.5, True, [], [5], [None]])
def test_errors_of_the_wrong_type_read_as_no_information(junk):
    assert run({"errors": junk}) is Outcome.CRASHED


def test_errors_still_read_when_well_formed_or_a_lone_string():
    assert run({"errors": ["You've hit your limit"]}) is Outcome.USAGE_LIMIT
    assert run({"errors": "You've hit your limit"}) is Outcome.USAGE_LIMIT
    assert run({"errors": ["ok", 7, "usage limit reached"]}) is Outcome.USAGE_LIMIT


@pytest.mark.parametrize("junk", [5, ["x"], {"a": 1}, None])
def test_result_text_of_the_wrong_type_reads_as_no_information(junk):
    assert run({"result": junk}) is Outcome.CRASHED


@pytest.mark.parametrize("junk", ["401", "429", 401.0, True, [401], {}, 4.29])
def test_an_api_status_that_is_not_an_int_is_unknown_not_login_or_rate_limit(junk):
    assert run({"api_error_status": junk}) is Outcome.CRASHED


@pytest.mark.parametrize("junk", [5, None, [["a"]], [{}], [[]], {"authentication_failed": 1}])
def test_retry_errors_of_the_wrong_type_read_as_none(junk):
    assert run(retry_errors=junk) is Outcome.CRASHED


def test_retry_errors_still_read_when_well_formed():
    assert run(retry_errors=("authentication_failed",)) is Outcome.LOGIN
    assert run(retry_errors=["rate_limit"]) is Outcome.RATE_LIMITED


@pytest.mark.parametrize("junk", [[], ["rejected"], 1, {"status": "rejected"}, None])
def test_a_rate_limit_status_that_is_not_the_string_rejected_is_not_a_usage_limit(junk):
    assert run(rate_limit_status=junk) is Outcome.CRASHED


@pytest.mark.parametrize("junk", [1, "x", [], {}, None, "rate_limit"])
def test_subtype_and_terminal_reason_of_the_wrong_type_are_ignored(junk):
    assert run({"subtype": junk, "terminal_reason": junk}) is Outcome.CRASHED


def test_a_few_junk_fields_at_once_never_raise():
    for combo in itertools.product(JUNK[:8], repeat=3):
        result = FAILED | {"errors": combo[0], "api_error_status": combo[1], "result": combo[2]}
        assert isinstance(classify(RunSignals(result=result, retry_errors=combo[0])), Outcome)
