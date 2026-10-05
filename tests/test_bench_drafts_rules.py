"""Drafts made with the rules prompt (term_sheet_v3.md) keep their claims, and `--max-spend` stops
before a call that could pass the cap. A fake boss; no model calls, no spend."""

import json

from test_bench_drafts import SOUND, cell, draft_of, env  # noqa: F401  (env is a fixture)

from boss.bench import drafts
from boss.bench.drafts import INVALID, SCORED, DraftCell, settings_for


def cited(draft, *rules):
    for check in draft["checks"]:
        check["rules"] = list(rules)
    return draft


def rules_settings():
    return settings_for("term_sheet_v3.md", "haiku", None)


def test_a_draft_with_rules_keeps_the_rule_list_and_who_cites_what(env):  # noqa: F811
    env.set_drafts(**{"marker-alpha": cited(draft_of(SOUND), "R01") | {"untested": []}})
    result = cell(env, settings=rules_settings())
    assert result.status == SCORED and result.prompt == "term_sheet_v3.md"
    folder = env.out / "alpha" / "rep1"
    claims = json.loads((folder / "claims.json").read_text())
    assert claims == {"claims": {"c01": ["R01"]}, "untested": {}}
    rules = json.loads((folder / "rules.json").read_text())
    assert [r["id"] for r in rules["rules"]] == ["R01"]
    prompt = env.calls()[0]["argv"][-1]
    assert "R01: Create demo.py, marker-alpha, with f(x) returning x + 1." in prompt


def test_a_draft_that_cites_a_rule_that_does_not_exist_is_invalid_and_paid_for(env):  # noqa: F811
    env.set_drafts(**{"marker-alpha": cited(draft_of(SOUND), "R09")})
    result = cell(env, settings=rules_settings())
    assert result.status == INVALID and "unknown rule 'R09'" in result.detail
    assert result.cost_micros == 4_000
    assert not (env.out / "alpha" / "rep1" / "claims.json").exists()


def test_a_draft_without_the_rules_prompt_has_no_claims_and_no_rules_in_its_prompt(env):  # noqa: F811
    result = cell(env)
    assert result.status == SCORED
    assert not (env.out / "alpha" / "rep1" / "claims.json").exists()
    assert "Rules of the idea" not in env.calls()[0]["argv"][-1]


def test_max_spend_stops_before_a_call_that_could_pass_the_cap_and_says_so(env, capsys):  # noqa: F811
    env.set_drafts(**{"marker-alpha": draft_of(SOUND), "marker-beta": draft_of(SOUND)})
    # each call costs $0.004 and may cost up to the $0.25 cap: three fit under $0.26, not four
    assert env.run(["--reps", "3", "--max-spend", "0.26"]) == 0
    out = capsys.readouterr().out
    assert "Stopped at the spend cap" in out and "3 draft(s) not made" in out
    assert "Measured spend $0.0120 of the $0.2600 cap" in out
    made = sorted(p.parent.parent.name + p.parent.name for p in env.out.glob("*/rep*/draft.json"))
    assert len(made) == 3
    assert len(env.calls()) == 3, "no call was made past the cap"


def test_max_spend_counts_an_unreported_cost_at_the_cap_never_as_zero():
    unknown = DraftCell(
        "t", 1, "h", "p", "s", "haiku", None, "failed", "crashed", "", None, 0, 0, 0, None
    )
    assert drafts._charge(unknown) == drafts.DEFAULT_CAP_MICROS
    kept = drafts._run_within(lambda item: unknown, [("a", 1), ("b", 1)], 400_000, [])
    assert len(kept) == 1, "after one unknown cost the next call might not fit"
    exact = drafts._run_within(lambda item: unknown, [("a", 1), ("b", 1)], 500_000, [])
    assert len(exact) == 2, "a call that fits the cap exactly is made"


def test_max_spend_reserves_the_staged_drafts_full_cap_not_the_single_call_cap():
    staged = 3 * drafts.DEFAULT_CAP_MICROS  # kn: stand-in for the three staged role caps
    cheap = DraftCell(
        "t", 1, "h", "p", "s", "haiku", None, "failed", "crashed", "", None, 0, 0, 0, None
    )
    started: list[object] = []

    def run(item):
        started.append(item)
        return cheap

    # room for one single-call cap but not a staged draft's worst case: no call may start
    assert drafts._run_within(run, [("a", 1)], staged - 1, [], staged) == []
    assert started == []
    # a staged draft with no reported cost is charged its full cap, so the second one is refused
    kept = drafts._run_within(run, [("a", 1), ("b", 1)], 2 * staged - 1, [], staged)
    assert len(kept) == 1 and drafts._charge(cheap, staged) == staged
    # drafts already made count at the same cap
    assert drafts._run_within(run, [("c", 1)], 2 * staged - 1, [cheap], staged) == []


def test_without_max_spend_every_draft_is_made(env):  # noqa: F811
    assert env.run(["--reps", "2"]) == 0
    assert len(list(env.out.glob("*/rep*/draft.json"))) == 4
