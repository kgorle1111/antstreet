"""`check_workspace` refuses agent configuration wherever a worker planted it."""

import os
from pathlib import Path

import pytest

from boss.runner import WorkspaceError, check_workspace


def test_a_clean_workspace_passes(tmp_path: Path):
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "mod.py").write_text("x = 1\n")
    (tmp_path / ".claude-notes.md").write_text("not config\n")  # only the exact names count
    (tmp_path / "claude").mkdir()
    check_workspace(tmp_path)


@pytest.mark.parametrize(
    ("planted", "offender"),
    [
        (".claude/settings.json", ".claude"),
        ("sub/.claude/settings.json", "sub/.claude"),
        ("a/b/c/.claude/commands/x.md", "a/b/c/.claude"),
        (".mcp.json", ".mcp.json"),
        ("sub/.mcp.json", "sub/.mcp.json"),
        ("a/b/c/.mcp.json", "a/b/c/.mcp.json"),
    ],
)
def test_agent_config_at_any_depth_is_refused_and_named(tmp_path: Path, planted, offender):
    target = tmp_path / planted
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}")
    with pytest.raises(WorkspaceError, match="agent configuration") as excinfo:
        check_workspace(tmp_path)
    assert str(excinfo.value).endswith(f"[{offender!r}]")


def test_every_offender_is_named_in_sorted_order(tmp_path: Path):
    for rel in ("z/.mcp.json", "a/.claude/x", ".mcp.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("{}")
    with pytest.raises(WorkspaceError) as excinfo:
        check_workspace(tmp_path)
    assert str(excinfo.value).endswith("['.mcp.json', 'a/.claude', 'z/.mcp.json']")


def test_a_nested_config_directory_that_is_empty_is_still_refused(tmp_path: Path):
    (tmp_path / "sub" / ".claude").mkdir(parents=True)
    with pytest.raises(WorkspaceError, match="sub/.claude"):
        check_workspace(tmp_path)


def test_a_dangling_symlink_with_a_forbidden_name_is_refused(tmp_path: Path):
    (tmp_path / "sub").mkdir()
    os.symlink(tmp_path / "nowhere", tmp_path / "sub" / ".mcp.json")
    with pytest.raises(WorkspaceError, match="sub/.mcp.json"):
        check_workspace(tmp_path)


def test_a_symlinked_directory_is_not_followed_out_of_the_workspace(tmp_path: Path):
    outside = tmp_path / "outside"
    (outside / ".claude").mkdir(parents=True)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "ok.py").write_text("x = 1\n")
    os.symlink(outside, workspace / "link")  # holds a .claude, but only through the link
    check_workspace(workspace)


def test_a_symlink_named_dot_claude_is_refused_even_though_it_points_out(tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace = tmp_path / "ws"
    (workspace / "sub").mkdir(parents=True)
    os.symlink(outside, workspace / "sub" / ".claude")
    with pytest.raises(WorkspaceError, match="sub/.claude"):
        check_workspace(workspace)


def test_an_unreadable_subdirectory_is_refused_not_skipped(tmp_path: Path):
    hidden = tmp_path / "locked"
    hidden.mkdir()
    (hidden / ".claude").mkdir()
    hidden.chmod(0)
    try:
        if os.access(hidden, os.R_OK):
            pytest.skip("permissions are not enforced for this user")
        with pytest.raises(WorkspaceError, match="cannot inspect"):
            check_workspace(tmp_path)
    finally:
        hidden.chmod(0o700)


def test_a_missing_workspace_is_refused(tmp_path: Path):
    with pytest.raises(WorkspaceError, match="does not exist"):
        check_workspace(tmp_path / "gone")
