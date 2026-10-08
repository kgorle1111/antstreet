"""The organisation chart is built from the roles themselves: hand-built registries for the shapes
that matter, and the real registry, whatever it holds when the test runs (empty is fine)."""

import pytest

from antstreet.roles import org, registry
from antstreet.roles.base import DEPARTMENTS, RoleSpec
from antstreet.roles.builders import PROFILES, WorkerProfile
from antstreet.roles.org import OrgError, OrgNode, org_chart, org_problems, render_org


def role(name, reports_to="boss", department="quality", **over) -> RoleSpec:
    fields = {
        "name": name,
        "department": department,
        "reports_to": reports_to,
        "purpose": f"{name} purpose",
        "gate": f"{name} gate",
        "prompt": "term_sheet_v1.md",
    }
    return RoleSpec(**fields | over)


def reg(*specs: RoleSpec) -> dict[str, RoleSpec]:
    return {s.name: s for s in specs}


def walk(node: OrgNode):
    yield node
    for child in node.children:
        yield from walk(child)


def find(node: OrgNode, name: str) -> OrgNode:
    return next(n for n in walk(node) if n.name == name)


def test_an_empty_registry_is_sound_and_still_shows_the_boss_and_the_builders():
    assert org_problems({}) == []
    chart = org_chart({}, PROFILES)
    assert chart.name == "investor" and chart.children[0].name == "boss"
    departments = chart.children[0].children
    assert [d.name for d in departments] == ["engineering"]
    assert [n.name for n in departments[0].children] == [p.name for p in PROFILES]
    assert all(n.kind == "profile" for n in departments[0].children)


def test_no_registry_and_no_profiles_is_a_chart_of_two():
    chart = org_chart({}, ())
    assert [n.name for n in walk(chart)] == ["investor", "boss"]
    assert render_org(chart).splitlines()[1].startswith("`-- boss")


def test_the_chart_is_investor_then_boss_then_departments_in_their_fixed_order():
    specs = reg(
        role("critic", department="advisory"),
        role("pm", department="product"),
        role("tester", department="quality"),
    )
    chart = org_chart(specs, ())
    assert chart.kind == "investor" and chart.children[0].kind == "boss"
    names = [d.name for d in chart.children[0].children]
    assert names == [d for d in DEPARTMENTS if d in {"advisory", "product", "quality"}]
    assert names == ["product", "quality", "advisory"]
    assert all(d.kind == "department" and d.children for d in chart.children[0].children)


def test_a_department_with_no_role_is_left_out_and_is_not_a_problem():
    specs = reg(role("pm", department="product"))
    assert org_problems(specs) == []
    names = [d.name for d in org_chart(specs, ()).children[0].children]
    assert names == ["product"]


def test_a_role_that_reports_to_a_role_hangs_under_it_not_under_its_department():
    specs = reg(
        role("lead", department="quality"),
        role("junior", reports_to="lead", department="engineering"),
        role("solo", department="quality"),
    )
    chart = org_chart(specs, ())
    lead = find(chart, "lead")
    assert [c.name for c in lead.children] == ["junior"]
    quality = find(chart, "quality")
    assert [c.name for c in quality.children] == ["lead", "solo"]
    assert "engineering" not in [d.name for d in chart.children[0].children]


def test_a_role_node_carries_its_purpose_gate_skills_and_switch():
    spec = role("tester", skills=("builder/exact-names",), default_on=True)
    node = find(org_chart(reg(spec), ()), "tester")
    assert (node.kind, node.purpose, node.gate) == ("role", "tester purpose", "tester gate")
    assert node.skills == ("builder/exact-names",) and node.default_on is True
    assert find(org_chart(reg(role("tester")), ()), "tester").default_on is False


def test_profiles_hang_under_engineering_and_only_the_loops_default_is_on():
    chart = org_chart(reg(role("dev", department="engineering")), PROFILES, "generalist")
    engineering = find(chart, "engineering")
    assert [c.name for c in engineering.children] == ["dev", *[p.name for p in PROFILES]]
    on = {n.name for n in walk(chart) if n.kind == "profile" and n.default_on}
    assert on == {"generalist"}
    none_on = org_chart(reg(role("dev", department="engineering")), PROFILES)
    assert not any(n.default_on for n in walk(none_on) if n.kind == "profile")
    node = find(chart, "ai_engineer")
    assert node.skills == PROFILES[2].skills and node.suited_to == PROFILES[2].suited_to


def test_a_role_reporting_to_a_role_that_does_not_exist_is_a_problem():
    problems = org_problems(reg(role("tester", reports_to="ghost")))
    assert problems == ["role tester reports to ghost, which is not a role"]


def test_a_role_reporting_to_itself_is_one_problem_and_not_also_a_cycle():
    assert org_problems(reg(role("loop", reports_to="loop"))) == ["role loop reports to itself"]


def test_a_cycle_is_named_once_however_many_roles_lead_into_it():
    specs = reg(
        role("aa", reports_to="bb"),
        role("bb", reports_to="cc"),
        role("cc", reports_to="aa"),
        role("tail", reports_to="aa"),
        role("fine"),
    )
    assert org_problems(specs) == ["roles aa, bb, cc report to each other in a cycle"]


