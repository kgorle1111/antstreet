"""B33: the roles are an ordinary, visible option, and the judge cannot decide pass or fail."""

import ast
import pathlib

import pytest

from antstreet import cli
from antstreet.roles import registry

SRC = pathlib.Path(cli.__file__).parent


def test_the_roles_option_is_visible_in_fund_help_and_names_the_critic(capsys):
    with pytest.raises(SystemExit):
        cli._parser().parse_args(["fund", "--help"])
    help_text = " ".join(capsys.readouterr().out.split())
    assert "--roles" in help_text and "critic is the one to try" in help_text


def test_no_role_is_on_by_default_and_the_critic_exists():
    assert "critic" in registry()
    assert not [name for name, spec in registry().items() if spec.default_on]


def test_the_judge_is_imported_only_by_the_pipeline_which_never_gates_on_it():
    importers = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").endswith("roles.judge"):
                importers.add(path.name)
                if path.name == "pipeline.py":
                    # a gate on a score would have to call require_calibrated first
                    assert "require_calibrated" not in {a.name for a in node.names}
    assert importers == {"pipeline.py"}
