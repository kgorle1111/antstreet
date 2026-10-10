"""`antstreet.gitrepo`: git treated as hostile input. A repository whose config names programs never
runs them, a ref that looks like an option never reaches git, and an export touches nothing."""

import io
import os
import subprocess
import sys
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from antstreet import gitrepo
from antstreet.gitrepo import (
    GitError,
    commits_between,
    diff,
    export,
    is_ancestor,
    is_clean,
    resolve,
)

PLAIN_ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    """Plain git as the test author, for building fixtures and for the 'is the trap live' checks."""
    done = subprocess.run(
        ["git", "-C", str(repo), *args], env={**PLAIN_ENV, **(env or {})},
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    return done.stdout.strip()


def commit(repo: Path, name: str, text: str, when: str = "2024-01-02T03:04:05+00:00") -> str:
    (repo / name).write_text(text)
    git(repo, "add", name)
    env = {"GIT_COMMITTER_DATE": when, "GIT_AUTHOR_DATE": when}
    git(repo, "commit", "-q", "-m", f"add {name}", env=env)
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    return root


@pytest.fixture
def two(repo):
    """(repo, first commit, second commit)."""
    first = commit(repo, "a.txt", "one\n", "2024-01-02T03:04:05+00:00")
    second = commit(repo, "b.txt", "two\n", "2024-02-03T04:05:06+00:00")
    return repo, first, second


# --- refs -----------------------------------------------------------------------------------


def test_resolve_takes_a_branch_a_tag_a_full_hash_and_a_short_hash(two):
    root, first, second = two
    git(root, "tag", "v1", first)
    assert resolve(root, "main") == second
    assert resolve(root, "v1") == first
    assert resolve(root, first) == first
    assert resolve(root, first[:10]) == first
    assert resolve(root, "HEAD") == second


def test_an_annotated_tag_resolves_to_its_commit(two):
    root, first, _ = two
    git(root, "tag", "-a", "-m", "note", "v1", first)
    assert resolve(root, "v1") == first


def test_an_option_shaped_ref_is_refused_and_nothing_is_written(two, tmp_path):
    root, _, _ = two
    target = tmp_path / "x"
    for ref in (f"--output={target}", "-x", "--", "-"):
        with pytest.raises(GitError, match="starts with '-'"):
            resolve(root, ref)
    assert not target.exists()


@pytest.mark.parametrize(
    "ref", ["HEAD~1", "main^", "main..HEAD", "main:a.txt", "@{u}", "a b", "a\nb", "main\\x", ""]
)
def test_a_revision_expression_is_not_a_ref_name(two, ref):
    with pytest.raises(GitError):
        resolve(two[0], ref)


def test_a_nul_or_oversized_ref_is_refused(two):
    for ref in ("a\x00b", "a" * 300, None, 5):
        with pytest.raises(GitError):
            resolve(two[0], ref)  # type: ignore[arg-type]


def test_an_unknown_ref_says_what_to_try(two):
    with pytest.raises(GitError, match=r"names no commit.*try"):
        resolve(two[0], "nope")


def test_a_ref_to_a_tree_is_not_a_commit(two):
    root, _, _ = two
    tree = git(root, "rev-parse", "HEAD^{tree}")
    with pytest.raises(GitError, match="names no commit"):
        resolve(root, tree)


def test_a_folder_that_is_not_a_checkout_root_is_refused(two, tmp_path):
    sub = two[0] / "sub"
    sub.mkdir()
    for folder in (sub, tmp_path):
        with pytest.raises(GitError, match="top folder of a git checkout"):
            resolve(folder, "main")


# --- hostile config -------------------------------------------------------------------------


@pytest.fixture
def hostile(two, tmp_path):
    """Two commits whose tree selects filters and a diff driver, then a `.git/config` that names
    a program for every hook of git it can, each of which drops a file in `markers/` if it runs."""
    root, first, second = two
    (root / ".gitattributes").write_text("* filter=evil diff=evil\n")
    git(root, "add", ".gitattributes")
    git(root, "commit", "-q", "-m", "attrs")
    markers = tmp_path / "markers"
    markers.mkdir()
    script = tmp_path / "evil.sh"
    script.write_text(f'#!/bin/sh\ntouch "{markers}/$(basename "$0")-$$"\ncat\n')
    script.chmod(0o755)
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    for name in ("pre-commit", "post-checkout", "post-index-change", "reference-transaction"):
        (hooks / name).write_text(f'#!/bin/sh\ntouch "{markers}/hook-{name}"\n')
        (hooks / name).chmod(0o755)
    for key, value in {
        "core.fsmonitor": str(script),
        "core.hooksPath": str(hooks),
        "diff.external": str(script),
        "diff.evil.textconv": str(script),
        "diff.evil.command": str(script),
        "filter.evil.smudge": str(script),
        "filter.evil.clean": str(script),
        "filter.evil.process": str(script),
        "tar.tar.command": str(script),
        "core.pager": str(script),
        "core.sshCommand": str(script),
        "gpg.program": str(script),
        "log.showSignature": "true",
        "core.alternateRefsCommand": str(script),
    }.items():
        git(root, "config", key, value)
    return root, first, second, markers


def ran(markers: Path) -> list[str]:
    return sorted(p.name for p in markers.iterdir())


def test_the_traps_are_live_for_plain_git(hostile):
    """If plain git did not run them, the next test would pass for the wrong reason."""
    root, _, _, markers = hostile
    git(root, "status", "--porcelain")
    git(root, "archive", "--format=tar", "HEAD")
    names = ran(markers)
    assert any(n.startswith("evil.sh") for n in names)
    assert len(names) >= 2


def test_no_program_named_by_the_repository_config_runs(hostile, tmp_path):
    root, first, second, markers = hostile
    assert is_clean(root) in (True, False)
    assert resolve(root, "main") == resolve(root, "HEAD")
    head = resolve(root, "main")
    assert is_ancestor(root, first, head)
    assert [c.sha for c in commits_between(root, first, "main")][-1] == head
    assert "+two" in diff(root, first, head)
    export(root, head, tmp_path / "out")  # the tree at `head` selects the evil filter
    assert (tmp_path / "out" / "b.txt").read_text() == "two\n"
    assert ran(markers) == []


def test_a_hostile_environment_does_not_reach_git(two, monkeypatch, tmp_path):
    root, first, second = two
    marker = tmp_path / "ext-ran"
    script = tmp_path / "ext.sh"
    script.write_text(f'#!/bin/sh\ntouch "{marker}"\n')
    script.chmod(0o755)
    monkeypatch.setenv("GIT_EXTERNAL_DIFF", str(script))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "elsewhere"))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "elsewhere"))
    assert "+two" in diff(root, first, second)
    assert resolve(root, "main") == second
    assert not marker.exists()