def test_separate_cycles_are_separate_problems_in_a_fixed_order():
    pairs = [("aa", "bb"), ("cc", "dd"), ("ee", "ff"), ("gg", "hh"), ("ii", "jj"), ("kk", "ll")]
    specs = reg(*(r for x, y in pairs for r in (role(x, reports_to=y), role(y, reports_to=x))))
    assert org_problems(specs) == [
        f"roles {x}, {y} report to each other in a cycle" for x, y in pairs
    ]


def test_the_boss_and_the_investor_cannot_be_role_names():
    for name in ("boss", "investor"):
        assert f"role {name} has a reserved name" in org_problems(reg(role(name)))
    assert org_problems(reg(role("investor"))) == ["role investor has a reserved name"]


def test_a_broken_org_is_never_drawn_and_the_error_lists_every_problem():
    specs = reg(
        role("aa", reports_to="bb"), role("bb", reports_to="aa"), role("cc", reports_to="zz")
    )
    with pytest.raises(OrgError) as info:
        org_chart(specs, PROFILES)
    assert "cycle" in str(info.value) and "zz, which is not a role" in str(info.value)
    assert isinstance(info.value, ValueError)


def test_a_deep_chain_is_one_path_all_the_way_down_and_is_sound():
    depth = 150
    names = ["r" + chr(97 + n // 26) + chr(97 + n % 26) for n in range(depth)]
    specs = reg(
        *(role(name, reports_to=names[i - 1] if i else "boss") for i, name in enumerate(names))
    )
    assert org_problems(specs) == []
    node = find(org_chart(specs, ()), "quality")
    for name in names:
        assert [c.name for c in node.children] == [name]
        node = node.children[0]
    assert node.children == ()


def test_the_render_shows_purpose_gate_skills_and_default_for_every_role_and_profile():
    specs = reg(
        role("tester", skills=("builder/exact-names", "builder/trace-by-hand")),
        role("pm", department="product", default_on=True),
    )
    text = render_org(org_chart(specs, PROFILES[:2], "generalist"))
    assert text.endswith("\n") and "\t" not in text
    assert text.splitlines()[0].startswith("investor  ")
    assert "boss  drafts the tasks and the checks" in text
    assert "tester  [role, off by default]  tester purpose" in text
    assert "gate: tester gate" in text
    assert "skills: builder/exact-names, builder/trace-by-hand" in text
    assert "pm  [role, on by default]  pm purpose" in text
    assert "skills: none" in text
    assert "generalist  [profile, on by default]" in text
    assert "backend_engineer  [profile, off by default]" in text
    assert "suited to: " + PROFILES[0].suited_to in text
    assert f"gate: {org.BUILDER_GATE}" in text


def test_the_render_draws_a_tree_a_person_can_follow():
    specs = reg(
        role("lead"),
        role("junior", reports_to="lead"),
        role("other", department="advisory", default_on=True, skills=("builder/exact-names",)),
    )
    assert render_org(org_chart(specs, ())) == (
        "investor  funds the idea, approves the checks, rules on disputes\n"
        "`-- boss  drafts the tasks and the checks; the gate decides\n"
        "    |-- quality\n"
        "    |   `-- lead  [role, off by default]  lead purpose\n"
        "    |       |  gate: lead gate\n"
        "    |       |  skills: none\n"
        "    |       `-- junior  [role, off by default]  junior purpose\n"
        "    |             gate: junior gate\n"
        "    |             skills: none\n"
        "    `-- advisory\n"
        "        `-- other  [role, on by default]  other purpose\n"
        "              gate: other gate\n"
        "              skills: builder/exact-names\n"
    )


def test_render_is_stable_and_leaves_the_chart_unchanged():
    specs = reg(role("bb"), role("aa"))
    chart = org_chart(specs, PROFILES)
    assert render_org(chart) == render_org(org_chart(dict(reversed(specs.items())), PROFILES))


def test_the_real_registry_is_sound_and_every_role_and_profile_appears_once_in_the_chart():
    specs = registry()
    assert org_problems(specs) == [], "the roles do not form a tree under the boss"
    chart = org_chart(specs, PROFILES)
    seen = [n.name for n in walk(chart) if n.kind == "role"]
    assert sorted(seen) == sorted(specs)
    assert [n.name for n in walk(chart) if n.kind == "profile"] == [p.name for p in PROFILES]
    text = render_org(chart)
    for name, spec in specs.items():
        assert f"{name}  [role, {'on' if spec.default_on else 'off'} by default]" in text
        assert spec.gate in text and spec.purpose in text
        for skill in spec.skills:
            assert skill in text
    for p in PROFILES:
        assert p.name in text


def test_a_profile_may_not_be_built_without_a_purpose_so_the_chart_always_has_a_line_for_it():
    with pytest.raises(ValueError):
        WorkerProfile("empty", " ", (), "x")


def test_the_module_prints_the_firm_and_defines_no_roles(capsys):
    assert not hasattr(org, "SPECS")
    assert org.main() == 0
    out = capsys.readouterr().out
    assert out.startswith("investor") and "generalist" in out and out.endswith("\n")


def test_no_profile_is_on_unless_the_loop_uses_it_without_being_asked():
    chart = render_org(org_chart({}, PROFILES))
    assert "on by default" not in chart and "generalist  [profile, off by default]" in chart
    chosen = render_org(org_chart({}, PROFILES, "backend_engineer"))
    assert "backend_engineer  [profile, on by default]" in chosen
    assert "generalist  [profile, off by default]" in chosen
