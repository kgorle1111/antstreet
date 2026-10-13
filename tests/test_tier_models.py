"""`--tier-models`: each dispatch tier launched on a pinned model id, never the CLI's alias.

E9 was confounded because the `haiku` alias moved to a new model mid-run; a routed run that pins
its tiers launches the same model on every hire, a step up and a resume included.
"""

import pytest
from test_firm import BAD, C01, C02, GOOD, STARTED, run, step
from test_firm_dispatch import ModelScript, hired, planned

from antstreet import dispatch
from antstreet.dispatch import DispatchPolicy, DispatchView, RunLevel
from antstreet.firm import FirmConfig, config_data, config_from_data
from antstreet.rundir import RunPaths

PINS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
PINNED = FirmConfig(dispatch=True, tier_models=PINS)


@pytest.fixture
def paths(tmp_path):
    p = RunPaths(tmp_path / "run")
    p.checks.mkdir(parents=True)
    for name, code in (("test_c01.py", C01), ("test_c02.py", C02)):
        (p.checks / name).write_text(code)
    return p


# --- parsing and validation ---


def test_a_full_mapping_parses_with_spaces_around_its_parts():
    text = "haiku=claude-haiku-5-5, sonnet = claude-sonnet-5-5,opus=claude-opus-5-5"
    assert dispatch.parse_tier_models(text) == PINS


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("mini=claude-haiku-5-5", "'mini' is not one of ['haiku', 'sonnet', 'opus']"),
        ("haiku=", "haiku='' is not a model id"),
        ("haiku=claude-haiku-5-5;rm -rf", "is not a model id"),
        ("haiku=$(id)", "is not a model id"),
        ("haiku=-claude-haiku", "is not a model id"),  # would read as an option of the CLI
        ("haiku=claude-opus-5-5", "haiku=claude-opus-5-5 is not a haiku model"),
        ("haiku=claude-haiku-5-5,haiku=claude-haiku-4-5", "tier 'haiku' is given twice"),
        ("haiku", "'haiku' is not TIER=MODEL"),
        ("", "'' is not TIER=MODEL"),
    ],
)
def test_a_mapping_that_cannot_pin_the_ladder_is_refused_with_the_reason(text, said):
    with pytest.raises(ValueError) as caught:
        dispatch.parse_tier_models(text)
    assert said in str(caught.value)


def test_a_tampered_ledger_mapping_is_refused_when_the_config_is_loaded():
    data = config_data(PINNED) | {"tier_models": {"haiku": "claude-opus-5-5"}}
    with pytest.raises(ValueError, match="not a haiku model"):
        config_from_data(data)
    with pytest.raises(ValueError, match="needs dispatch"):
        FirmConfig(tier_models=PINS)
    with pytest.raises(ValueError, match="tier_models"):
        DispatchPolicy("sonnet", 100_000, tier_models={"opus": "x y"})


# --- the ledger ---


def test_the_mapping_is_recorded_on_started_and_read_back():
    data = config_data(PINNED)
    assert data["tier_models"] == PINS
    assert config_from_data(data) == PINNED
    assert PINNED.dispatch_policy().model_for("sonnet") == "claude-sonnet-5-5"


def test_a_ledger_written_before_the_key_existed_loads_and_launches_the_aliases():
    data = config_data(FirmConfig(dispatch=True))
    assert "tier_models" not in data  # an unpinned run's ledger is what it always was
    old = config_from_data(data)
    assert old.tier_models is None
    assert [old.dispatch_policy().model_for(t) for t in dispatch.TIERS] == list(dispatch.TIERS)


# --- the worker's argv ---


def test_each_hire_launches_its_tiers_pinned_id_and_the_ledger_keeps_the_tier(paths):
    worker = ModelScript(step(BAD), step(BAD), step(GOOD, "done"))
    report, _ = run(paths, worker, planned(), config=PINNED)
    assert report.all_passed
    assert [s.model for s in worker.specs] == ["claude-haiku-5-5"] * 2 + ["claude-sonnet-5-5"]
    first, second = hired(paths)
    assert first["model"] == "claude-haiku-5-5" and first["dispatch"]["tier"] == "haiku"
    assert second["model"] == "claude-sonnet-5-5" and second["dispatch"]["tier"] == "sonnet"
    assert second["dispatch"]["from_tier"] == "haiku"


def test_a_resumed_run_hires_the_step_up_on_the_pin_its_started_config_recorded(paths):
    first = ModelScript(step(BAD), KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        run(paths, first, planned(), config=PINNED)
    resumed = ModelScript(step(BAD), step(GOOD, "done"))
    resumed.totals = dict(first.totals)
    report, _ = run(paths, resumed, planned(), config=STARTED)
    assert report.all_passed
    launched = [s.model for s in first.specs + resumed.specs]
    assert launched == ["claude-haiku-5-5"] * 3 + ["claude-sonnet-5-5"]


# --- what the investor reads ---


def test_the_term_sheet_shows_the_pinned_id_and_the_whole_mapping():
    policy = DispatchPolicy("sonnet", 100_000, tier_models=PINS)
    view = DispatchView(policy, RunLevel("claude-opus-5-5", "off", 0, 1), 2, {})
    lines = dispatch.render_table(planned(), view)
    row = next(line for line in lines if line.startswith("t1 "))
    assert "claude-haiku-5-5" in row
    assert (
        "Pinned models (--tier-models): haiku=claude-haiku-5-5, opus=claude-opus-5-5, "
        "sonnet=claude-sonnet-5-5"
    ) in lines


def test_without_pins_the_table_is_unchanged():
    view = DispatchView(DispatchPolicy("sonnet", 100_000), RunLevel("haiku", "off", 0, 1), 2, {})
    lines = dispatch.render_table(planned(), view)
    assert not any("Pinned" in line for line in lines)
    assert any(line.startswith("t1    builder  haiku  default") for line in lines)