def test_every_git_process_carries_the_hardening_flags_and_no_shell(two, tmp_path, monkeypatch):
    root, first, second = two
    seen: list[list[str]] = []
    real = gitrepo._popen

    def spy(cmd, cwd, **kwargs):
        assert "shell" not in kwargs and isinstance(cmd, list)
        seen.append(cmd)
        return real(cmd, cwd, **kwargs)

    monkeypatch.setattr(gitrepo, "_popen", spy)
    resolve(root, "main")
    is_clean(root)
    is_ancestor(root, first, second)
    commits_between(root, first, second)
    diff(root, first, second)
    export(root, second, tmp_path / "out")
    assert len(seen) > 15
    for cmd in seen:
        assert cmd[1:7] == [
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "diff.external=",
        ], cmd
        assert cmd[0].endswith("git")


def test_replace_objects_cannot_change_what_is_read(two):
    root, first, second = two
    before = diff(root, first, second)
    git(root, "replace", "-f", second, first)
    assert diff(root, first, second) == before


# --- is_clean -------------------------------------------------------------------------------


def test_a_clean_tree_is_clean_and_each_kind_of_change_is_not(two):
    root, _, _ = two
    assert is_clean(root)
    (root / "a.txt").write_text("changed\n")
    assert not is_clean(root)
    git(root, "checkout", "--", "a.txt")
    assert is_clean(root)
    (root / "new.txt").write_text("x")
    assert not is_clean(root)
    git(root, "add", "new.txt")
    assert not is_clean(root)
    git(root, "rm", "-q", "-f", "new.txt")
    (root / "b.txt").unlink()
    assert not is_clean(root)


def test_an_ignored_file_and_a_touched_file_do_not_make_a_tree_dirty(two):
    root, _, _ = two
    (root / ".gitignore").write_text("*.log\n")
    git(root, "add", ".gitignore")
    git(root, "commit", "-q", "-m", "ignore")
    (root / "run.log").write_text("noise")
    os.utime(root / "a.txt", (1, 1))
    assert is_clean(root)


def test_is_clean_does_not_write_the_index(two):
    root, _, _ = two
    os.utime(root / "a.txt", (1, 1))
    index = root / ".git" / "index"
    before = (index.read_bytes(), index.stat().st_mtime_ns)
    is_clean(root)
    assert (index.read_bytes(), index.stat().st_mtime_ns) == before


def test_a_repo_with_no_commit_cannot_be_called_clean(repo):
    with pytest.raises(GitError, match="no commits yet"):
        is_clean(repo)


def global_config(monkeypatch, tmp_path, text: str) -> Path:
    cfg = tmp_path / "global.gitconfig"
    cfg.write_text(text)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(cfg))
    return cfg


def test_a_file_ignored_by_the_global_excludes_file_is_clean(two, monkeypatch, tmp_path):
    root, _, _ = two
    ignore = tmp_path / "global_ignore"
    ignore.write_text("*.scratch\n")
    (root / "x.scratch").write_text("noise")
    assert not is_clean(root)
    global_config(monkeypatch, tmp_path, f"[core]\n\texcludesFile = {ignore}\n")
    assert is_clean(root)


def test_the_repo_excludes_file_setting_wins_over_the_global_one(two, monkeypatch, tmp_path):
    root, _, _ = two
    mine, theirs = tmp_path / "mine", tmp_path / "theirs"
    mine.write_text("*.scratch\n")
    theirs.write_text("*.other\n")
    global_config(monkeypatch, tmp_path, f"[core]\n\texcludesFile = {theirs}\n")
    git(root, "config", "core.excludesFile", str(mine))
    (root / "x.scratch").write_text("noise")
    assert is_clean(root)


def test_file_mode_false_makes_a_mode_only_change_clean(two):
    root, _, _ = two
    (root / "a.txt").chmod(0o755)
    git(root, "config", "core.fileMode", "true")
    assert not is_clean(root)
    git(root, "config", "core.fileMode", "false")
    assert is_clean(root)


@pytest.mark.parametrize("value", ["maybe", "$(touch pwned)", "2", "x y"])
def test_a_non_boolean_setting_is_ignored_not_executed(two, tmp_path, monkeypatch, value):
    root, _, _ = two
    global_config(
        monkeypatch,
        tmp_path,
        f'[core]\n\tfileMode = "{value}"\n\tautocrlf = "{value}"\n\tignoreCase = "{value}"\n',
    )
    assert is_clean(root)
    assert not (root / "pwned").exists() and not (tmp_path / "pwned").exists()


def test_an_unreadable_or_missing_excludes_file_is_ignored(two, tmp_path):
    root, _, _ = two
    for target in ("/nonexistent/ignore", "/etc/shadow", str(tmp_path), "relative/path"):
        git(root, "config", "core.excludesFile", target)
        assert is_clean(root)
        (root / "y.txt").write_text("untracked")
        assert not is_clean(root)
        (root / "y.txt").unlink()


def test_a_program_naming_setting_is_never_copied_into_the_view(two, tmp_path, monkeypatch):
    root, _, _ = two
    marker = tmp_path / "ran"
    git(root, "config", "core.fsmonitor", f"touch {marker}")
    git(root, "config", "core.autocrlf", "input")
    seen: list[list[str]] = []
    real = gitrepo._popen

    def spy(cmd, cwd, **kw):
        seen.append(cmd)
        return real(cmd, cwd, **kw)

    monkeypatch.setattr(gitrepo, "_popen", spy)
    assert is_clean(root)
    flat = " ".join(" ".join(c) for c in seen)
    assert "core.autocrlf=input" in flat and "fsmonitor=touch" not in flat
    assert not marker.exists()


# --- bounded output ---------------------------------------------------------------------------


def test_output_over_the_cap_kills_the_process_early(tmp_path, monkeypatch):
    marker = tmp_path / "finished"
    script = tmp_path / "flood.py"
    script.write_text(
        "import sys, time, pathlib\n"
        "sys.stdout.buffer.write(b'x' * 200000); sys.stdout.buffer.flush()\n"
        "time.sleep(20)\n"
        f"pathlib.Path({str(marker)!r}).write_text('done')\n"
    )
    monkeypatch.setattr(gitrepo, "MAX_OUTPUT_BYTES", 1000)
    monkeypatch.setattr(gitrepo, "_command", lambda *a, **k: [sys.executable, str(script)])
    started = time.monotonic()
    with pytest.raises(GitError, match="its output is over the size cap"):
        gitrepo._run(["flood"], gitdir=None, cwd=tmp_path)
    assert time.monotonic() - started < 10
    assert not marker.exists()


def test_output_under_the_cap_comes_back_whole_and_stderr_names_a_failure(tmp_path, monkeypatch):
    script = tmp_path / "quiet.py"
    script.write_text(
        "import sys\nsys.stdout.write('a' * 5000)\nsys.stderr.write('boom ' * 100000)\n"
        "sys.exit(int(sys.argv[1]))\n"
    )
    monkeypatch.setattr(
        gitrepo, "_command", lambda args, *a, **k: [sys.executable, str(script), *args]
    )
    code, out = gitrepo._run(["0"], gitdir=None, cwd=tmp_path)
    assert (code, out) == (0, b"a" * 5000)
    with pytest.raises(GitError, match="boom"):
        gitrepo._run(["3"], gitdir=None, cwd=tmp_path)


def test_a_command_that_runs_too_long_is_killed(tmp_path, monkeypatch):
    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(30)\n")
    monkeypatch.setattr(gitrepo, "_command", lambda *a, **k: [sys.executable, str(script)])
    started = time.monotonic()
    with pytest.raises(GitError, match="ran longer than"):
        gitrepo._run(["slow"], gitdir=None, cwd=tmp_path, timeout_s=1)
    assert time.monotonic() - started < 10


# --- history --------------------------------------------------------------------------------


def test_ancestry(two):
    root, first, second = two
    assert is_ancestor(root, first, second)
    assert is_ancestor(root, second, second)
    assert not is_ancestor(root, second, first)


def test_a_divergent_branch_is_not_a_descendant(two):
    root, first, second = two
    git(root, "checkout", "-q", "-b", "other", first)
    other = commit(root, "c.txt", "three\n")
    assert not is_ancestor(root, second, other)
    assert not is_ancestor(root, other, second)
    assert is_ancestor(root, first, other)


def test_commits_between_are_oldest_first_with_committer_dates(two):
    root, first, second = two
    third = commit(root, "c.txt", "three\n", "2024-03-04T05:06:07+00:00")
    got = commits_between(root, first, third)
    assert [c.sha for c in got] == [second, third]
    assert got[0].committed_at == datetime(2024, 2, 3, 4, 5, 6, tzinfo=UTC)
    assert got[1].committed_at == datetime(2024, 3, 4, 5, 6, 7, tzinfo=UTC)
    assert commits_between(root, third, third) == []


def test_diff_shows_added_lines_and_is_empty_for_the_same_commit(two):
    root, first, second = two
    text = diff(root, first, second)
    assert "+++ b/b.txt" in text and "+two" in text
    assert diff(root, second, second) == ""


def test_a_linked_worktree_works(two, tmp_path):
    root, first, second = two
    linked = tmp_path / "linked"
    git(root, "worktree", "add", "-q", "-b", "side", str(linked), first)
    assert resolve(linked, "side") == first
    assert is_clean(linked)
    assert is_ancestor(linked, first, second)
    export(linked, second, tmp_path / "out")
    assert (tmp_path / "out" / "b.txt").exists()


def test_a_sha256_repository_works(tmp_path):
    root = tmp_path / "r256"
    root.mkdir()
    try:
        git(root, "init", "-q", "-b", "main", "--object-format=sha256")
    except subprocess.CalledProcessError:
        pytest.skip("this git has no sha256 repositories")
    first = commit(root, "a.txt", "one\n")
    second = commit(root, "b.txt", "two\n")
    assert len(first) == 64 and resolve(root, "main") == second
    assert is_ancestor(root, first, second)


# --- export ---------------------------------------------------------------------------------


def test_export_writes_the_tree_and_leaves_the_checkout_alone(two, tmp_path):
    root, first, second = two
    (root / "dirty.txt").write_text("not committed")
    (root / "a.txt").write_text("edited")
    run = root / "run.sh"
    run.write_text("#!/bin/sh\n")
    run.chmod(0o755)
    git(root, "add", "run.sh")
    git(root, "commit", "-q", "-m", "exec")
    (root / "link").symlink_to("a.txt")
    git(root, "add", "link")
    git(root, "commit", "-q", "-m", "link")
    head = git(root, "rev-parse", "HEAD")
    status = git(root, "status", "--porcelain=v2")
    index = (root / ".git" / "index").read_bytes()
    tree = (root / "a.txt").read_text()

    export(root, head, tmp_path / "out")

    out = tmp_path / "out"
    assert sorted(p.name for p in out.iterdir()) == ["a.txt", "b.txt", "link", "run.sh"]
    assert (out / "a.txt").read_text() == "one\n"  # the committed text, not the edit
    assert os.access(out / "run.sh", os.X_OK)
    assert (out / "link").is_symlink() and os.readlink(out / "link") == "a.txt"
    assert not (out / "dirty.txt").exists() and not (out / ".git").exists()
    assert git(root, "status", "--porcelain=v2") == status
    assert (root / ".git" / "index").read_bytes() == index
    assert (root / "a.txt").read_text() == tree
    assert git(root, "rev-parse", "HEAD") == head


def test_export_of_an_old_commit_is_that_commits_tree(two, tmp_path):
    root, first, _ = two
    export(root, first, tmp_path / "out")
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["a.txt"]


def test_export_refuses_a_folder_that_has_something_in_it(two, tmp_path):
    root, _, second = two
    full = tmp_path / "full"
    full.mkdir()
    (full / "keep").write_text("mine")
    with pytest.raises(GitError, match="not an empty folder"):
        export(root, second, full)
    assert (full / "keep").read_text() == "mine"
    export(root, second, tmp_path / "empty-ok")  # an existing empty folder is fine
    empty = tmp_path / "empty"
    empty.mkdir()
    export(root, second, empty)
    assert (empty / "b.txt").exists()


def test_export_refuses_a_ref_that_is_not_a_commit(two, tmp_path):
    with pytest.raises(GitError):
        export(two[0], "--output=/tmp/x", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_a_link_that_leaves_the_export_folder_is_refused_and_removed(two, tmp_path):
    root, _, _ = two
    (root / "escape").symlink_to("../../../etc/passwd")
    git(root, "add", "escape")
    git(root, "commit", "-q", "-m", "escape")
    with pytest.raises(GitError, match="was refused"):
        export(root, "main", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_git_itself_will_not_archive_a_dot_git_path_and_nothing_is_left(two, tmp_path):
    """A crafted tree object can hold `.git/config`; `git archive` refuses it and so do we."""
    root, _, _ = two

    def plumbing(*args: str, text: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(root), *args], input=text, text=True, capture_output=True,
            check=True, env=PLAIN_ENV,
        )  # fmt: skip
        return done.stdout.strip()

    blob = plumbing("hash-object", "-w", "--stdin", text="[core]\n")
    inner = plumbing("mktree", text=f"100644 blob {blob}\tconfig\n")
    top = plumbing("mktree", text=f"040000 tree {inner}\t.git\n")
    evil = git(root, "commit-tree", top, "-m", "evil")
    with pytest.raises(GitError, match="was refused"):
        export(root, evil, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("name", [".git/config", "x/.GIT/hooks/pre-commit", ".Git"])
def test_a_tar_member_with_a_dot_git_component_is_refused_whatever_its_case(tmp_path, name):
    """The second line of defence, in case an archive ever carries one: checked on the stream."""
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        info = tarfile.TarInfo(name)
        info.size = 2
        tar.addfile(info, io.BytesIO(b"hi"))
    stream.seek(0)
    with pytest.raises(GitError, match=r"`\.git` folder"):
        gitrepo._extract(stream, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_a_device_file_in_a_tar_stream_is_refused(tmp_path):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        info = tarfile.TarInfo("dev")
        info.type = tarfile.CHRTYPE
        tar.addfile(info)
    stream.seek(0)
    with pytest.raises(GitError, match="device or pipe"):
        gitrepo._extract(stream, tmp_path)


def test_an_oversized_tree_is_refused(two, tmp_path, monkeypatch):
    monkeypatch.setattr(gitrepo, "MAX_EXPORT_BYTES", 3)
    with pytest.raises(GitError, match="size cap"):
        export(two[0], "main", tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_head_in_a_repo_with_no_commits_says_to_commit_first(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    with pytest.raises(gitrepo.GitError, match="this repo has no commits yet") as caught:
        gitrepo.resolve(tmp_path, "HEAD")
    assert "git add -A && git commit" in str(caught.value)
    with pytest.raises(gitrepo.GitError, match="names no commit"):  # other refs: as before
        gitrepo.resolve(tmp_path, "main")
